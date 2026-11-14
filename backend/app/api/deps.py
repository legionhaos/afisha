import hmac
from collections.abc import AsyncGenerator
from typing import Annotated
from uuid import uuid4

from fastapi import Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.orchestrator import CulturalAgentOrchestrator
from app.core.config import Settings, get_settings
from app.core.database import db_manager
from app.core.exceptions import UnauthorizedAdminError
from app.core.logging import request_id_ctx_var
from app.core.security import SecurityService
from app.repositories.audit_trace_repo import AuditTraceRepository
from app.repositories.dictionary_repo import DictionaryRepository
from app.repositories.event_repo import EventRepository
from app.repositories.feedback_repo import FeedbackRepository
from app.repositories.raw_record_repo import RawRecordRepository
from app.repositories.subscription_repo import SubscriptionRepository
from app.services.catalog_service import CatalogService
from app.services.embedding_service import embedding_service
from app.services.fallback_search_service import FallbackSearchService
from app.services.import_service import ImportService
from app.services.crawler_service import CrawlerService


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency injecting an asynchronous SQLAlchemy session."""
    if db_manager._sessionmaker is None:
        await db_manager.init_pools()
    async with db_manager.sessionmaker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


def get_trusted_telegram_user(
    x_bot_token: Annotated[str | None, Header(alias="X-Bot-Token")] = None,
    x_telegram_user_id: Annotated[str | None, Header(alias="X-Telegram-User-Id")] = None,
    settings: Settings = Depends(get_settings),
) -> str | None:
    """Accept a Telegram identity only from the configured trusted bot backend."""
    expected = settings.TELEGRAM_BACKEND_TOKEN.get_secret_value()
    if not expected or not x_bot_token or not hmac.compare_digest(
        x_bot_token.encode(), expected.encode()
    ):
        return None
    if (not x_telegram_user_id or len(x_telegram_user_id) > 19
            or not x_telegram_user_id.isascii() or not x_telegram_user_id.isdecimal()):
        return None
    telegram_id = int(x_telegram_user_id)
    if not 0 < telegram_id <= 2**63 - 1:
        return None
    return str(telegram_id)


def get_request_id(request: Request) -> str:
    """Retrieves or generates X-Request-ID for tracing."""
    req_id = request.headers.get("X-Request-ID") or uuid4().hex
    request_id_ctx_var.set(req_id)
    return req_id


def get_event_repo(session: Annotated[AsyncSession, Depends(get_db_session)]) -> EventRepository:
    return EventRepository(session)


def get_dict_repo(session: Annotated[AsyncSession, Depends(get_db_session)]) -> DictionaryRepository:
    return DictionaryRepository(session)


def get_raw_repo(session: Annotated[AsyncSession, Depends(get_db_session)]) -> RawRecordRepository:
    return RawRecordRepository(session)


def get_sub_repo(session: Annotated[AsyncSession, Depends(get_db_session)]) -> SubscriptionRepository:
    return SubscriptionRepository(session)


def get_feedback_repo(session: Annotated[AsyncSession, Depends(get_db_session)]) -> FeedbackRepository:
    return FeedbackRepository(session)


def get_audit_repo(session: Annotated[AsyncSession, Depends(get_db_session)]) -> AuditTraceRepository:
    return AuditTraceRepository(session)


def get_catalog_service(
    event_repo: Annotated[EventRepository, Depends(get_event_repo)],
    dict_repo: Annotated[DictionaryRepository, Depends(get_dict_repo)],
) -> CatalogService:
    return CatalogService(event_repo=event_repo, dict_repo=dict_repo, emb_service=embedding_service)


def get_fallback_service(
    catalog_service: Annotated[CatalogService, Depends(get_catalog_service)],
    dict_repo: Annotated[DictionaryRepository, Depends(get_dict_repo)],
    audit_repo: Annotated[AuditTraceRepository, Depends(get_audit_repo)],
) -> FallbackSearchService:
    return FallbackSearchService(
        catalog_service=catalog_service,
        dict_repo=dict_repo,
        audit_repo=audit_repo,
    )


def get_import_service(
    event_repo: Annotated[EventRepository, Depends(get_event_repo)],
    raw_repo: Annotated[RawRecordRepository, Depends(get_raw_repo)],
    dict_repo: Annotated[DictionaryRepository, Depends(get_dict_repo)],
    audit_repo: Annotated[AuditTraceRepository, Depends(get_audit_repo)],
) -> ImportService:
    return ImportService(
        event_repo=event_repo,
        raw_repo=raw_repo,
        dict_repo=dict_repo,
        audit_repo=audit_repo,
        emb_service=embedding_service,
    )


def get_crawler_service(
    import_service: Annotated[ImportService, Depends(get_import_service)],
) -> CrawlerService:
    return CrawlerService(import_service=import_service)


def get_agent_orchestrator(
    event_repo: Annotated[EventRepository, Depends(get_event_repo)],
    dict_repo: Annotated[DictionaryRepository, Depends(get_dict_repo)],
    sub_repo: Annotated[SubscriptionRepository, Depends(get_sub_repo)],
    feedback_repo: Annotated[FeedbackRepository, Depends(get_feedback_repo)],
    audit_repo: Annotated[AuditTraceRepository, Depends(get_audit_repo)],
    catalog_service: Annotated[CatalogService, Depends(get_catalog_service)],
    fallback_service: Annotated[FallbackSearchService, Depends(get_fallback_service)],
) -> CulturalAgentOrchestrator:
    return CulturalAgentOrchestrator(
        event_repo=event_repo,
        dict_repo=dict_repo,
        sub_repo=sub_repo,
        feedback_repo=feedback_repo,
        audit_repo=audit_repo,
        catalog_service=catalog_service,
        fallback_service=fallback_service,
    )


def require_admin_token(
    x_admin_token: Annotated[str | None, Header(alias="X-Admin-Token")] = None,
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
    settings: Annotated[Settings, Depends(get_settings)] = None,
) -> str:
    """Dependency verifying administrator secret token."""
    token = x_admin_token
    if not token and authorization:
        if authorization.lower().startswith("bearer "):
            token = authorization[7:].strip()
        else:
            token = authorization.strip()

    expected = settings.ADMIN_API_TOKEN.get_secret_value()
    if not token or not SecurityService.verify_admin_token(token, expected):
        raise UnauthorizedAdminError()

    return token
