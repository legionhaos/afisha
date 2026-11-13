import csv
import io
import json
import re
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import structlog

from app.core.security import SecurityService
from app.models.enums import EventStatus, ModerationReason, SourceType
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
            except (ValueError, TypeError) as exc:
                report.rejected_count += 1
                title = row.get("title") or row.get("name")
                report.errors.append(ImportReportItemErrorDTO(
                    row_index=idx, raw_title=str(title) if title is not None else None, reason=str(exc),
                ))

        # Логирование в аудит
        await self.audit_repo.log_change(
            request_id=request_id,
            actor_id=actor_id,
            action="import_batch",
            entity_type="event_import",
            entity_id=UUID(int=0),
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
        replay_record: Any | None = None,
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
        source_url = str(raw_row.get("source_url") or raw_row.get("url") or "").strip()
        if not source_url:
            report.rejected_count += 1
            report.errors.append(ImportReportItemErrorDTO(
                row_index=row_index, raw_title=raw_title_str,
                reason="Отсутствует обязательная ссылка на источник (source_url/url)",
            ))
            return
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
        if replay_record is None:
            existing_raw = await self.raw_repo.get_by_hash(source_hash)
            if existing_raw:
                report.updated_count += 1
                return
            raw_record = await self.raw_repo.save_raw_record(
                source_type=SourceType.IMPORT,
                source_url=source_url,
                source_hash=source_hash,
                raw_payload=raw_row,
                imported_by=actor_id,
            )
            if raw_record is None:
                report.updated_count += 1
                return
        else:
            raw_record = replay_record
            source_hash = raw_record.source_hash

        # 3. Нормализация полей
        title = self.norm_service.normalize_title(raw_title_str)
        normalized_title = title.lower()

        # Отсутствующие факты нельзя заменять вымышленными значениями.
        required = {
            "city": raw_row.get("city"),
            "venue": raw_row.get("venue") or raw_row.get("place"),
            "address": raw_row.get("address"),
            "description": raw_row.get("description"),
        }
        missing = [key for key, value in required.items() if not isinstance(value, str) or not value.strip()]
        if missing:
            report.rejected_count += 1
            report.errors.append(ImportReportItemErrorDTO(
                row_index=row_index, raw_title=raw_title_str,
                reason=f"Отсутствуют обязательные поля: {', '.join(missing)}",
            ))
            return
        raw_city = required["city"].strip()
        canonical_city = await self.dict_repo.resolve_city_name(raw_city)
        resolved_city = canonical_city or raw_city
        venue = required["venue"].strip()
        address = required["address"].strip()
        description = required["description"].strip()

        # Неполная или противоречивая цена не может стать фактом карточки.
        free_marker = raw_row.get("is_free")
        free_text = str(free_marker).strip().casefold() if free_marker is not None else ""
        if free_text not in ("", "true", "false", "1", "0", "yes", "no", "да", "нет"):
            raise ValueError("Некорректный признак бесплатного входа")
        explicitly_free = free_text in ("true", "1", "yes", "да")
        low, high = raw_row.get("price_min"), raw_row.get("price_max")
        has_low = low is not None and str(low).strip() != ""
        has_high = high is not None and str(high).strip() != ""
        text_price = next((raw_row[key] for key in ("price_text", "price", "cost")
                           if raw_row.get(key) is not None and str(raw_row[key]).strip()), None)
        if has_low and has_high:
            price_min, price_max = int(low), int(high)
            if price_min < 0 or price_max < price_min:
                raise ValueError("Некорректный диапазон цен")
            if explicitly_free and (price_min or price_max):
                raise ValueError("Цена противоречит бесплатному входу")
            is_free = explicitly_free or (price_min == 0 and price_max == 0)
        elif explicitly_free and not has_low and not has_high and text_price is None:
            price_min, price_max, is_free = 0, 0, True
        else:
            if has_low or has_high:
                raise ValueError("Указана только одна граница цены")
            if text_price is None:
                raise ValueError("Цена не указана")
            raw_price_text = str(text_price).strip().casefold()
            if re.match(r"^-\s*\d", raw_price_text):
                raise ValueError("Цена не может быть отрицательной")
            numbers = re.findall(r"\d+", raw_price_text)
            if re.search(r"\d[.,]\d", raw_price_text) or len(numbers) > 2:
                raise ValueError("Некорректная цена")
            if len(numbers) == 1 and re.search(r"\b(?:от|до)\s*\d", raw_price_text):
                raise ValueError("Указана только одна граница цены")
            if len(numbers) == 2 and int(numbers[0]) > int(numbers[1]):
                raise ValueError("Минимальная цена больше максимальной")
            price_min, price_max, is_free = self.norm_service.parse_price_text(text_price)
            if numbers and is_free:
                raise ValueError("Цена противоречит бесплатному входу")
            if not numbers and not is_free:
                raise ValueError("Не удалось разобрать цену")
            if explicitly_free and not is_free:
                raise ValueError("Цена противоречит бесплатному входу")
        if price_max > 2_147_483_647:
            raise ValueError("Цена превышает допустимый диапазон")

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
        if canonical_city is None:
            confidence = min(confidence, 0.7)
            is_disputed = True
            dispute_reason = dispute_reason or ModerationReason.LOW_CONFIDENCE
        event_dict_payload["confidence"] = confidence
        event_dict_payload["is_disputed"] = is_disputed
        event_dict_payload["dispute_reason"] = dispute_reason

        # Статус публикации (с корректной фиксацией отмененных мероприятий)
        raw_status = str(raw_row.get("status") or "").strip().lower()
        if (
            raw_status in ("cancelled", "отменено", "отменен", "canceled")
            or "отменен" in raw_title_str.lower()
            or "отменено" in raw_title_str.lower()
        ):
            event_dict_payload["status"] = EventStatus.CANCELLED
        elif is_disputed:
            event_dict_payload["status"] = EventStatus.DRAFT
            report.flagged_for_moderation_count += 1
        else:
            event_dict_payload["status"] = EventStatus.PUBLISHED

        # 6. Вычисление эмбеддинга
        embedding = await self.emb_service.generate_embedding(f"{title} {description}")
        event_dict_payload["embedding"] = embedding

        # 7. Идемпотентное сохранение / дедупликация
        if replay_record is not None and raw_record.processed_event_id is not None:
            event = await self.event_repo.get_by_id(raw_record.processed_event_id)
            if event is None:
                raise ValueError("Связанное мероприятие не найдено")
            if event.dedup_key != dedup_key:
                raise ValueError("Ключ мероприятия изменился; требуется проверка модератора")
            merged = self.dedup_service.merge_event_fields(event, event_dict_payload)
            for field, value in merged.items():
                setattr(event, field, value)
            if event_dict_payload["status"] == EventStatus.CANCELLED:
                event.status = EventStatus.CANCELLED
            if is_disputed:
                event.is_disputed = True
                event.dispute_reason = dispute_reason
                if event.status != EventStatus.CANCELLED:
                    event.status = EventStatus.DRAFT
            await self.event_repo.session.flush()
            action = "updated"
        else:
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
                        replay_record=record,
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
