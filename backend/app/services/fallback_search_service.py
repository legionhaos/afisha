import re
from datetime import datetime, time, timedelta
from decimal import Decimal
from time import monotonic
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
        clean_text = text.lower().replace("ё", "е").strip()
        filters = EventSearchFilterDTO()

        now_yekt = datetime.now(YEKT_TZ)
        today_start = datetime.combine(now_yekt.date(), time.min, tzinfo=YEKT_TZ)
        today_end = datetime.combine(now_yekt.date(), time.max, tzinfo=YEKT_TZ)

        # 1. Поиск города
        # Only match city names or conservative Russian inflections, never fuzzy-match
        # arbitrary words (e.g. "концерт") to unrelated cities.
        words = re.findall(r"[а-яёa-z-]+", clean_text)
        cities = await self.dict_repo.get_all_cities()
        for city in cities:
            name = city.name.lower().replace('ё', 'е')
            forms = {name}
            if name == 'уфа':
                forms.update({'уфе', 'уфу', 'уфы'})
            elif name.endswith('а') and len(name) > 4:
                forms.update({name[:-1] + 'е', name[:-1] + 'у', name[:-1] + 'ы'})
            elif name.endswith('й') and len(name) > 4:
                forms.update({name[:-1] + 'ом', name[:-1] + 'ого'})
            elif len(name) > 4 and name[-1] not in 'оеьы':
                forms.update({name + 'е', name + 'а', name + 'у', name + 'ом'})
            if any(word in forms for word in words):
                filters.city = city.name
                break

        # 2. Поиск даты
        if "сегодня" in clean_text:
            filters.date_from = today_start
            filters.date_to = today_end
        elif "завтра" in clean_text:
            filters.date_from = today_start + timedelta(days=1)
            filters.date_to = today_end + timedelta(days=1)
        elif "суббот" in clean_text:
            filters.date_from = today_start + timedelta(days=(5 - now_yekt.weekday()) % 7)
            filters.date_to = filters.date_from + timedelta(days=1, microseconds=-1)
        elif "воскрес" in clean_text:
            filters.date_from = today_start + timedelta(days=(6 - now_yekt.weekday()) % 7)
            filters.date_to = filters.date_from + timedelta(days=1, microseconds=-1)
        elif "выходн" in clean_text:
            days_until_sat = 0 if now_yekt.weekday() == 6 else (5 - now_yekt.weekday()) % 7
            filters.date_from = today_start + timedelta(days=days_until_sat)
            days = 1 if now_yekt.weekday() == 6 else 2
            filters.date_to = filters.date_from + timedelta(days=days, microseconds=-1)
        elif re.search(r'\b(?:на\s+)?следующ\w*\s+недел\w*\b', clean_text):
            filters.date_from = today_start + timedelta(days=7 - now_yekt.weekday())
            filters.date_to = filters.date_from + timedelta(days=7, microseconds=-1)
        elif "на этой неделе" in clean_text:
            filters.date_from = today_start
            filters.date_to = today_end + timedelta(days=6 - now_yekt.weekday())

        # 3. Поиск цены
        if re.search(r"(?<!не )\b(?:бесплатн\w*|вход\s+свободн\w*|свободный\s+вход|даром)\b", clean_text):
            filters.is_free = True
        else:
            price_match = re.search(
                r"(?:до|дешевле|менее|не дороже|за|в пределах)\s*(\d{1,3}(?:[  ]\d{3})+|\d+)\s*(?:руб(?:лей|ля|ль)?\.?|р\.?(?!\w)|₽)",
                clean_text,
            )
            if price_match:
                amount = int(re.sub(r"\s", "", price_match.group(1)))
                filters.price_max = amount // 2 if re.search(r"\bна\s+двоих\b", clean_text) else amount

        # 4. Поиск возраста
        age_match = re.search(
            r"\b(?:ребенк\w*|дет\w*|сын\w*|доч\w*)\s+(\d{1,2})\s*(?:лет|года|год)\b"
            r"|\b(\d{1,2})\s*(?:лет|года|год)\s+(?:ребенк\w*|сын\w*|доч\w*)\b",
            clean_text,
        )
        if age_match:
            filters.age_limit_max = min(int(age_match.group(1) or age_match.group(2)), 18)

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

        # Specific interests are mandatory constraints, not merely ranking hints.
        if re.search(r'\b(?:рок(?:а|у|ом|е)?|rock)\b', clean_text):
            filters.category = EventCategory.CONCERT
            filters.query_text = 'рок|rock'
        elif re.search(r'\b(?:хокке\w*|hockey)\b', clean_text):
            filters.query_text = 'хоккей|hockey'
        elif re.search(r'\b(?:футбол\w*|football)\b', clean_text):
            filters.query_text = 'футбол|football'
        elif re.search(r'\b(?:волейбол\w*|volleyball)\b', clean_text):
            filters.query_text = 'волейбол'
        elif re.search(r'\b(?:баскетбол\w*|basketball)\b', clean_text):
            filters.query_text = 'баскетбол'
        elif re.search(r'\b(?:спорт\w*|матч\w*|турнир\w*)\b', clean_text):
            filters.query_text = 'спорт|хоккей|футбол'
        elif re.search(r'\b(?:танц\w*|танцевальн\w*|dance)\b', clean_text):
            filters.query_text = 'танцы|танцевальный|танцевальная|dance'
        elif re.search(r'\b(?:джаз\w*|jazz)\b', clean_text):
            filters.category = EventCategory.CONCERT
            filters.query_text = 'джаз|jazz'
        else:
            filters.query_text = None
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
        started = monotonic()
        filters = await self.parse_free_text_deterministically(message)
        needs_city = not filters.city
        result = None if needs_city else await self.catalog_service.search_catalog(filters)

        recommendations = [
            AgentRecommendationItemDTO(
                event=item,
                constraint_match_explanation="Сведения из каталога; уточните условия у организатора.",
            )
            for item in (result.items if result else [])
        ]

        trace_id = uuid4()
        if needs_city:
            reply_intro = 'В каком городе ищем события?'
        elif recommendations:
            reply_intro = f'Нашлось событий: {len(recommendations)}. Сейчас работает упрощённый поиск — проверьте остальные условия.'
        else:
            reply_intro = 'По этим параметрам событий не нашлось. Попробуйте изменить запрос.'

        # Сохранение трассировки с флагом fallback_used = True
        await self.audit_repo.save_agent_trace({
            "id": trace_id,
            "request_id": request_id,
            "thread_id": thread_id,
            "user_query": message,
            "plan_steps": ["fallback_deterministic_parse", "catalog_search"],
            "tool_calls": [{"tool": "deterministic_search", "args": filters.model_dump(mode="json")}],
            "grounding_event_ids": [item.id for item in (result.items if result else [])],
            "latency_ms": round((monotonic() - started) * 1000),
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
            fallback_notice="Работает упрощённый поиск без ИИ.",
            clarifying_question=('В каком городе ищем события?' if needs_city and not unsupported_sport else None),
            data_grounded_badge="Ответ построен исключительно по проверенным данным сервиса",
        )
