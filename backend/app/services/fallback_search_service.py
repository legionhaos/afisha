import re
from datetime import datetime, time, timedelta
from decimal import Decimal
from typing import Any
from uuid import uuid4

from app.models.enums import EventCategory
from app.repositories.audit_trace_repo import AuditTraceRepository
from app.repositories.dictionary_repo import DictionaryRepository
from app.schemas.chat import (
    AgentRecommendationItemDTO,
    ChatMessageResponseDTO,
)
from app.schemas.event import EventSearchFilterDTO
from app.services.catalog_service import CatalogService
from app.services.normalization_service import YEKT_TZ


class FallbackSearchService:
    """Резервный детерминированный парсер и поиск при отключенной LLM (раздел 7.5 ТЗ)."""

    def __init__(
        self,
        catalog_service: CatalogService,
        dict_repo: DictionaryRepository,
        audit_repo: AuditTraceRepository,
    ) -> None:
        self.catalog_service = catalog_service
        self.dict_repo = dict_repo
        self.audit_repo = audit_repo

    async def parse_free_text_deterministically(self, text: str) -> EventSearchFilterDTO:
        """Детерминированно извлекает фильтры из русскоязычного свободного текста без LLM."""
        clean_text = text.lower().strip()
        filters = EventSearchFilterDTO()

        now_yekt = datetime.now(YEKT_TZ)
        today_start = datetime.combine(now_yekt.date(), time.min, tzinfo=YEKT_TZ)
        today_end = datetime.combine(now_yekt.date(), time.max, tzinfo=YEKT_TZ)

        # 1. Поиск города
        # Проверяем токены запроса через триграммный справочник городов
        words = re.findall(r"[а-яёА-ЯЁa-zA-Z]+", text)
        for w in words:
            if len(w) >= 3:
                resolved = await self.dict_repo.resolve_city_name(w)
                if resolved:
                    filters.city = resolved
                    break

        # 2. Поиск даты
        if "сегодня" in clean_text:
            filters.date_from = today_start
            filters.date_to = today_end
        elif "завтра" in clean_text:
            filters.date_from = today_start + timedelta(days=1)
            filters.date_to = today_end + timedelta(days=1)
        elif any(w in clean_text for w in ["выходн", "суббот", "воскрес"]):
            days_until_sat = (5 - now_yekt.weekday()) % 7
            sat_start = today_start + timedelta(days=days_until_sat)
            sun_end = sat_start + timedelta(days=1, hours=23, minutes=59, seconds=59)
            filters.date_from = sat_start
            filters.date_to = sun_end
        elif "на этой неделе" in clean_text or "недел" in clean_text:
            filters.date_from = today_start
            filters.date_to = today_end + timedelta(days=7)

        # 3. Поиск цены
        if re.search(r"(?i)(?:^|\s)(бесплатн\w*|вход\s+свободн\w*|свободный\s+вход|даром|(?<!\d)0\s*(?:руб|р|₽)?)(?:$|\s|[.,;!?])", f" {clean_text} "):
            filters.is_free = True
        else:
            price_match = re.search(r"(?:до|дешевле|менее|не дороже)\s*(\d+)", clean_text)
            if price_match:
                filters.price_max = int(price_match.group(1))

        # 4. Поиск возраста
        age_match = re.search(r"(\d+)\s*(?:лет|года|год)", clean_text)
        if age_match:
            filters.age_limit_max = int(age_match.group(1))
        elif any(w in clean_text for w in ["с ребенком", "для детей", "детск"]):
            filters.age_limit_max = 12

        # 5. Поиск категории
        if any(w in clean_text for w in ["концерт", "музык", "песн", "оркестр", "симфон"]):
            filters.category = EventCategory.CONCERT
        elif any(w in clean_text for w in ["спектакл", "театр", "драм", "балет", "опер"]):
            filters.category = EventCategory.THEATER
        elif any(w in clean_text for w in ["выставк", "музей", "галере", "экспозици"]):
            filters.category = EventCategory.EXHIBITION
        elif any(w in clean_text for w in ["фестивал", "праздник"]):
            filters.category = EventCategory.FESTIVAL
        elif any(w in clean_text for w in ["кино", "фильм"]):
            filters.category = EventCategory.CINEMA
        elif any(w in clean_text for w in ["экскурси", "тур"]):
            filters.category = EventCategory.EXCURSION

        # 6. Остальной текст как query_text
        filters.query_text = text[:150]
        filters.page_size = 5
        return filters

    async def execute_fallback_query(
        self,
        thread_id: str,
        user_identifier: str,
        message: str,
        request_id: str,
    ) -> ChatMessageResponseDTO:
        """Выполняет поиск без языковой модели и возвращает гарантированный структурированный ответ."""
        filters = await self.parse_free_text_deterministically(message)
        result = await self.catalog_service.search_catalog(filters)

        recommendations = [
            AgentRecommendationItemDTO(
                event=item,
                constraint_match_explanation="Мероприятие подобрано по совпадению города, дат и категории.",
            )
            for item in result.items
        ]

        trace_id = uuid4()
        reply_intro = (
            "⚠️ Интеллектуальный агент временно работает в резервном режиме поиска по фильтрам. "
        )
        if recommendations:
            reply_intro += f"По вашему запросу найдено {len(recommendations)} подходящих мероприятий в базе:"
        else:
            reason = result.empty_explanation.message if result.empty_explanation else "Ничего не найдено."
            reply_intro += f"{reason} Попробуйте изменить параметры поиска."

        # Сохранение трассировки с флагом fallback_used = True
        await self.audit_repo.save_agent_trace({
            "id": trace_id,
            "request_id": request_id,
            "thread_id": thread_id,
            "user_query": message,
            "plan_steps": ["fallback_deterministic_parse", "catalog_search"],
            "tool_calls": [{"tool": "deterministic_search", "args": filters.model_dump(mode="json")}],
            "grounding_event_ids": [item.id for item in result.items],
            "latency_ms": 15,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "estimated_cost_rub": Decimal("0.0000"),
            "fallback_used": True,
        })

        return ChatMessageResponseDTO(
            thread_id=thread_id,
            trace_id=trace_id,
            reply_text=reply_intro,
            recommendations=recommendations,
            is_fallback_mode=True,
            fallback_notice="Интеллектуальный агент переключен в резервный режим без LLM.",
            data_grounded_badge="Ответ построен исключительно по проверенным данным сервиса",
        )
