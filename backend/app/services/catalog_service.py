from datetime import datetime, time, timedelta
from typing import Any
from uuid import UUID

from app.core.exceptions import EventNotFoundError
from app.models.enums import EventStatus
from app.repositories.dictionary_repo import DictionaryRepository
from app.repositories.event_repo import EventRepository
from app.schemas.event import (
    EmptyResultExplanationDTO,
    EventCardDTO,
    EventSearchFilterDTO,
    EventSourceDTO,
    PaginatedEventsResponseDTO,
)
from app.services.embedding_service import EmbeddingService
from app.services.normalization_service import YEKT_TZ


class CatalogService:
    """Сервис обслуживания каталога, фильтрации и карточек мероприятий."""

    def __init__(
        self,
        event_repo: EventRepository,
        dict_repo: DictionaryRepository,
        emb_service: EmbeddingService | None = None,
    ) -> None:
        self.event_repo = event_repo
        self.dict_repo = dict_repo
        self.emb_service = emb_service or EmbeddingService()

    def _apply_date_preset(self, filters: EventSearchFilterDTO) -> None:
        """Преобразует пресеты дат ('today', 'tomorrow', 'weekend', 'week') в границы UTC+5."""
        if not filters.date_preset:
            return

        now_yekt = datetime.now(YEKT_TZ)
        today_start = datetime.combine(now_yekt.date(), time.min, tzinfo=YEKT_TZ)
        today_end = datetime.combine(now_yekt.date(), time.max, tzinfo=YEKT_TZ)

        if filters.date_preset == "today":
            filters.date_from = today_start
            filters.date_to = today_end
        elif filters.date_preset == "tomorrow":
            filters.date_from = today_start + timedelta(days=1)
            filters.date_to = today_end + timedelta(days=1)
        elif filters.date_preset == "weekend":
            # Ближайшие суббота и воскресенье
            days_until_sat = (5 - now_yekt.weekday()) % 7
            sat_start = today_start + timedelta(days=days_until_sat)
            sun_end = sat_start + timedelta(days=1, hours=23, minutes=59, seconds=59)
            filters.date_from = sat_start
            filters.date_to = sun_end
        elif filters.date_preset == "week":
            filters.date_from = today_start
            filters.date_to = today_end + timedelta(days=7)

    async def search_catalog(self, filters: EventSearchFilterDTO) -> PaginatedEventsResponseDTO:
        """Поиск по каталогу с гибридным ранжированием и диагностикой пустой выдачи."""
        self._apply_date_preset(filters)

        # Исправление опечатки в городе
        if filters.city:
            resolved_city = await self.dict_repo.resolve_city_name(filters.city)
            if resolved_city:
                filters.city = resolved_city

        # Генерация эмбеддинга для гибридного поиска
        query_embedding = None
        # Lexical matching is a mandatory gate; avoid sending private user queries
        # to the embedding provider until semantic retrieval is calibrated.

        items, total = await self.event_repo.hybrid_search(filters, query_embedding)

        empty_explanation = None
        if total == 0:
            blocking = await self.event_repo.diagnose_blocking_constraints(filters)
            empty_explanation = EmptyResultExplanationDTO(
                is_empty=True,
                message="По вашему запросу ничего не найдено.",
                blocking_constraints=blocking,
                suggested_relaxations=[
                    "Попробуйте расширить диапазон дат или выбрать 'Все дни'",
                    "Увеличьте максимальную цену билета или снимите ограничение бюджета",
                    "Проверьте правильность написания названия города или площадки",
                ],
            )

        cards = [self._to_card_dto(item) for item in items]

        return PaginatedEventsResponseDTO(
            items=cards,
            total=total,
            page=filters.page,
            page_size=filters.page_size,
            empty_explanation=empty_explanation,
        )

    async def get_event_card(self, event_id: UUID) -> EventCardDTO:
        """Получает карточку события (включая отмененные по прямой ссылке с пометкой)."""
        event = await self.event_repo.get_by_id(event_id, include_cancelled=True)
        if not event:
            raise EventNotFoundError(event_id=str(event_id))

        return self._to_card_dto(event)

    def _to_card_dto(self, event: Any) -> EventCardDTO:
        """Конвертирует ORM-модель Event в DTO с заполнением cancelled_badge."""
        cancelled_badge = None
        if event.status == EventStatus.CANCELLED:
            cancelled_badge = "⚠️ Внимание: мероприятие отменено организатором"

        sources_dto = [
            EventSourceDTO(
                source_url=s.source_url,
                source_type=s.source_type,
                merged_at=s.merged_at,
            )
            for s in getattr(event, "sources", [])
        ]

        return EventCardDTO(
            id=event.id,
            title=event.title,
            normalized_title=event.normalized_title,
            category=event.category,
            tags=event.tags or [],
            date_start=event.date_start,
            date_end=event.date_end,
            duration_min=event.duration_min,
            city=event.city,
            venue=event.venue,
            address=event.address,
            lat=event.lat,
            lon=event.lon,
            description=event.description,
            price_min=event.price_min,
            price_max=event.price_max,
            is_free=event.is_free,
            age_limit=event.age_limit,
            language=event.language,
            org_link=event.org_link,
            source_url=event.source_url,
            status=event.status,
            cancelled_badge=cancelled_badge,
            confidence=float(event.confidence) if event.confidence is not None else 1.0,
            is_disputed=event.is_disputed,
            dispute_reason=event.dispute_reason,
            verified_at=event.verified_at,
            sources=sources_dto,
        )
