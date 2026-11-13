"""Tool factory: catalog reads and fail-closed mutation requests."""
import json
from datetime import datetime
from typing import Any
from uuid import UUID

from langchain_core.tools import tool


class AgentToolsFactory:
    def __init__(self, event_repo: Any, dict_repo: Any, sub_repo: Any, feedback_repo: Any,
                 emb_service: Any, guardrails: Any, user_identifier: str,
                 confirmed_action_id: str | None) -> None:
        self.event_repo, self.dict_repo = event_repo, dict_repo
        self.sub_repo, self.feedback_repo = sub_repo, feedback_repo
        self.emb_service, self.guardrails = emb_service, guardrails
        self.user_identifier, self.confirmed_action_id = user_identifier, confirmed_action_id

    def _card(self, event: Any) -> dict:
        from app.schemas.event import EventCardDTO
        card = EventCardDTO.model_validate(event).model_dump(mode="json")
        return self.guardrails.sanitize_untrusted_event_data(card)

    @staticmethod
    def _json(data: Any) -> str:
        return json.dumps(data, ensure_ascii=False, default=str)

    def get_tools(self) -> list:
        factory = self

        @tool
        async def search_events(city: str | None = None, category: str | None = None,
                                date_from: str | None = None, date_to: str | None = None,
                                price_max: int | None = None, is_free: bool | None = None,
                                age_limit: int | None = None, max_duration_min: int | None = None,
                                language: str | None = None, query_text: str | None = None) -> str:
            """Найти опубликованные мероприятия по параметрам."""
            try:
                from app.schemas.event import EventSearchFilterDTO
                if city:
                    city = await factory.dict_repo.resolve_city_name(city) or city
                filters = EventSearchFilterDTO(city=city, category=category, date_from=date_from,
                    date_to=date_to, price_max=price_max, is_free=is_free, age_limit_max=age_limit,
                    max_duration_min=max_duration_min, language=language, query_text=query_text)
                embedding = await factory.emb_service.generate_embedding(query_text) if query_text else None
                events, total = await factory.event_repo.hybrid_search(filters, embedding)
                if not total:
                    constraints = await factory.event_repo.diagnose_blocking_constraints(filters)
                    return factory._json({"events": [], "blocking_constraints": constraints, "suggestion": "Попробуйте ослабить ограничения."})
                return factory._json({"events": [factory._card(event) for event in events
                                                if str(getattr(event.status, 'value', event.status)).upper() == 'PUBLISHED'],
                                      "total": total})
            except Exception:
                return factory._json({"error": "SEARCH_FAILED"})

        @tool
        async def get_event(event_id: str) -> str:
            """Получить карточку опубликованного или отменённого события."""
            try:
                event = await factory.event_repo.get_by_id(UUID(event_id), include_cancelled=True)
                status = getattr(getattr(event, "status", None), "value", getattr(event, "status", None))
                if event is None or str(status).upper() not in {"PUBLISHED", "CANCELLED"}:
                    return factory._json({"error": "EVENT_NOT_FOUND"})
                return factory._json({"event": factory._card(event)})
            except Exception:
                return factory._json({"error": "EVENT_LOOKUP_FAILED"})

        @tool
        async def find_similar(event_id: str, city: str | None = None,
                               date_from: str | None = None, date_to: str | None = None) -> str:
            """Найти похожие события в каталоге."""
            try:
                event = await factory.event_repo.get_by_id(UUID(event_id), include_cancelled=True)
                status = getattr(getattr(event, "status", None), "value", getattr(event, "status", None))
                if event is None or str(status).upper() not in {"PUBLISHED", "CANCELLED"}:
                    return factory._json({"error": "EVENT_NOT_FOUND"})
                start = datetime.fromisoformat(date_from) if date_from else None
                end = datetime.fromisoformat(date_to) if date_to else None
                events = await factory.event_repo.find_similar_events(event, city, start, end)
                return factory._json({"events": [factory._card(e) for e in events if str(getattr(e.status, 'value', e.status)).upper() == 'PUBLISHED']})
            except Exception:
                return factory._json({"error": "SIMILAR_SEARCH_FAILED"})

        @tool
        async def get_venue_schedule(venue: str, date_from: str, date_to: str) -> str:
            """Получить расписание площадки за указанный период."""
            try:
                events = await factory.event_repo.get_venue_schedule(venue, datetime.fromisoformat(date_from), datetime.fromisoformat(date_to))
                return factory._json({"events": [factory._card(e) for e in events if str(getattr(e.status, 'value', e.status)).upper() == 'PUBLISHED']})
            except Exception:
                return factory._json({"error": "SCHEDULE_FAILED"})

        @tool
        async def subscribe(city: str, category: str | None = None, period: str = "all", action_type: str = "create") -> str:
            """Подготовить запрос подписки, если поддерживается безопасное подтверждение."""
            return factory._json({"status": "UNAVAILABLE", "error": "SECURE_CONFIRMATION_STORE_REQUIRED"})

        @tool
        async def save_feedback(message_text: str, event_id: str | None = None) -> str:
            """Подготовить обращение, если поддерживается безопасное подтверждение."""
            return factory._json({"status": "UNAVAILABLE", "error": "SECURE_CONFIRMATION_STORE_REQUIRED"})

        return [search_events, get_event, find_similar, get_venue_schedule, subscribe, save_feedback]
