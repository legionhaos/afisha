from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from sqlalchemy import and_, delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import EventCategory
from app.models.user_data import Subscription


class SubscriptionRepository:
    """Репозиторий для управления подписками пользователей без лишних ПДн (152-ФЗ)."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def upsert_subscription(
        self,
        user_identifier: str,
        telegram_chat_id: int | None,
        city: str,
        category: EventCategory | None = None,
        period_type: str = "all",
        retention_days: int = 180,
    ) -> Subscription:
        """Создает или обновляет подписку пользователя на город и категорию."""
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(days=retention_days)

        stmt = select(Subscription).where(
            and_(
                Subscription.user_identifier == user_identifier,
                Subscription.city == city,
                Subscription.category == category,
            )
        )
        res = await self.session.execute(stmt)
        existing = res.scalar_one_or_none()

        if existing:
            existing.telegram_chat_id = telegram_chat_id or existing.telegram_chat_id
            existing.period_type = period_type
            existing.is_active = True
            existing.expires_at = expires_at
            await self.session.flush()
            return existing

        sub = Subscription(
            id=uuid4(),
            user_identifier=user_identifier,
            telegram_chat_id=telegram_chat_id,
            city=city,
            category=category,
            period_type=period_type,
            is_active=True,
            created_at=now,
            expires_at=expires_at,
        )
        self.session.add(sub)
        await self.session.flush()
        return sub

    async def list_by_user(self, user_identifier: str) -> list[Subscription]:
        """Возвращает все активные подписки пользователя."""
        stmt = (
            select(Subscription)
            .where(
                and_(
                    Subscription.user_identifier == user_identifier,
                    Subscription.is_active.is_(True),
                )
            )
            .order_by(Subscription.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def delete_by_user(
        self,
        user_identifier: str,
        subscription_id: UUID | None = None,
    ) -> int:
        """Удаляет одну или все подписки пользователя одной командой (/unsubscribe)."""
        stmt = delete(Subscription).where(Subscription.user_identifier == user_identifier)
        if subscription_id is not None:
            stmt = stmt.where(Subscription.id == subscription_id)

        result = await self.session.execute(stmt)
        return result.rowcount
