import copy
import re
import unicodedata
from html import escape
from typing import Any

INJECTION_PATTERNS = [
    re.compile(r"(?i)\b(?:игнорируй|забудь|отмени|сбрось)\s+(?:все\s+)?(?:предыдущие\s+)?(?:инструкции|правила|указания)\b"),
    re.compile(r"(?i)\b(?:ignore|forget|disregard|override)\s+(?:all\s+)?(?:previous\s+)?(?:instructions|rules|prompts?)\b"),
    re.compile(r"(?i)\b(?:покажи|выведи|раскрой|скажи)\s+(?:свой\s+)?(?:системный\s+промпт|system\s+prompt|исходный\s+промпт)\b"),
    re.compile(r"(?i)\b(?:show|reveal|display|output|print)\s+(?:your\s+)?(?:system\s+prompt|developer\s+mode|initial\s+prompt)\b"),
    re.compile(r"(?i)\b(?:ты\s+теперь|ты\s+больше\s+не|действуй\s+как|act\s+as)\s+(?:DAN|jailbreak|режим\s+разработчика|unrestricted)\b"),
    re.compile(r"(?i)<\s*(?:script|iframe|object|embed|svg|style)"),
    re.compile(r"(?i)(?:^|\s)(?:system|assistant|developer)\s*:\s"),
]

PROMPT_LEAK_PATTERNS = [
    re.compile(r"(?i)ZERO HALLUCINATION POLICY"),
    re.compile(r"(?i)<untrusted_event_description>"),
    re.compile(r"(?i)ГЛАВНЫЕ ПРАВИЛА И ПОЛИТИКА ДОСТОВЕРНОСТИ"),
]


class GuardrailService:
    """Многослойная защита от инъекций промпта и контроль фактической достоверности (152-ФЗ, Defense-in-Depth)."""

    @staticmethod
    def _normalize(text: str) -> str:
        return "".join(" " if unicodedata.category(c) == "Cc" else c
                       for c in unicodedata.normalize("NFKC", text)
                       if unicodedata.category(c) != "Cf")

    def scan_external_data_for_injection(self, text: str) -> bool:
        normalized = self._normalize(str(text))
        return any(pattern.search(normalized) for pattern in INJECTION_PATTERNS)

    def check_user_input(self, user_text: str) -> tuple[bool, str | None]:
        """Проверяет входной текст пользователя на наличие попыток Prompt Injection."""
        if not user_text or not user_text.strip():
            return True, None

        # Нормализация Unicode (удаление невидимых символов и гомоглифов)
        normalized = self._normalize(user_text)

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
        def screen(value: Any) -> Any:
            if isinstance(value, str):
                return "[Скрыто: обнаружены подозрительные инструкции]" if self.scan_external_data_for_injection(value) else value
            if isinstance(value, list):
                return [screen(item) for item in value]
            if isinstance(value, dict):
                return {key: screen(item) for key, item in value.items()}
            return value

        sanitized = {key: screen(value) for key, value in event_dict.items() if key != "description"}
        desc = self._normalize(str(event_dict.get("description") or ""))
        if self.scan_external_data_for_injection(desc):
            desc = "[Описание скрыто: обнаружены подозрительные инструкции]"
        sanitized["description"] = f"<untrusted_event_description>{escape(desc)}</untrusted_event_description>"
        return sanitized

    def verify_output_grounding(
        self,
        output_or_reply: dict[str, Any] | str | None = None,
        cards_or_ids: dict[str, dict[str, Any]] | list[str] | None = None,
        verified_cards_map: dict[str, dict[str, Any]] | None = None,
        *,
        reply_text: str | None = None,
        grounding_event_ids: list[str] | None = None,
        llm_output: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        """Проверяет финальный ответ модели на отсутствие галлюцинаций и утечек промпта.

        Поддерживает как 2-аргументную сигнатуру со словарём (llm_output, verified_cards_map),
        так и 3-аргументную сигнатуру (reply_text, grounding_event_ids, verified_cards_map).
        """
        if reply_text is not None:
            output_or_reply = reply_text
        elif llm_output is not None:
            output_or_reply = llm_output
        if grounding_event_ids is not None:
            cards_or_ids = grounding_event_ids

        if isinstance(output_or_reply, dict):
            llm_output = output_or_reply
            cards_map = cards_or_ids if isinstance(cards_or_ids, dict) else {}
            output: dict[str, Any] = {}
            for key in ("recommendations", "events", "cards"):
                if key not in llm_output or not isinstance(llm_output[key], list):
                    continue
                verified = []
                for item in llm_output[key]:
                    if not isinstance(item, dict):
                        continue
                    nested = item.get("event")
                    event_id = item.get("event_id") or item.get("id") or (nested.get("id") if isinstance(nested, dict) else None)
                    card = cards_map.get(str(event_id))
                    if not isinstance(card, dict):
                        continue
                    if key == "recommendations" or isinstance(nested, dict):
                        verified.append({"event": copy.deepcopy(card), "constraint_match_explanation": "Данные мероприятия проверены по каталогу."})
                    else:
                        verified.append(copy.deepcopy(card))
                output[key] = verified
            return output

        # 3-arg signature (reply_text, grounding_event_ids, verified_cards_map)
        cleaned_reply = str(output_or_reply)
        for leak_pattern in PROMPT_LEAK_PATTERNS:
            cleaned_reply = leak_pattern.sub("[СКРЫТО]", cleaned_reply)

        grounding_event_ids = cards_or_ids if isinstance(cards_or_ids, list) else []
        cards_map = verified_cards_map or {}
        valid_recommendations: list[dict[str, Any]] = []
        seen: set[str] = set()
        for eid in grounding_event_ids:
            if eid in cards_map and eid not in seen:
                valid_recommendations.append(cards_map[eid])
                seen.add(eid)

        valid_recommendations = valid_recommendations[:5]
        return cleaned_reply, valid_recommendations


guardrail_service = GuardrailService()
