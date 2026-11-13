"""Deterministic search used when the model cannot be reached."""

import re
import time as monotonic_time
from datetime import datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from app.schemas.event import EventSearchFilterDTO
from app.schemas.chat import AgentRecommendationItemDTO, ChatMessageResponseDTO

ZONE = ZoneInfo("Asia/Yekaterinburg")
NOTICE = "Интеллектуальный агент временно недоступен. Показаны результаты автоматического поиска по вашим параметрам."


class FallbackSearchService:
    def __init__(self, catalog_service: Any, dict_repo: Any, audit_repo: Any) -> None:
        self.catalog_service = catalog_service
        self.dict_repo = dict_repo
        self.audit_repo = audit_repo

    async def parse_free_text_deterministically(self, text: str, dict_repo: Any) -> EventSearchFilterDTO:
        text = text.lower().replace("ё", "е")
        values: dict[str, Any] = {}
        if re.search(r"(?<!не )\b(?:бесплатн\w*|свободн\w*\s+вход)\b", text):
            values["is_free"] = True
        budget = re.search(r"\bдо\s+(\d{1,3}(?:[\s ]\d{3})+|\d+)\s*(?:руб(?:лей|ля|ль)?\.?|р\.?(?!\w)|₽)", text)
        if budget and not re.search(r"\b(?:от|более|дороже)\s+\d", text):
            amount = int(re.sub(r"\s", "", budget.group(1)))
            values["price_max"] = amount // 2 if re.search(r"\bна\s+двоих\b", text) else amount
        age = re.search(r"\b(?:ребенк\w*|дет\w*|сын\w*|доч\w*)\s+(\d{1,2})\s*(?:лет|года|год)\b|\b(\d{1,2})\s*(?:лет|года|год)\s+(?:ребенк\w*|сын\w*|доч\w*)\b", text)
        if age:
            values["age_limit_max"] = min(int(age.group(1) or age.group(2)), 18)
        today = datetime.now(ZONE).date()
        day = None
        days = 1
        date_terms = [bool(re.search(pattern, text)) for pattern in (r"\bсегодня\b", r"\bзавтра\b", r"\bвыходн\w*", r"\bсуббот\w*", r"\bвоскресен\w*")]
        ambiguous_date = sum(date_terms) > 1 or bool(re.search(r"\b(?:следующ\w*|прошл\w*|через|после|до)\s+(?:недел\w*|выходн\w*|суббот\w*|воскресен\w*|завтра)", text))
        if ambiguous_date:
            pass
        elif "сегодня" in text:
            day = today
        elif "завтра" in text:
            day = today + timedelta(days=1)
        elif "выходн" in text:
            day = today if today.weekday() == 6 else today + timedelta(days=(5 - today.weekday()) % 7)
            days = 1 if today.weekday() == 6 else 2
        elif re.search(r"суббот", text):
            day = today + timedelta(days=(5 - today.weekday()) % 7)
        elif re.search(r"воскресен", text):
            day = today + timedelta(days=(6 - today.weekday()) % 7)
        if day:
            values["date_from"] = datetime.combine(day, time.min, ZONE)
            values["date_to"] = datetime.combine(day + timedelta(days=days), time.min, ZONE) - timedelta(microseconds=1)
        categories = {"концерт": "CONCERT", "спектакл": "THEATER", "театр": "THEATER", "выставк": "EXHIBITION", "фестивал": "FESTIVAL", "экскурс": "EXCURSION", "кино": "CINEMA"}
        matched_categories = {category for root, category in categories.items() if root in text}
        if len(matched_categories) == 1 and not re.search(r"\b(?:без|кроме|не)\s+\w+", text):
            values["category"] = matched_categories.pop()
        ignored = {"концерты", "концерт", "сегодня", "завтра", "субботу", "воскресенье", "ребенком", "бесплатные", "выставки", "спектакли", "мероприятия", "рублей", "двоих", "пойти", "куда", "выходных"}
        for token in re.findall(r"[а-я-]{3,}", text):
            if token in ignored or len(token) < 4 and token != "уфа":
                continue
            city = await dict_repo.resolve_city_name(token)
            if city:
                values["city"] = city
                break
        return EventSearchFilterDTO(**values)

    async def execute_fallback_query(self, thread_id: str, user_identifier: str, message: str, request_id: str) -> ChatMessageResponseDTO:
        started = monotonic_time.monotonic()
        filters = await self.parse_free_text_deterministically(message, self.dict_repo)
        # The current CatalogService contract always generates embeddings for text
        # queries; an empty query keeps this path independent of the model.
        result = await self.catalog_service.search_catalog(filters)
        cards = [AgentRecommendationItemDTO(event=event, constraint_match_explanation="Данные из каталога мероприятий; уточните ограничения и стоимость у организатора.") for event in result.items]
        trace = await self.audit_repo.save_agent_trace({
            "request_id": request_id, "thread_id": thread_id, "user_query": message,
            "plan_steps": ["Резервный поиск"], "tool_calls": [],
            "grounding_event_ids": [item.event.id for item in cards], "latency_ms": round((monotonic_time.monotonic() - started) * 1000),
            "prompt_tokens": 0, "completion_tokens": 0, "estimated_cost_rub": 0,
            "fallback_used": True,
        })
        explanation = getattr(result, "empty_explanation", None)
        reply = "Найдены мероприятия. Проверьте все условия у организатора: автоматический поиск может распознать не все ограничения."
        if not cards:
            reply = getattr(explanation, "message", None) or "По распознанным параметрам мероприятия не найдены."
            reply += " Автоматический поиск мог не распознать некоторые ограничения; уточните запрос."
        return ChatMessageResponseDTO(thread_id=thread_id, trace_id=trace.id,
            reply_text=reply, recommendations=cards, is_fallback_mode=True, fallback_notice=NOTICE)
