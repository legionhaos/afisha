from typing import Any
from fastapi import Request
from fastapi.responses import JSONResponse

from app.core.logging import request_id_ctx_var


class AppError(Exception):
    """Base application exception following RFC 7807 problem details specification."""

    def __init__(
        self,
        code: str,
        title: str,
        detail: str,
        status_code: int = 400,
        type_uri: str = "about:blank",
        errors: list[dict[str, Any]] | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(detail)
        self.code = code
        self.title = title
        self.detail = detail
        self.status_code = status_code
        self.type_uri = type_uri
        self.errors = errors
        self.extra = extra or {}


class UnauthorizedAdminError(AppError):
    """HTTP 401 Unauthorized for admin endpoints."""

    def __init__(
        self,
        detail: str = "Неверный или отсутствующий ключ администратора",
        extra: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            code="UNAUTHORIZED_ADMIN",
            title="Ошибка авторизации администратора",
            detail=detail,
            status_code=401,
            extra=extra,
        )


class EventNotFoundError(AppError):
    """HTTP 404 Not Found for missing cultural events."""

    def __init__(
        self,
        event_id: str | None = None,
        detail: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        if detail is None:
            detail = f"Мероприятие с идентификатором '{event_id}' не найдено" if event_id else "Мероприятие не найдено"
        super().__init__(
            code="EVENT_NOT_FOUND",
            title="Мероприятие не найдено",
            detail=detail,
            status_code=404,
            extra=extra,
        )


class ValidationFailedError(AppError):
    """HTTP 422 Unprocessable Entity for domain validation failures."""

    def __init__(
        self,
        detail: str = "Ошибка валидации входных данных",
        errors: list[dict[str, Any]] | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            code="VALIDATION_FAILED",
            title="Ошибка валидации данных",
            detail=detail,
            status_code=422,
            errors=errors,
            extra=extra,
        )


class RateLimitExceededError(AppError):
    """HTTP 429 Too Many Requests for rate limiter breaches."""

    def __init__(
        self,
        detail: str = "Превышен лимит запросов. Пожалуйста, повторите попытку позже.",
        extra: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            code="RATE_LIMIT_EXCEEDED",
            title="Превышен лимит запросов",
            detail=detail,
            status_code=429,
            extra=extra,
        )


class AgentBudgetExceededError(AppError):
    """HTTP 503 Service Unavailable when dialog or daily AI budget limit is reached."""

    def __init__(
        self,
        detail: str = "Превышен лимит расходов на ИИ-агента. Доступен базовый поиск.",
        extra: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            code="AGENT_BUDGET_EXCEEDED",
            title="Превышен бюджет запросов агента",
            detail=detail,
            status_code=503,
            extra=extra,
        )


async def rfc7807_exception_handler(request: Request, exc: AppError) -> JSONResponse:
    """RFC 7807 compliant exception handler for FastAPI."""
    req_id = request_id_ctx_var.get() or request.headers.get("X-Request-ID")

    problem_body: dict[str, Any] = {
        "type": exc.type_uri,
        "title": exc.title,
        "status": exc.status_code,
        "detail": exc.detail,
        "instance": str(request.url.path),
        "code": exc.code,
        "request_id": req_id,
    }

    if exc.errors is not None:
        problem_body["errors"] = exc.errors

    if exc.extra:
        problem_body.update(exc.extra)

    return JSONResponse(
        status_code=exc.status_code,
        content=problem_body,
        media_type="application/problem+json",
    )
