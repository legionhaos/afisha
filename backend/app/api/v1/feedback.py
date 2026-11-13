from typing import Annotated

from fastapi import APIRouter, Depends, Request, status

from app.api.deps import get_feedback_repo, require_admin_token
from app.core.exceptions import RateLimitExceededError, ValidationFailedError
from app.core.security import security_service
from app.models.enums import FeedbackStatus
from app.repositories.feedback_repo import FeedbackRepository
from app.schemas.feedback import FeedbackCreateDTO, FeedbackReadDTO

router = APIRouter(prefix="/feedback", tags=["feedback"])


@router.post(
    "",
    response_model=FeedbackReadDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Отправка обращения от жителя или организатора",
)
async def submit_feedback(
    dto: FeedbackCreateDTO,
    request: Request,
    feedback_repo: Annotated[FeedbackRepository, Depends(get_feedback_repo)],
) -> FeedbackReadDTO:
    # 1. Защита от спам-ботов через honeypot
    if dto.honeypot.strip():
        raise ValidationFailedError(detail="Спам-запрос заблокирован")

    # 2. Rate Limiting (не более 5 заявок за 10 минут с одного клиента)
    client_ip = request.client.host if request.client else "unknown_client"
    allowed = await security_service.check_rate_limit(f"feedback_{client_ip}", limit=5, window_sec=600)
    if not allowed:
        raise RateLimitExceededError(detail="Слишком много обращений. Пожалуйста, подождите перед следующей отправкой.")

    ticket = await feedback_repo.create_feedback(
        sender_identifier=dto.sender_identifier,
        message_text=dto.message_text,
        event_id=dto.event_id,
    )
    return FeedbackReadDTO.model_validate(ticket)


@router.get(
    "",
    response_model=list[FeedbackReadDTO],
    summary="Просмотр тикетов обратной связи (для администратора)",
)
async def list_feedback_tickets(
    feedback_repo: Annotated[FeedbackRepository, Depends(get_feedback_repo)],
    admin_token: Annotated[str, Depends(require_admin_token)],
    status: FeedbackStatus | None = None,
    page: int = 1,
    page_size: int = 50,
) -> list[FeedbackReadDTO]:
    items, total = await feedback_repo.list_feedback(status=status, page=page, page_size=page_size)
    return [FeedbackReadDTO.model_validate(t) for t in items]
