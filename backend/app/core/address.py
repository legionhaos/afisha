import ast
import json
from typing import Any


def normalize_address(value: Any) -> str:
    """Extract a readable address from schema.org objects, including legacy serialized values."""
    if isinstance(value, str):
        text = value.strip()
        if not text.startswith("{"):
            return text
        try:
            value = json.loads(text)
        except (ValueError, TypeError):
            try:
                value = ast.literal_eval(text)
            except (ValueError, SyntaxError, MemoryError, RecursionError):
                return ""
    if not isinstance(value, dict):
        return ""
    parts = [value.get(key) for key in ("postalCode", "addressRegion", "addressLocality", "streetAddress")]
    return ", ".join(part.strip() for part in parts if isinstance(part, str) and part.strip())
