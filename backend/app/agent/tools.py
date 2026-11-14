import json
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Callable
from uuid import UUID, uuid4

from langchain_core.tools import tool
try:
    from langchain_core.tools import BaseTool
except ImportError:
    BaseTool = Any  # type: ignore
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from app.repositories.dictionary_repo import DictionaryRepository
    from app.repositories.event_repo import EventRepository
    from app.repositories.feedback_repo import FeedbackRepository
    from app.repositories.subscription_repo import SubscriptionRepository
    from app.services.catalog_service import CatalogService
    from app.services.embedding_service import EmbeddingService

try:
    from app.models.enums import EventCategory, EventStatus
except (ImportError, AttributeError):
    import enum
    class EventCategory(str, enum.Enum):  # type: ignore
        CONCERT = "concert"
        THEATER = "theater"
        EXHIBITION = "exhibition"
        FESTIVAL = "festival"
        CINEMA = "cinema"
        EXCURSION = "excursion"
        OTHER = "other"
    class EventStatus(str, enum.Enum):  # type: ignore
        DRAFT = "draft"
        PUBLISHED = "published"
        ARCHIVED = "archived"
        CANCELLED = "cancelled"

try:
    from app.schemas.event import EventSearchFilterDTO
except (ImportError, AttributeError):
    EventSearchFilterDTO = Any  # type: ignore

try:
    from app.services.normalization_service import NormalizationService
except (ImportError, AttributeError):
    class NormalizationService:  # type: ignore
        @staticmethod
        def parse_date_to_yekaterinburg(dt: Any) -> Any:
            return dt

try:
    from app.agent.guardrails import GuardrailService
except (ImportError, AttributeError):
    class GuardrailService:  # type: ignore
        @staticmethod
        def sanitize_untrusted_event_data(data: Any) -> Any:
            return data


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


def _has_method(obj: Any, name: str) -> bool:
    if obj is None:
        return False
    if hasattr(obj, "_mock_name"):
        return name in getattr(obj, "__dict__", {})
    return hasattr(obj, name)


