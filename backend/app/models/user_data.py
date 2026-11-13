from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import BigInteger, Boolean, DateTime, Enum, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.enums import EventCategory, FeedbackStatus


class Subscription(Base):
    """Подписка пользователя на уведомления по городу и категории."""
    __tablename__ = "subscriptions"
    __table_args__ = (
        UniqueConstraint("user_identifier", "city", "category", name="uq_subscription_user_city_category"),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    user_identifier: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        index=True,
    )
    # Telegram Chat ID strictly as BigInteger (BIGINT in PostgreSQL) to prevent 32-bit overflow
    telegram_chat_id: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
        index=True,
    )
    city: Mapped[str] = mapped_column(
        String(120),
        nullable=False,
        index=True,
    )
    category: Mapped[EventCategory | None] = mapped_column(
        Enum(EventCategory, name="event_category_enum", values_callable=lambda x: [e.value for e in x]),
        nullable=True,
        index=True,
    )
    period_type: Mapped[str] = mapped_column(
        String(32),
        default="all",
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )


class FeedbackRequest(Base):
    """Обращение или уточнение от организатора или жителя."""
    __tablename__ = "feedback_requests"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    event_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("events.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    sender_identifier: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
    )
    message_text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    status: Mapped[FeedbackStatus] = mapped_column(
        Enum(FeedbackStatus, name="feedback_status_enum", values_callable=lambda x: [e.value for e in x]),
        default=FeedbackStatus.NEW,
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
