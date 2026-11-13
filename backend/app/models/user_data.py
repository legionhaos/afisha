import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.enums import EventCategory, SubscriptionChannel


class Subscription(Base):
    __tablename__ = "subscriptions"
    __table_args__ = (UniqueConstraint("channel", "user_identifier", "city", "category", name="uq_subscriptions_identity", postgresql_nulls_not_distinct=True),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    channel: Mapped[SubscriptionChannel] = mapped_column(Enum(SubscriptionChannel, name="subscriptionchannel"))
    user_identifier: Mapped[str] = mapped_column(String(128), index=True)
    city: Mapped[str] = mapped_column(String(120))
    category: Mapped[EventCategory | None] = mapped_column(Enum(EventCategory, name="eventcategory"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FeedbackTicket(Base):
    __tablename__ = "feedback_tickets"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("events.id", ondelete="SET NULL"))
    organizer_contact: Mapped[str] = mapped_column(String(255))
    message: Mapped[str] = mapped_column(Text)
    is_processed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
