from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, Query, UploadFile

from app.api.deps import (
    get_audit_repo,
    get_catalog_service,
    get_crawler_service,
    get_event_repo,
    get_import_service,
    get_request_id,
    require_admin_token,
)
from app.core.exceptions import EventNotFoundError
from app.models.enums import EventStatus
from app.repositories.audit_trace_repo import AuditTraceRepository
from app.repositories.event_repo import EventRepository
from app.schemas.event import EventCardDTO, EventUpdateAdminDTO, PaginatedEventsResponseDTO
from app.schemas.import_mod import ImportReportDTO
from app.services.catalog_service import CatalogService
from app.services.crawler_service import CrawlerService
from app.services.import_service import ImportService

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post(
    "/import",
    response_model=ImportReportDTO,
    summary="Идемпотентный импорт мероприятий из файла CSV или JSON",
)
async def import_events_file(
    file: Annotated[UploadFile, File(...)],
    import_service: Annotated[ImportService, Depends(get_import_service)],
    admin_token: Annotated[str, Depends(require_admin_token)],
    request_id: Annotated[str, Depends(get_request_id)],
) -> ImportReportDTO:
    content = await file.read()
    return await import_service.import_file(
        file_bytes=content,
        filename=file.filename or "upload.csv",
        actor_id="admin_user",
        request_id=request_id,
    )


@router.post(
    "/crawl",
    summary="Запуск сбора и обновления мероприятий из внешних источников (Уровень 4: 6.5 ТЗ)",
)
async def crawl_external_events(
    crawler_service: Annotated[CrawlerService, Depends(get_crawler_service)],
    admin_token: Annotated[str, Depends(require_admin_token)],
    request_id: Annotated[str, Depends(get_request_id)],
    verify_urls: bool = Query(default=False, description="Проверять ли доступность ссылок на источник"),
) -> dict[str, Any]:
    return await crawler_service.crawl_and_import(
        actor_id="admin_user",
        request_id=request_id,
        verify_urls=verify_urls,
    )


@router.post(
    "/replay-normalization",
    response_model=ImportReportDTO,
    summary="Переигровка нормализации по сохраненным сырым записям",
)
async def replay_normalization(
    import_service: Annotated[ImportService, Depends(get_import_service)],
    admin_token: Annotated[str, Depends(require_admin_token)],
    request_id: Annotated[str, Depends(get_request_id)],
) -> ImportReportDTO:
    return await import_service.replay_all_normalizations(
        actor_id="admin_user",
        request_id=request_id,
    )


@router.get(
    "/moderation",
    response_model=PaginatedEventsResponseDTO,
    summary="Очередь модерации спорных карточек и черновиков",
)
async def get_moderation_queue(
    event_repo: Annotated[EventRepository, Depends(get_event_repo)],
    catalog: Annotated[CatalogService, Depends(get_catalog_service)],
    admin_token: Annotated[str, Depends(require_admin_token)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=50),
) -> PaginatedEventsResponseDTO:
    items, total = await event_repo.list_moderation_queue(page=page, page_size=page_size)
    cards = [catalog._to_card_dto(e) for e in items]
    return PaginatedEventsResponseDTO(
        items=cards,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.patch(
    "/events/{event_id}",
    response_model=EventCardDTO,
    summary="Модерация или снятие события (перевод в CANCELLED)",
)
async def moderate_event(
    event_id: UUID,
    dto: EventUpdateAdminDTO,
    event_repo: Annotated[EventRepository, Depends(get_event_repo)],
    audit_repo: Annotated[AuditTraceRepository, Depends(get_audit_repo)],
    catalog: Annotated[CatalogService, Depends(get_catalog_service)],
    admin_token: Annotated[str, Depends(require_admin_token)],
    request_id: Annotated[str, Depends(get_request_id)],
) -> EventCardDTO:
    event = await event_repo.get_by_id(event_id, include_cancelled=True)
    if not event:
        raise EventNotFoundError(event_id=str(event_id))

    old_status = event.status.value
    if dto.status:
        event.status = dto.status
    if dto.is_disputed is not None:
        event.is_disputed = dto.is_disputed
    if dto.title:
        event.title = dto.title
        event.normalized_title = dto.title.lower()

    await event_repo.session.flush()

    # Журналирование изменения
    await audit_repo.log_change(
        request_id=request_id,
        actor_id=dto.moderator_actor,
        action="moderate_event",
        entity_type="event",
        entity_id=event.id,
        changes={
            "old_status": old_status,
            "new_status": event.status.value,
            "is_disputed": event.is_disputed,
        },
    )

    return catalog._to_card_dto(event)


@router.get(
    "/audit-logs",
    summary="Журнал аудита действий модераторов и системы",
)
async def list_audit_logs(
    audit_repo: Annotated[AuditTraceRepository, Depends(get_audit_repo)],
    admin_token: Annotated[str, Depends(require_admin_token)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
) -> dict[str, Any]:
    items, total = await audit_repo.list_audit_logs(page=page, page_size=page_size)
    return {
        "items": [
            {
                "id": str(log.id),
                "request_id": log.request_id,
                "actor_id": log.actor_id,
                "action": log.action,
                "entity_type": log.entity_type,
                "entity_id": str(log.entity_id),
                "changes": log.changes,
                "created_at": log.created_at.isoformat(),
            }
            for log in items
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get(
    "/traces/{trace_id}",
    summary="Просмотр полной трассы рассуждений и инструментов ИИ-агента",
)
async def get_agent_trace_by_id(
    trace_id: UUID,
    audit_repo: Annotated[AuditTraceRepository, Depends(get_audit_repo)],
    admin_token: Annotated[str, Depends(require_admin_token)],
) -> dict[str, Any]:
    trace = await audit_repo.get_agent_trace(trace_id)
    if not trace:
        raise EventNotFoundError(detail=f"Трасса {trace_id} не найдена")

    return {
        "id": str(trace.id),
        "request_id": trace.request_id,
        "thread_id": trace.thread_id,
        "user_query": trace.user_query,
        "plan_steps": trace.plan_steps,
        "tool_calls": trace.tool_calls,
        "grounding_event_ids": [str(gid) for gid in trace.grounding_event_ids],
        "latency_ms": trace.latency_ms,
        "prompt_tokens": trace.prompt_tokens,
        "completion_tokens": trace.completion_tokens,
        "estimated_cost_rub": float(trace.estimated_cost_rub),
        "fallback_used": trace.fallback_used,
        "created_at": trace.created_at.isoformat(),
    }
