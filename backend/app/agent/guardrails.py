"""Input screening and output grounding for the cultural assistant."""

import copy
import re
import unicodedata
from html import escape
from typing import Any

_REFUSAL = "Я помогаю только с поиском культурных мероприятий Башкортостана и не могу выполнить эту инструкцию."
_PATTERNS = tuple(re.compile(p, re.IGNORECASE) for p in (
    r"игнорируй(?:те)?\s+(?:все\s+)?(?:предыдущие|прежние|системные)\s+инструкц",
    r"забудь(?:те)?\s+(?:все\s+)?(?:предыдущие|прежние|правила|инструкц)",
    r"(?:покажи|раскрой|выведи)\s+(?:свой\s+)?системн\w*\s+(?:промпт|инструкц)",
    r"ignore\s+(?:all\s+)?(?:previous|prior|system)\s+instructions?",
    r"(?:reveal|show|print)\s+(?:the\s+)?system\s+prompt",
    r"you\s+are\s+now\s+dan\b",
    r"(?:^|\s)(?:system|assistant|developer)\s*:\s",
))


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    return "".join(" " if unicodedata.category(c) == "Cc" else c for c in text if unicodedata.category(c) != "Cf")


class GuardrailService:
    def check_user_input(self, user_text: str) -> tuple[bool, str | None]:
        return (False, _REFUSAL) if self.scan_external_data_for_injection(user_text) else (True, None)

    def scan_external_data_for_injection(self, text: str) -> bool:
        normalized = _normalize(str(text))
        return any(pattern.search(normalized) for pattern in _PATTERNS)

    def sanitize_untrusted_event_data(self, event_dict: dict[str, Any]) -> dict[str, Any]:
        def screen(value: Any) -> Any:
            if isinstance(value, str):
                return "[Скрыто: обнаружены подозрительные инструкции]" if self.scan_external_data_for_injection(value) else value
            if isinstance(value, list):
                return [screen(item) for item in value]
            if isinstance(value, dict):
                return {key: screen(item) for key, item in value.items()}
            return copy.deepcopy(value)

        result = {key: screen(value) for key, value in event_dict.items() if key != "description"}
        description = _normalize(str(event_dict.get("description") or ""))
        if self.scan_external_data_for_injection(description):
            description = "[Описание скрыто: обнаружены подозрительные инструкции]"
        result["description"] = f"<untrusted_event_description>{escape(description)}</untrusted_event_description>"
        return result

    def verify_output_grounding(self, llm_output: dict[str, Any], verified_cards_map: dict[str, dict[str, Any]]) -> dict[str, Any]:
        # Do not pass through free-form model prose or unknown fields: checking IDs
        # cannot validate claims embedded in them.
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
                card = verified_cards_map.get(str(event_id))
                if not isinstance(card, dict):
                    continue
                if key == "recommendations" or isinstance(nested, dict):
                    verified.append({"event": copy.deepcopy(card), "constraint_match_explanation": "Данные мероприятия проверены по каталогу."})
                else:
                    verified.append(copy.deepcopy(card))
            output[key] = verified
        return output
