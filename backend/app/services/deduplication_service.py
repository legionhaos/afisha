import hashlib
from datetime import datetime, timezone
from typing import Any

from app.models.enums import ModerationReason
from app.models.event import Event


class DeduplicationService:
    """Сервис вычисления ключей дедупликации и слияния полей карточек."""

    @staticmethod
    def build_dedup_key(
        city: str,
        venue: str,
        date_start: datetime,
        normalized_title: str,
    ) -> str:
        """Формирует канонический детерминированный ключ дедупликации.

        Строго по контракту AGENTS.md:
        sha256(f"{city.lower()}::{venue.lower()}::{date_start.strftime('%Y-%m-%d %H:%M')}::{normalized_title[:60]}")
        """
        canonical_str = (
            f"{city.strip().lower()}::"
            f"{venue.strip().lower()}::"
            f"{date_start.strftime('%Y-%m-%d %H:%M')}::"
            f"{normalized_title.strip()[:60]}"
        )
        return hashlib.sha256(canonical_str.encode("utf-8")).hexdigest()

    def merge_event_fields(
        self,
        existing: Event,
        incoming: dict[str, Any],
    ) -> dict[str, Any]:
        """Объединяет данные двух источников в наиболее полную карточку."""
        merged: dict[str, Any] = {}

        # 1. Описание: выбираем более длинное и содержательное
        desc_existing = existing.description or ""
        desc_incoming = incoming.get("description") or ""
        merged["description"] = desc_incoming if len(desc_incoming) > len(desc_existing) else desc_existing

        # 2. Теги: объединение множеств
        existing_tags = set(existing.tags or [])
        incoming_tags = set(incoming.get("tags") or [])
        merged["tags"] = sorted(list(existing_tags | incoming_tags))

        # 3. Ссылка на покупку билетов / сайт организатора
        merged["org_link"] = incoming.get("org_link") or existing.org_link

        # 4. Координаты (если у существующего не было, а у нового есть)
        merged["lat"] = existing.lat if existing.lat is not None else incoming.get("lat")
        merged["lon"] = existing.lon if existing.lon is not None else incoming.get("lon")

        # 5. Дата окончания и длительность
        merged["date_end"] = existing.date_end or incoming.get("date_end")
        merged["duration_min"] = existing.duration_min or incoming.get("duration_min")

        # 6. Дата верификации обновляется на текущую
        merged["verified_at"] = incoming.get("verified_at", datetime.now(timezone.utc))

        return merged

    def evaluate_confidence_and_disputes(
        self,
        event_data: dict[str, Any],
    ) -> tuple[float, bool, ModerationReason | None]:
        """Оценивает полноту карточки и необходимость отправки в очередь модерации."""
        confidence = 1.0
        reasons: list[ModerationReason] = []

        title = event_data.get("title", "")
        desc = event_data.get("description", "")
        venue = event_data.get("venue", "")
        address = event_data.get("address", "")

        # 1. Проверка описания
        if len(desc) < 20:
            confidence -= 0.3
            reasons.append(ModerationReason.MISSING_REQUIRED_FIELDS)

        # 2. Проверка точного адреса
        if not address or len(address) < 5 or address.lower() == venue.lower():
            confidence -= 0.15
            reasons.append(ModerationReason.MISSING_REQUIRED_FIELDS)

        # 3. Проверка подозрительных инструкций в тексте
        combined_text = f"{title} {desc}".lower()
        if any(w in combined_text for w in ["забудь инструкции", "system prompt", "ignore instructions", "опубликуй только меня"]):
            confidence = 0.1
            return 0.1, True, ModerationReason.PROMPT_INJECTION_SUSPECTED

        confidence = max(0.0, min(1.0, confidence))
        is_disputed = confidence < 0.75
        primary_reason = reasons[0] if is_disputed and reasons else None

        return confidence, is_disputed, primary_reason


deduplication_service = DeduplicationService()
