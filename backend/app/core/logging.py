import logging
import re
import sys
from contextvars import ContextVar
from typing import Any

import structlog

# Context variable for request tracing
request_id_ctx_var: ContextVar[str] = ContextVar("request_id", default="")
trace_id_ctx_var: ContextVar[str] = ContextVar("trace_id", default="")

# Regular expressions for identifying PII according to 152-FZ
# Russian phone numbers: +7..., 89...
PHONE_REGEX = re.compile(r"(?:\+7|8)[\s\-]?(?:\(?\d{3}\)?[\s\-]?)?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}\b")
# Email addresses
EMAIL_REGEX = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")
# IPv4 addresses
IP_REGEX = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
# Sensitive keys to scrub entirely
SENSITIVE_KEYS = {
    "password",
    "token",
    "secret",
    "api_key",
    "authorization",
    "access_token",
    "refresh_token",
    "cookie",
    "credentials",
}


class PIIScrubberProcessor:
    """Structlog processor that masks Personally Identifiable Information (152-FZ).

    Redacts phone numbers, emails, IP addresses, and sensitive credentials
    replacing them with [SCRUBBED].
    """

    def __call__(
        self,
        logger: Any,
        method_name: str,
        event_dict: dict[str, Any],
    ) -> dict[str, Any]:
        return self._scrub_dict(event_dict)

    def _scrub_value(self, val: Any) -> Any:
        if isinstance(val, str):
            val = PHONE_REGEX.sub("[SCRUBBED_PHONE]", val)
            val = EMAIL_REGEX.sub("[SCRUBBED_EMAIL]", val)
            val = IP_REGEX.sub("[SCRUBBED_IP]", val)
            return val
        elif isinstance(val, dict):
            return self._scrub_dict(val)
        elif isinstance(val, list | tuple):
            return [self._scrub_value(item) for item in val]
        return val

    def _scrub_dict(self, d: dict[str, Any]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for k, v in d.items():
            key_lower = k.lower()
            if any(sensitive in key_lower for sensitive in SENSITIVE_KEYS):
                result[k] = "[SCRUBBED_SECRET]"
            else:
                result[k] = self._scrub_value(v)
        return result


def add_request_id_processor(
    logger: Any,
    method_name: str,
    event_dict: dict[str, Any],
) -> dict[str, Any]:
    """Injects active request_id and trace_id from contextvars."""
    req_id = request_id_ctx_var.get()
    if req_id:
        event_dict["request_id"] = req_id

    tr_id = trace_id_ctx_var.get()
    if tr_id:
        event_dict["trace_id"] = tr_id

    return event_dict


def setup_logging(level: str = "INFO") -> None:
    """Configures structlog and standard logging with PII scrubbing and JSON output."""
    log_level = getattr(logging, level.upper(), logging.INFO)

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        add_request_id_processor,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        PIIScrubberProcessor(),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    structlog.configure(
        processors=shared_processors + [
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
    )
