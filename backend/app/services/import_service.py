import csv
import hashlib
import inspect
import io
import json
from datetime import datetime, timezone
from typing import Any

from app.core.security import SecurityService
from app.models.enums import EventStatus, ModerationReason, SourceType
from app.schemas.import_mod import ImportReportDTO, ImportReportItemErrorDTO


class ImportService:
    def __init__(self, event_repo, raw_repo, dict_repo, audit_repo, norm_service=None, dedup_service=None, emb_service=None, guardrail_service=None):
        from app.services.deduplication_service import DeduplicationService
        from app.services.normalization_service import NormalizationService

        if emb_service is None:
            from app.services.embedding_service import EmbeddingService
            emb_service = EmbeddingService()
        if guardrail_service is None:
            from app.agent.guardrails import GuardrailService
            guardrail_service = GuardrailService()
        self.event_repo = event_repo
        self.raw_repo = raw_repo
        self.dict_repo = dict_repo
        self.audit_repo = audit_repo
        self.norm_service = norm_service if norm_service is not None else NormalizationService()
        self.dedup_service = dedup_service if dedup_service is not None else DeduplicationService()
        self.emb_service = emb_service
        self.guardrail_service = guardrail_service

    @staticmethod
    def _parse(file_bytes: bytes, filename: str) -> list[dict[str, Any]]:
        text = file_bytes.decode("utf-8-sig")
        if filename.lower().endswith(".csv"):
            reader = csv.DictReader(io.StringIO(text, newline=""))
            if not reader.fieldnames or any(not name or not name.strip() for name in reader.fieldnames):
                raise ValueError("CSV должен содержать заголовки столбцов")
            if len(set(reader.fieldnames)) != len(reader.fieldnames):
                raise ValueError("CSV содержит повторяющиеся заголовки")
            rows = list(reader)
            if any(None in row for row in rows):
                raise ValueError("CSV содержит больше полей, чем заголовков")
        elif filename.lower().endswith(".json"):
            rows = json.loads(text)
        else:
            raise ValueError("Поддерживаются только CSV и JSON")
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise ValueError("Файл должен содержать список объектов")
        return rows

    @staticmethod
    def _report() -> dict[str, Any]:
        return dict(total_received=0, added_count=0, updated_count=0, deduplicated_merged_count=0, flagged_for_moderation_count=0, rejected_count=0, errors=[])

    async def _process(self, raw, report: dict[str, Any], actor_id: str, request_id: str, row_index: int) -> None:
        payload = raw.raw_payload
        try:
            data, confidence, reason = await self.norm_service.normalize_raw_payload(payload, self.dict_repo)
            dedup_key = self.dedup_service.build_dedup_key(data["city"], data["venue"], data["date_start"], data["normalized_title"])
            if raw.event_id is not None:
                linked = await self.event_repo.get_by_id(raw.event_id)
                if linked is not None and linked.dedup_key != dedup_key:
                    raise ValueError("Изменился ключ связанного события; требуется проверка модератора")
        except (ValueError, TypeError, KeyError) as exc:
            report["rejected_count"] += 1
            title = payload.get("title")
            report["errors"].append(ImportReportItemErrorDTO(row_index=row_index, raw_title=str(title) if title is not None else None, reason=str(exc)))
            return
        try:
            description = str(payload.get("description") or "")
            scanner = getattr(self.guardrail_service, "scan_external_data_for_injection", None)
            if scanner is not None:
                suspicious = scanner(description)
                if inspect.isawaitable(suspicious):
                    suspicious = await suspicious
                if not isinstance(suspicious, bool):
                    raise TypeError("scan_external_data_for_injection must return bool")
            else:
                result = self.guardrail_service.check_user_input(description)
                if inspect.isawaitable(result):
                    result = await result
                if not isinstance(result, tuple) or not isinstance(result[0], bool):
                    raise TypeError("check_user_input must return (bool, message)")
                suspicious = not result[0]
            if suspicious:
                reason = ModerationReason.PROMPT_INJECTION_SUSPECTED
            raw_status = str(payload.get("status") or "").strip().casefold().replace("ё", "е")
            cancelled = raw_status in {"cancelled", "canceled", "отменено", "отменен", "отменена"}
            data.update(source_type=raw.source_type, source_hash=raw.source_hash, source_url=raw.source_url,
                        confidence=confidence, verified_at=datetime.now(timezone.utc),
                        is_disputed=reason is not None, dispute_reason=reason.value if reason else None,
                        status=EventStatus.CANCELLED if cancelled else EventStatus.DRAFT if reason else EventStatus.PUBLISHED)
            data["dedup_key"] = dedup_key
            existing = await self.event_repo.get_by_dedup_key(data["dedup_key"])
            if not existing:
                data["embedding"] = await self.emb_service.generate_embedding(f"{data['title']} {data['description']}")
            event, action = await self.event_repo.create_or_update_event(data, raw.id)
            await self.audit_repo.log_change(request_id, actor_id, action, "event", event.id, {"source_hash": raw.source_hash})
            field = {"added": "added_count", "updated": "updated_count", "merged": "deduplicated_merged_count"}[action]
            report[field] += 1
            if reason is not None:
                report["flagged_for_moderation_count"] += 1
        except Exception:
            # Database and integration failures must abort the surrounding transaction.
            raise

    async def import_file(self, file_bytes: bytes, filename: str, actor_id: str, request_id: str) -> ImportReportDTO:
        rows = self._parse(file_bytes, filename)
        report = self._report()
        report["total_received"] = len(rows)
        for index, row in enumerate(rows, 1):
            missing_identity = [name for name in ("source_url", "title", "date_start") if not str(row.get(name) or "").strip()]
            url = str(row.get("source_url") or "")
            if missing_identity:
                # Retain malformed input for replay without collapsing unrelated rows
                # onto the hash of three empty identity fields.
                canonical = json.dumps(row, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
                source_hash = hashlib.sha256(("invalid:" + canonical).encode("utf-8")).hexdigest()
            else:
                source_hash = SecurityService.compute_source_hash(url, str(row.get("title") or ""), str(row.get("date_start") or ""))
            existing_raw = await self.raw_repo.get_by_hash(source_hash)
            if existing_raw:
                if missing_identity:
                    await self._process(existing_raw, report, actor_id, request_id, index)
                continue
            raw = await self.raw_repo.save_raw_record(SourceType.IMPORT, url, source_hash, row, actor_id)
            if raw is None:  # Concurrent importer already stored this source.
                if missing_identity:
                    raw = await self.raw_repo.get_by_hash(source_hash)
                    if raw is not None:
                        await self._process(raw, report, actor_id, request_id, index)
                continue
            await self._process(raw, report, actor_id, request_id, index)
        return ImportReportDTO(**report)

    async def replay_all_normalizations(self, actor_id: str, request_id: str) -> ImportReportDTO:
        report = self._report()
        async for batch in self.raw_repo.list_all_for_replay():
            for raw in batch:
                report["total_received"] += 1
                await self._process(raw, report, actor_id, request_id, report["total_received"])
        return ImportReportDTO(**report)
