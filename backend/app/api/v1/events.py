from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Response, status
from fastapi.responses import Response as FastApiResponse

from app.api.deps import get_catalog_service
from app.schemas.event import EventCardDTO, EventSearchFilterDTO, PaginatedEventsResponseDTO
from app.services.catalog_service import CatalogService

router = APIRouter(prefix="/events", tags=["events"])


@router.get(
    "",
    response_model=PaginatedEventsResponseDTO,
    summary="Поиск и фильтрация мероприятий каталога",
    description="Возвращает пагинированный список событий с поддержкой гибридного поиска и объяснением пустой выдачи.",
)
async def list_events(
    response: Response,
    filters: Annotated[EventSearchFilterDTO, Query()],
    catalog: Annotated[CatalogService, Depends(get_catalog_service)],
) -> PaginatedEventsResponseDTO:
    result = await catalog.search_catalog(filters)
    # HTTP Cache-Control header for catalog search
    response.headers["Cache-Control"] = "public, max-age=60"
    return result


@router.get(
    "/{event_id}",
    response_model=EventCardDTO,
    summary="Получение детальной карточки мероприятия",
    description="Возвращает полную карточку события. Отмененные события возвращаются со статусом cancelled и пометкой.",
)
async def get_event_detail(
    event_id: UUID,
    response: Response,
    catalog: Annotated[CatalogService, Depends(get_catalog_service)],
    if_none_match: Annotated[str | None, Header(alias="If-None-Match")] = None,
) -> Any:
    card = await catalog.get_event_card(event_id)

    # Compute ETag based on event ID, status, and verification timestamp
    etag = f'"{card.id}-{int(card.verified_at.timestamp())}-{card.status.value}"'
    response.headers["ETag"] = etag
    response.headers["Cache-Control"] = "public, max-age=60"

    if if_none_match and if_none_match.strip() == etag:
        return FastApiResponse(status_code=status.HTTP_304_NOT_MODIFIED)

    return card
