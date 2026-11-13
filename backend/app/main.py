from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute

from app.api.v1.health import router as health_router
from app.api.v1.router import api_v1_router
from app.core.config import get_settings
from app.core.database import db_manager
from app.core.exceptions import AppError, rfc7807_exception_handler
from app.core.logging import request_id_ctx_var, setup_logging


def custom_generate_unique_id(route: APIRoute) -> str:
    """Генерирует уникальные читаемые идентификаторы операций для OpenAPI 3.1."""
    tag = route.tags[0] if route.tags else "default"
    path_clean = route.path_format.replace("/", "_").replace("{", "").replace("}", "").strip("_")
    return f"{tag}_{route.name}_{path_clean}"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Инициализация пулов базы данных при старте и корректное закрытие при остановке."""
    setup_logging()
    settings = get_settings()
    try:
        await db_manager.init_pools(settings)
    except Exception as e:
        import structlog
        structlog.get_logger(__name__).warning("db_pools_startup_skipped_or_failed", error=str(e))
    yield
    try:
        await db_manager.close_pools()
    except Exception:
        pass


settings = get_settings()

app = FastAPI(
    title=settings.APP_NAME,
    version="0.1.0",
    openapi_url="/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
    generate_unique_id_function=custom_generate_unique_id,
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_security_and_tracing_headers(request: Request, call_next: Any) -> Response:
    """Прокидывает request_id и выставляет заголовок CSP frame-ancestors для виджета."""
    req_id = request.headers.get("X-Request-ID")
    if not req_id:
        from uuid import uuid4
        req_id = uuid4().hex
    request_id_ctx_var.set(req_id)

    response: Response = await call_next(request)

    # Защита виджета: заголовок CSP frame-ancestors
    response.headers["Content-Security-Policy"] = f"frame-ancestors 'self' {settings.ALLOWED_FRAME_ANCESTORS}"
    response.headers["X-Request-ID"] = req_id
    return response


# Регистрация обработчиков ошибок RFC 7807
app.add_exception_handler(AppError, rfc7807_exception_handler)

# Подключение роутеров
app.include_router(api_v1_router, prefix=settings.API_V1_PREFIX)
app.include_router(health_router)
