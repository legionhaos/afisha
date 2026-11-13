import json
from datetime import datetime
from decimal import Decimal
from typing import Any, Callable
from uuid import UUID, uuid4

from langchain_core.tools import BaseTool, tool
from pydantic import BaseModel, Field

from app.models.enums import EventCategory, EventStatus
from app.repositories.dictionary_repo import DictionaryRepository
from app.repositories.event_repo import EventRepository
from app.repositories.feedback_repo import FeedbackRepository
from app.repositories.subscription_repo import SubscriptionRepository
from app.schemas.event import EventSearchFilterDTO
from app.services.catalog_service import CatalogService
from app.services.embedding_service import EmbeddingService
from app.agent.guardrails import GuardrailService
from app.services.normalization_service import NormalizationService


class SearchEventsInput(BaseModel):
    query_text: str | None = Field(default=None, description="Текстовый поисковый запрос (например 'джаз', 'симфонический оркестр')")
    city: str | None = Field(default=None, description="Город проведения (Уфа, Стерлитамак, Салават и т.д.)")
    category: str | None = Field(default=None, description="Категория: concert, theater, exhibition, festival, cinema, excursion, other")
    date_preset: str | None = Field(default=None, description="Пресет даты: today, tomorrow, weekend, week")
    date_from: str | None = Field(default=None, description="Дата начала в формате ISO или YYYY-MM-DD")
    date_to: str | None = Field(default=None, description="Дата окончания в формате ISO или YYYY-MM-DD")
    price_max: int | None = Field(default=None, description="Максимальная цена билета в рублях")
    is_free: bool | None = Field(default=None, description="Только бесплатные мероприятия")
    age_limit: int | None = Field(default=None, description="Возрастной ценз (0, 6, 12, 16, 18)")
    max_duration_min: int | None = Field(default=None, description="Максимальная длительность в минутах")
    language: str | None = Field(default=None, description="Язык проведения (русский, башкирский)")


class GetEventInput(BaseModel):
    event_id: str = Field(..., description="UUID идентификатор мероприятия")


class FindSimilarInput(BaseModel):
    event_id: str = Field(..., description="UUID базового мероприятия")
    city: str | None = Field(default=None, description="Опциональный город для поиска похожих")
    date_from: str | None = Field(default=None, description="Нижняя граница даты")
    date_to: str | None = Field(default=None, description="Верхняя граница даты")


class GetVenueScheduleInput(BaseModel):
    venue: str = Field(..., description="Название площадки (театр, ДК, музей)")
    date_from: str = Field(..., description="Начало периода (YYYY-MM-DD)")
    date_to: str = Field(..., description="Конец периода (YYYY-MM-DD)")


class SubscribeInput(BaseModel):
    city: str = Field(..., description="Город подписки")
    category: str | None = Field(default=None, description="Категория мероприятий")
    period_type: str = Field(default="all", description="Периодичность: weekend, all")


class SaveFeedbackInput(BaseModel):
    message_text: str = Field(..., description="Текст обращения организатора или жителя")
    event_id: str | None = Field(default=None, description="Опциональный UUID мероприятия")


