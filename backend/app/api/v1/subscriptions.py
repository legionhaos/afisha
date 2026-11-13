from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import get_sub_repo
from app.repositories.subscription_repo import SubscriptionRepository
from app.schemas.subscription import SubscriptionCreateDTO, SubscriptionReadDTO

router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])


@router.post(
    "",
    response_model=SubscriptionReadDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Оформление подписки на мероприятия",
)
async def create_subscription(
    dto: SubscriptionCreateDTO,
    sub_repo: Annotated[SubscriptionRepository, Depends(get_sub_repo)],
) -> SubscriptionReadDTO:
    sub = await sub_repo.upsert_subscription(
        user_identifier=dto.user_identifier,
        telegram_chat_id=dto.telegram_chat_id,
        city=dto.city,
        category=dto.category,
        period_type=dto.period_type,
    )
    return SubscriptionReadDTO.model_validate(sub)


@router.get(
    "",
    response_model=list[SubscriptionReadDTO],
    summary="Список активных подписок пользователя",
)
async def list_user_subscriptions(
    user_identifier: str = Query(..., min_length=2),
    sub_repo: Annotated[SubscriptionRepository, Depends(get_sub_repo)] = None,
) -> list[SubscriptionReadDTO]:
    items = await sub_repo.list_by_user(user_identifier)
    return [SubscriptionReadDTO.model_validate(item) for item in items]


@router.delete(
    "/{user_identifier}",
    summary="Отписка от уведомлений (одной подписки или всех сразу командой /unsubscribe)",
)
async def delete_subscriptions(
    user_identifier: str,
    subscription_id: UUID | None = Query(default=None, description="Опциональный ID конкретной подписки. Если не передан — удаляются все подписки"),
    sub_repo: Annotated[SubscriptionRepository, Depends(get_sub_repo)] = None,
) -> dict[str, int]:
    deleted_count = await sub_repo.delete_by_user(user_identifier, subscription_id)
    return {"deleted": deleted_count}
