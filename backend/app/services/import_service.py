import csv
import io
import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import structlog

from app.core.security import SecurityService
from app.models.enums import EventStatus, SourceType
from app.repositories.audit_trace_repo import AuditTraceRepository
from app.repositories.dictionary_repo import DictionaryRepository
from app.repositories.event_repo import EventRepository
from app.repositories.raw_record_repo import RawRecordRepository
from app.schemas.import_mod import ImportReportDTO, ImportReportItemErrorDTO
from app.services.deduplication_service import DeduplicationService
from app.services.embedding_service import EmbeddingService
from app.services.normalization_service import NormalizationService

logger = structlog.get_logger(__name__)


class ImportService:
    """Сервис импорта данных из CSV/JSON, дедупликации и переигрывания нормализации."""

    def __init__(
        self,
        event_repo: EventRepository,
        raw_repo: RawRecordRepository,
        dict_repo: DictionaryRepository,
        audit_repo: AuditTraceRepository,
        norm_service: NormalizationService | None = None,
        dedup_service: DeduplicationService | None = None,
        emb_service: EmbeddingService | None = None,
    ) -> None:
        self.event_repo = event_repo
        self.raw_repo = raw_repo
        self.dict_repo = dict_repo
        self.audit_repo = audit_repo
        self.norm_service = norm_service or NormalizationService()
        self.dedup_service = dedup_service or DeduplicationService()
        self.emb_service = emb_service or EmbeddingService()

    async def import_file(
        self,
        file_bytes: bytes,
        filename: str,
        actor_id: str,
        request_id: str,
    ) -> ImportReportDTO:
        """Идемпотентный импорт файла CSV или JSON со сведением дубликатов."""
        rows = self._parse_file_to_rows(file_bytes, filename)
        report = ImportReportDTO(total_received=len(rows))

        for idx, row in enumerate(rows, start=1):
            try:
                await self._process_single_row(row, idx, actor_id, request_id, report)
            except Exception as e:
                logger.error("import_row_unexpected_error", row_index=idx, error=str(e))
                report.rejected_count += 1
                report.errors.append(
                    ImportReportItemErrorDTO(
                        row_index=idx,
                        raw_title=str(row.get("title") or row.get("name")),
                        reason=f"Внутренняя ошибка обработки строки: {str(e)}",
                    )
                )

        # Логирование в аудит
        await self.audit_repo.log_change(
            request_id=request_id,
            actor_id=actor_id,
            action="import_batch",
            entity_type="event_import",
            entity_id=report.errors[0].row_index if report.errors else UUID(int=0),
            changes={
                "filename": filename,
                "total": report.total_received,
                "added": report.added_count,
                "merged": report.deduplicated_merged_count,
                "rejected": report.rejected_count,
            },
        )

        return report

    async def _process_single_row(
        self,
        raw_row: dict[str, Any],
        row_index: int,
        actor_id: str,
        request_id: str,
        report: ImportReportDTO,
    ) -> None:
        raw_title = raw_row.get("title") or raw_row.get("name")
        if not raw_title or not str(raw_title).strip():
            report.rejected_count += 1
            report.errors.append(
                ImportReportItemErrorDTO(
                    row_index=row_index,
                    raw_title=None,
                    reason="Отсутствует обязательное поле названия мероприятия (title/name)",
                )
            )
            return

        raw_title_str = str(raw_title).strip()
        source_url = str(raw_row.get("source_url") or raw_row.get("url") or "https://culture.bashkortostan.ru")
        raw_date_start = raw_row.get("date_start") or raw_row.get("date")

        if not raw_date_start:
            report.rejected_count += 1
            report.errors.append(
                ImportReportItemErrorDTO(
                    row_index=row_index,
                    raw_title=raw_title_str,
                    reason="Отсутствует обязательное поле даты начала (date_start/date)",
                )
            )
            return

        date_start = self.norm_service.parse_date_to_yekaterinburg(raw_date_start)
        date_start_iso = date_start.isoformat()

        # 1. Сверка source_hash для 100% идемпотентности
        source_hash = SecurityService.compute_source_hash(source_url, raw_title_str, date_start_iso)
        existing_raw = await self.raw_repo.get_by_hash(source_hash)
        if existing_raw:
            # Карточка уже ранее была импортирована без изменений
            report.updated_count += 1
            return

        # 2. Сохранение сырой записи в raw_event_records
        raw_record = await self.raw_repo.save_raw_record(
            source_type=SourceType.IMPORT,
            source_url=source_url,
            source_hash=source_hash,
            raw_payload=raw_row,
            imported_by=actor_id,
        )

        # 3. Нормализация полей
        title = self.norm_service.normalize_title(raw_title_str)
        normalized_title = title.lower()

        # Город
        raw_city = str(raw_row.get("city") or "Уфа").strip()
        resolved_city = await self.dict_repo.resolve_city_name(raw_city) or raw_city

        venue = str(raw_row.get("venue") or raw_row.get("place") or "Площадка мероприятия").strip()
        address = str(raw_row.get("address") or f"г. {resolved_city}, {venue}").strip()
        description = str(raw_row.get("description") or title).strip()

        # Цены
        raw_price = raw_row.get("price") or raw_row.get("price_min")
        price_min, price_max, is_free = self.norm_service.parse_price_text(raw_price)

        # Возраст
        age_limit = self.norm_service.normalize_age_limit(raw_row.get("age_limit"), description)

        # Категория
        raw_category = raw_row.get("category")
        category, auto_tags = self.norm_service.normalize_category(str(raw_category) if raw_category else None, title, description)
        existing_tags = raw_row.get("tags") or []
        if isinstance(existing_tags, str):
            existing_tags = [t.strip() for t in existing_tags.split(",") if t.strip()]
        tags = list(set(existing_tags + auto_tags))

        # 4. Формирование dedup_key
        dedup_key = self.dedup_service.build_dedup_key(
            city=resolved_city,
            venue=venue,
            date_start=date_start,
            normalized_title=normalized_title,
        )

        # 5. Оценка уверенности и отправка на модерацию при необходимости
        event_dict_payload: dict[str, Any] = {
            "title": title,
            "normalized_title": normalized_title,
            "category": category,
            "tags": tags,
            "date_start": date_start,
            "date_end": self.norm_service.parse_date_to_yekaterinburg(raw_row.get("date_end")) if raw_row.get("date_end") else None,
            "duration_min": int(raw_row.get("duration_min")) if raw_row.get("duration_min") else None,
            "city": resolved_city,
            "venue": venue,
            "address": address,
            "lat": float(raw_row["lat"]) if raw_row.get("lat") else None,
            "lon": float(raw_row["lon"]) if raw_row.get("lon") else None,
            "description": description,
            "price_min": price_min,
            "price_max": price_max,
            "is_free": is_free,
            "age_limit": age_limit,
            "language": str(raw_row.get("language")).strip() if raw_row.get("language") else None,
            "org_link": str(raw_row.get("org_link") or raw_row.get("tickets_url") or "").strip() or None,
            "source_url": source_url,
            "source_type": SourceType.IMPORT,
            "source_hash": source_hash,
            "verified_at": datetime.now(timezone.utc),
            "dedup_key": dedup_key,
        }

        confidence, is_disputed, dispute_reason = self.dedup_service.evaluate_confidence_and_disputes(event_dict_payload)
        event_dict_payload["confidence"] = confidence
        event_dict_payload["is_disputed"] = is_disputed
        event_dict_payload["dispute_reason"] = dispute_reason
        event_dict_payload["status"] = EventStatus.DRAFT if is_disputed else EventStatus.PUBLISHED

        if is_disputed:
            report.flagged_for_moderation_count += 1

        # 6. Вычисление эмбеддинга
        embedding = await self.emb_service.generate_embedding(f"{title} {description}")
        event_dict_payload["embedding"] = embedding

        # 7. Идемпотентное сохранение / дедупликация
        event, action = await self.event_repo.create_or_update_event(
            event_data=event_dict_payload,
            raw_record_id=raw_record.id,
        )

        await self.raw_repo.update_processed_event_id(raw_record.id, event.id)

        if action == "merged":
            report.deduplicated_merged_count += 1
        elif action == "added":
            report.added_count += 1
        else:
            report.updated_count += 1

    async def replay_all_normalizations(
        self,
        actor_id: str,
        request_id: str,
    ) -> ImportReportDTO:
        """Переигрывает нормализацию по сырым данным без повторного обращения к внешним источникам."""
        report = ImportReportDTO()

        idx = 1
        async for batch in self.raw_repo.list_all_for_replay(batch_size=100):
            report.total_received += len(batch)
            for record in batch:
                try:
                    await self._process_single_row(
                        raw_row=record.raw_payload,
                        row_index=idx,
                        actor_id=actor_id,
                        request_id=request_id,
                        report=report,
                    )
                except Exception as e:
                    report.rejected_count += 1
                    report.errors.append(
                        ImportReportItemErrorDTO(
                            row_index=idx,
                            raw_title=str(record.raw_payload.get("title")),
                            reason=f"Ошибка переигровки нормализации: {str(e)}",
                        )
                    )
                idx += 1

        return report

    def _parse_file_to_rows(self, file_bytes: bytes, filename: str) -> list[dict[str, Any]]:
        """Разбирает CSV или JSON в список словарей."""
        filename_lower = filename.lower()
        if filename_lower.endswith(".json"):
            content_str = file_bytes.decode("utf-8-sig")
            data = json.loads(content_str)
            if isinstance(data, list):
                return data
            elif isinstance(data, dict) and "events" in data:
                return data["events"]
            return [data]
        else:
            # CSV parsing
            content_str = file_bytes.decode("utf-8-sig")
            f = io.StringIO(content_str)
            reader = csv.DictReader(f)
            return [dict(row) for row in reader]