class AgentToolsFactory:
    """Фабрика создания инструментов агента с контекстом текущего запроса."""

    def __init__(
        self,
        event_repo: EventRepository,
        dict_repo: DictionaryRepository,
        sub_repo: SubscriptionRepository,
        feedback_repo: FeedbackRepository,
        catalog_service: CatalogService,
        user_identifier: str,
        confirmed_action_id: str | None = None,
        on_card_fetched: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self.event_repo = event_repo
        self.dict_repo = dict_repo
        self.sub_repo = sub_repo
        self.feedback_repo = feedback_repo
        self.catalog_service = catalog_service
        self.user_identifier = user_identifier
        self.confirmed_action_id = confirmed_action_id
        self.on_card_fetched = on_card_fetched
        self.norm = NormalizationService()

    def create_tools(self) -> list[BaseTool]:
        """Возвращает список 6 инструментов по контракту раздела 7.2 ТЗ."""

        @tool("search_events", args_schema=SearchEventsInput)
        async def search_events_tool(
            query_text: str | None = None,
            city: str | None = None,
            category: str | None = None,
            date_preset: str | None = None,
            date_from: str | None = None,
            date_to: str | None = None,
            price_max: int | None = None,
            is_free: bool | None = None,
            age_limit: int | None = None,
            max_duration_min: int | None = None,
            language: str | None = None,
        ) -> str:
            """Поиск культурных мероприятий по фильтрам (город, дата, цена, возраст, категория)."""
            try:
                # Преобразование категории
                cat_enum = None
                if category:
                    try:
                        cat_enum = EventCategory(category.lower())
                    except ValueError:
                        pass

                parsed_df = self.norm.parse_date_to_yekaterinburg(date_from) if date_from else None
                parsed_dt = self.norm.parse_date_to_yekaterinburg(date_to) if date_to else None

                filters = EventSearchFilterDTO(
                    query_text=query_text,
                    city=city,
                    category=cat_enum,
                    date_preset=date_preset if date_preset in ["today", "tomorrow", "weekend", "week"] else None,
                    date_from=parsed_df,
                    date_to=parsed_dt,
                    price_max=price_max,
                    is_free=is_free,
                    age_limit_max=age_limit,
                    max_duration_min=max_duration_min,
                    language=language,
                    page=1,
                    page_size=5,
                )

                response = await self.catalog_service.search_catalog(filters)

                results = []
                for item in response.items:
                    if item.status != EventStatus.PUBLISHED:
                        continue
                    card_dict = item.model_dump(mode="json")
                    if self.on_card_fetched:
                        self.on_card_fetched(card_dict)
                    results.append(GuardrailService().sanitize_untrusted_event_data({
                        "id": str(item.id),
                        "title": item.title,
                        "category": item.category.value,
                        "date_start": item.date_start.isoformat(),
                        "duration_min": item.duration_min,
                        "city": item.city,
                        "venue": item.venue,
                        "address": item.address,
                        "price_min": item.price_min,
                        "price_max": item.price_max,
                        "is_free": item.is_free,
                        "age_limit": item.age_limit,
                        "language": item.language,
                        "org_link": item.org_link,
                        "source_url": item.source_url,
                        "description": item.description,
                    }))

                if not results and response.empty_explanation:
                    explanation = GuardrailService().sanitize_untrusted_event_data({
                        "message": response.empty_explanation.message,
                        "blocking_constraints": response.empty_explanation.blocking_constraints,
                        "suggested_relaxations": response.empty_explanation.suggested_relaxations,
                    })
                    explanation.pop("description", None)
                    return json.dumps({"count": 0, **explanation}, ensure_ascii=False)

                return json.dumps({"count": len(results), "events": results}, ensure_ascii=False)
            except Exception:
                return json.dumps({"error": "SEARCH_FAILED"})

        @tool("get_event", args_schema=GetEventInput)
        async def get_event_tool(event_id: str) -> str:
            """Получение полной информации о мероприятии по UUID (включая проверку статуса отмены)."""
            try:
                card = await self.catalog_service.get_event_card(UUID(event_id))
                if card.status not in (EventStatus.PUBLISHED, EventStatus.CANCELLED):
                    return json.dumps({"error": "EVENT_NOT_FOUND"})
                card_dict = card.model_dump(mode="json")
                if self.on_card_fetched:
                    self.on_card_fetched(card_dict)

                res = GuardrailService().sanitize_untrusted_event_data(card.model_dump(mode="json"))
                return json.dumps(res, ensure_ascii=False)
            except Exception:
                return json.dumps({"error": "EVENT_LOOKUP_FAILED"})

        @tool("find_similar", args_schema=FindSimilarInput)
        async def find_similar_tool(
            event_id: str,
            city: str | None = None,
            date_from: str | None = None,
            date_to: str | None = None,
        ) -> str:
            """Поиск похожих мероприятий (той же категории или семантически близких)."""
            try:
                base_event = await self.event_repo.get_by_id(UUID(event_id))
                if not base_event or base_event.status not in (EventStatus.PUBLISHED, EventStatus.CANCELLED):
                    return json.dumps({"error": "EVENT_NOT_FOUND"})

                df = self.norm.parse_date_to_yekaterinburg(date_from) if date_from else None
                dt = self.norm.parse_date_to_yekaterinburg(date_to) if date_to else None

                items = await self.event_repo.find_similar_events(base_event, city=city, date_from=df, date_to=dt, limit=4)
                results = []
                for item in items:
                    if item.status != EventStatus.PUBLISHED:
                        continue
                    card = self.catalog_service._to_card_dto(item)
                    card_dict = card.model_dump(mode="json")
                    if self.on_card_fetched:
                        self.on_card_fetched(card_dict)
                    results.append(GuardrailService().sanitize_untrusted_event_data({
                        "id": str(item.id),
                        "title": item.title,
                        "category": item.category.value,
                        "date_start": item.date_start.isoformat(),
                        "city": item.city,
                        "venue": item.venue,
                        "price_min": item.price_min,
                        "price_max": item.price_max,
                        "is_free": item.is_free,
                        "source_url": item.source_url,
                    }))

                return json.dumps({"count": len(results), "similar_events": results}, ensure_ascii=False)
            except Exception:
                return json.dumps({"error": "SIMILAR_SEARCH_FAILED"})

        @tool("get_venue_schedule", args_schema=GetVenueScheduleInput)
        async def get_venue_schedule_tool(venue: str, date_from: str, date_to: str) -> str:
            """Проверка расписания площадки за период (театр, ДК, филармония)."""
            try:
                df = self.norm.parse_date_to_yekaterinburg(date_from)
                dt = self.norm.parse_date_to_yekaterinburg(date_to)
                items = await self.event_repo.get_venue_schedule(venue, df, dt)

                results = []
                for item in items:
                    if item.status != EventStatus.PUBLISHED:
                        continue
                    card = self.catalog_service._to_card_dto(item)
                    card_dict = card.model_dump(mode="json")
                    if self.on_card_fetched:
                        self.on_card_fetched(card_dict)
                    results.append(GuardrailService().sanitize_untrusted_event_data({
                        "id": str(item.id),
                        "title": item.title,
                        "date_start": item.date_start.isoformat(),
                        "duration_min": item.duration_min,
                        "venue": item.venue,
                        "price_min": item.price_min,
                    }))

                safe_venue = GuardrailService().sanitize_untrusted_event_data({"venue": venue})["venue"]
                return json.dumps({"venue": safe_venue, "events_count": len(results), "schedule": results}, ensure_ascii=False)
            except Exception:
                return json.dumps({"error": "SCHEDULE_FAILED"})

        @tool("subscribe", args_schema=SubscribeInput)
        async def subscribe_tool(city: str, category: str | None = None, period_type: str = "all") -> str:
            """Оформление или перенос подписки. Требует обязательного подтверждения пользователя!"""
            try:
                cat_enum = None
                if category:
                    try:
                        cat_enum = EventCategory(category.lower())
                    except ValueError:
                        pass

                # Проверка двухфазного подтверждения
                action_id = f"sub_{uuid4().hex[:8]}"
                if not self.confirmed_action_id:
                    cat_name = cat_enum.value if cat_enum else "все категории"
                    return json.dumps({
                        "status": "CONFIRMATION_REQUIRED",
                        "pending_action_id": action_id,
                        "summary": f"Оформить подписку на культурные события в г. {city} ({cat_name})?",
                    }, ensure_ascii=False)

                sub = await self.sub_repo.upsert_subscription(
                    user_identifier=self.user_identifier,
                    telegram_chat_id=None,
                    city=city,
                    category=cat_enum,
                    period_type=period_type,
                )
                return json.dumps({
                    "status": "SUCCESS",
                    "subscription_id": str(sub.id),
                    "message": f"Подписка на г. {city} успешно активирована!",
                }, ensure_ascii=False)
            except Exception as e:
                return json.dumps({"error": f"Ошибка оформления подписки: {str(e)}"}, ensure_ascii=False)

        @tool("save_feedback", args_schema=SaveFeedbackInput)
        async def save_feedback_tool(message_text: str, event_id: str | None = None) -> str:
            """Отправка обращения или уточнения организаторам. Требует подтверждения пользователя!"""
            try:
                action_id = f"fdbk_{uuid4().hex[:8]}"
                if not self.confirmed_action_id:
                    return json.dumps({
                        "status": "CONFIRMATION_REQUIRED",
                        "pending_action_id": action_id,
                        "summary": f"Отправить сообщение организаторам: '{message_text[:100]}...'?",
                    }, ensure_ascii=False)

                eid = UUID(event_id) if event_id else None
                ticket = await self.feedback_repo.create_feedback(
                    sender_identifier=self.user_identifier,
                    message_text=message_text,
                    event_id=eid,
                )
                return json.dumps({
                    "status": "SUCCESS",
                    "ticket_id": str(ticket.id),
                    "message": "Обращение успешно зарегистрировано и передано модераторам.",
                }, ensure_ascii=False)
            except Exception as e:
                return json.dumps({"error": f"Ошибка отправки обращения: {str(e)}"}, ensure_ascii=False)

        return [
            search_events_tool,
            get_event_tool,
            find_similar_tool,
            get_venue_schedule_tool,
            subscribe_tool,
            save_feedback_tool,
        ]
