import re
import unicodedata
from typing import Any

INJECTION_PATTERNS = [
    re.compile(r"(?i)\b(?:игнорируй|забудь|отмени|сбрось)\s+(?:все\s+)?(?:предыдущие\s+)?(?:инструкции|правила|указания)\b"),
    re.compile(r"(?i)\b(?:ignore|forget|disregard|override)\s+(?:all\s+)?(?:previous\s+)?(?:instructions|rules|prompts?)\b"),
    re.compile(r"(?i)\b(?:покажи|выведи|раскрой|скажи)\s+(?:свой\s+)?(?:системный\s+промпт|system\s+prompt|исходный\s+промпт)\b"),
    re.compile(r"(?i)\b(?:show|reveal|display|output|print)\s+(?:your\s+)?(?:system\s+prompt|developer\s+mode|initial\s+prompt)\b"),
    re.compile(r"(?i)\b(?:ты\s+теперь|ты\s+больше\s+не|действуй\s+как|act\s+as)\s+(?:DAN|jailbreak|режим\s+разработчика|unrestricted)\b"),
    re.compile(r"(?i)<\s*(?:script|iframe|object|embed|svg|style)"),
]

PROMPT_LEAK_PATTERNS = [
    re.compile(r"(?i)ZERO HALLUCINATION POLICY"),
    re.compile(r"(?i)<untrusted_event_description>"),
    re.compile(r"(?i)ГЛАВНЫЕ ПРАВИЛА И ПОЛИТИКА ДОСТОВЕРНОСТИ"),
]


class GuardrailService:
    """Многослойная защита от инъекций промпта и контроль фактической достоверности (152-ФЗ, Defense-in-Depth)."""

    def check_user_input(self, user_text: str) -> tuple[bool, str | None]:
        """Проверяет входной текст пользователя на наличие попыток Prompt Injection."""
        if not user_text or not user_text.strip():
            return True, None

        # Нормализация Unicode (удаление невидимых символов и гомоглифов)
        normalized = unicodedata.normalize("NFKC", user_text)

        for pattern in INJECTION_PATTERNS:
            if pattern.search(normalized):
                return False, (
                    "Я интеллектуальный помощник по афише культурных мероприятий Республики Башкортостан. "
                    "Я могу помочь найти спектакли, концерты, выставки и экскурсии. "
                    "Пожалуйста, задайте вопрос по афише."
                )

        return True, None

    def sanitize_untrusted_event_data(self, event_dict: dict[str, Any]) -> dict[str, Any]:
        """Оборачивает неконтролируемые данные из БД в изолирующие теги (Spotlighting)."""
        sanitized = dict(event_dict)

        desc = str(sanitized.get("description", ""))
        # Вырезаем попытки внедрения тегов
        desc = re.sub(r"(?i)</?untrusted_event_description>", "", desc)
        sanitized["description"] = f"<untrusted_event_description>{desc}</untrusted_event_description>"

        title = str(sanitized.get("title", ""))
        sanitized["title"] = re.sub(r"(?i)</?untrusted_event_description>", "", title)

        return sanitized

    def verify_output_grounding(
        self,
        reply_text: str,
        grounding_event_ids: list[str],
        verified_cards_map: dict[str, dict[str, Any]],
    ) -> tuple[str, list[dict[str, Any]]]:
        """Проверяет финальный ответ модели на отсутствие галлюцинаций и утечек промпта."""
        cleaned_reply = reply_text

        # 1. Защита от утечки фрагментов системного промпта
        for leak_pattern in PROMPT_LEAK_PATTERNS:
            cleaned_reply = leak_pattern.sub("[СКРЫТО]", cleaned_reply)

        # 2. Фильтрация карточек-оснований
        # Оставляем только те карточки, которые реально были получены из инструментов в этом диалоге
        valid_recommendations: list[dict[str, Any]] = []
        for eid in grounding_event_ids:
            if eid in verified_cards_map:
                valid_recommendations.append(verified_cards_map[eid])

        # Ограничение до 5 лучших карточек
        valid_recommendations = valid_recommendations[:5]

        return cleaned_reply, valid_recommendations


guardrail_service = GuardrailService()
