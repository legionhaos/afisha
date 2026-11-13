import hashlib
from datetime import datetime, timezone
from typing import Any

from app.models.event import Event


class DeduplicationService:
    def build_dedup_key(
        self, city: str, venue: str, date_start: datetime, normalized_title: str
    ) -> str:
        canonical = (
            f"{city.lower()}|{normalized_title}|"
            f"{date_start.strftime('%Y-%m-%d %H:%M')}|{venue.lower()}"
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def merge_event_fields(self, existing: Event, incoming: dict[str, Any]) -> dict[str, Any]:
        description = incoming.get("description") or ""
        current_description = existing.description or ""
        return {
            "description": max((current_description, description), key=len),
            "tags": list(dict.fromkeys([*(existing.tags or []), *(incoming.get("tags") or [])])),
            "org_link": existing.org_link or incoming.get("org_link"),
            "verified_at": datetime.now(timezone.utc),
        }


deduplication_service = DeduplicationService()