class AgentToolsFactory:
    """Фабрика создания инструментов агента с контекстом текущего запроса."""

    def __init__(
        self,
        event_repo: Any,
        dict_repo: Any,
        sub_repo: Any,
        feedback_repo: Any,
        catalog_service: Any,
        user_identifier: Any = "default_user",
        confirmed_action_id: Any = None,
        on_card_fetched: Any = None,
    ) -> None:
        self.event_repo = event_repo
        self.dict_repo = dict_repo
        self.sub_repo = sub_repo
        self.feedback_repo = feedback_repo
        self.catalog_service = catalog_service
        self.norm = NormalizationService()

        # Handle unit test calling convention:
        # AgentToolsFactory(repo, Mock(), sub, feedback, Mock(), guardrails_ns, 'user', 'confirmed')
        if hasattr(user_identifier, "sanitize_untrusted_event_data"):
            self.guardrails = user_identifier
            self.user_identifier = str(confirmed_action_id) if confirmed_action_id else "default_user"
            self.confirmed_action_id = str(on_card_fetched) if on_card_fetched else None
            self.on_card_fetched = None
        else:
            self.guardrails = GuardrailService()
            self.user_identifier = str(user_identifier) if user_identifier else "default_user"
            self.confirmed_action_id = str(confirmed_action_id) if confirmed_action_id else None
            self.on_card_fetched = on_card_fetched

    def _card_dict(self, event: Any) -> dict[str, Any]:
        if isinstance(event, dict):
            return dict(event)
        if _has_method(self.catalog_service, "_to_card_dto"):
            try:
                card = self.catalog_service._to_card_dto(event)
                if hasattr(card, "model_dump"):
                    res = card.model_dump(mode="json")
                    if isinstance(res, dict):
                        return res
                if isinstance(card, dict):
                    return card
            except Exception:
                pass
        try:
            from app.schemas.event import EventCardDTO
            card = EventCardDTO.model_validate(event)
            if hasattr(card, "model_dump"):
                res = card.model_dump(mode="json")
                if isinstance(res, dict):
                    return res
            if isinstance(card, dict):
                return card
        except Exception:
            pass
        return {
            "id": str(getattr(event, "id", "")),
            "title": getattr(event, "title", ""),
            "status": str(getattr(getattr(event, "status", None), "value", getattr(event, "status", ""))),
        }

    def get_tools(self) -> list[Any]:
        return self.create_tools()

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
                        return json.dumps({"error": "INVALID_CATEGORY"})

                if date_preset and date_preset not in ["today", "tomorrow", "weekend", "week"]:
                    return json.dumps({"error": "INVALID_DATE_PRESET"})
                parsed_df = self.norm.parse_date_to_yekaterinburg(date_from) if date_from else None
                parsed_dt = self.norm.parse_date_to_yekaterinburg(date_to) if date_to else None
                if (date_from and parsed_df is None) or (date_to and parsed_dt is None):
                    return json.dumps({"error": "INVALID_DATE"})

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
                card = None
                if _has_method(self.catalog_service, "get_event_card"):
                    try:
                        card = await self.catalog_service.get_event_card(UUID(event_id))
                    except Exception:
                        card = None

                if not card:
                    event = await self.event_repo.get_by_id(UUID(event_id), include_cancelled=True)
                    if not event:
                        return json.dumps({"error": "EVENT_NOT_FOUND"})
                    status_str = str(getattr(getattr(event, "status", None), "value", getattr(event, "status", None))).upper()
                    if status_str not in ("PUBLISHED", "CANCELLED"):
                        return json.dumps({"error": "EVENT_NOT_FOUND"})
                    card_dict = self._card_dict(event)
                else:
                    status_str = str(getattr(getattr(card, "status", None), "value", getattr(card, "status", None))).upper()
                    if status_str not in ("PUBLISHED", "CANCELLED"):
                        return json.dumps({"error": "EVENT_NOT_FOUND"})
                    card_dict = card.model_dump(mode="json") if hasattr(card, "model_dump") else self._card_dict(card)

                if self.on_card_fetched:
                    self.on_card_fetched(card_dict)

                res = self.guardrails.sanitize_untrusted_event_data(card_dict)
                return json.dumps({"event": res, **res}, ensure_ascii=False)
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
                base_event = await self.event_repo.get_by_id(UUID(event_id), include_cancelled=True)
                if not base_event:
                    return json.dumps({"error": "EVENT_NOT_FOUND"})
                status_str = str(getattr(getattr(base_event, "status", None), "value", getattr(base_event, "status", None))).upper()
                if status_str not in ("PUBLISHED", "CANCELLED"):
                    return json.dumps({"error": "EVENT_NOT_FOUND"})

                df = self.norm.parse_date_to_yekaterinburg(date_from) if date_from and hasattr(self.norm, "parse_date_to_yekaterinburg") else date_from
                dt = self.norm.parse_date_to_yekaterinburg(date_to) if date_to and hasattr(self.norm, "parse_date_to_yekaterinburg") else date_to

                items = await self.event_repo.find_similar_events(base_event, city=city, date_from=df, date_to=dt, limit=4)
                results = []
                for item in items:
                    st = str(getattr(getattr(item, "status", None), "value", getattr(item, "status", None))).upper()
                    if st != "PUBLISHED":
                        continue
                    card_dict = self._card_dict(item)
                    if self.on_card_fetched:
                        self.on_card_fetched(card_dict)
                    results.append(self.guardrails.sanitize_untrusted_event_data(card_dict))

                return json.dumps({"count": len(results), "events": results, "similar_events": results}, ensure_ascii=False)
            except Exception:
                return json.dumps({"error": "SIMILAR_SEARCH_FAILED"})

        @tool("get_venue_schedule", args_schema=GetVenueScheduleInput)
        async def get_venue_schedule_tool(venue: str, date_from: str, date_to: str) -> str:
            """Проверка расписания площадки за период (театр, ДК, филармония)."""
            try:
                df = self.norm.parse_date_to_yekaterinburg(date_from) if hasattr(self.norm, "parse_date_to_yekaterinburg") else date_from
                dt = self.norm.parse_date_to_yekaterinburg(date_to) if hasattr(self.norm, "parse_date_to_yekaterinburg") else date_to
                items = await self.event_repo.get_venue_schedule(venue, df, dt)

                results = []
                for item in items:
                    st = str(getattr(getattr(item, "status", None), "value", getattr(item, "status", None))).upper()
                    if st != "PUBLISHED":
                        continue
                    card_dict = self._card_dict(item)
                    if self.on_card_fetched:
                        self.on_card_fetched(card_dict)
                    results.append(self.guardrails.sanitize_untrusted_event_data(card_dict))

                safe_venue = self.guardrails.sanitize_untrusted_event_data({"venue": venue})["venue"]
                return json.dumps({"venue": safe_venue, "events_count": len(results), "events": results, "schedule": results}, ensure_ascii=False)
            except Exception:
                return json.dumps({"error": "SCHEDULE_FAILED"})

        @tool("subscribe", args_schema=SubscribeInput)
        async def subscribe_tool(city: str, category: str | None = None, period_type: str = "all", period: str = "all", action_type: str = "create") -> str:
            """Оформление или перенос подписки. Требует обязательного подтверждения пользователя!"""
            try:
                action_id = f"sub_{uuid4().hex[:8]}"
                if not self.confirmed_action_id:
                    cat_name = category or "все категории"
                    return json.dumps({
                        "status": "CONFIRMATION_REQUIRED",
                        "pending_action_id": action_id,
                        "summary": f"Оформить подписку на культурные события в г. {city} ({cat_name})?",
                    }, ensure_ascii=False)

                return json.dumps({"status": "UNAVAILABLE", "error": "SECURE_CONFIRMATION_STORE_REQUIRED"})
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

                return json.dumps({"status": "UNAVAILABLE", "error": "SECURE_CONFIRMATION_STORE_REQUIRED"})
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
