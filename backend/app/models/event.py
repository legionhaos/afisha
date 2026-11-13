import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, CheckConstraint, Computed, DateTime, Enum, Index, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.enums import EventCategory, EventStatus, SourceType


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (
        CheckConstraint("age_limit IN (0, 6, 12, 16, 18)", name="ck_events_age_limit"),
        Index("ix_events_normalized_title_trgm", "normalized_title", postgresql_using="gin", postgresql_ops={"normalized_title": "gin_trgm_ops"}),
        Index("ix_events_tags_gin", "tags", postgresql_using="gin"),
        Index("ix_events_tsv_gin", "tsv", postgresql_using="gin"),
        Index("ix_events_embedding_hnsw", "embedding", postgresql_using="hnsw", postgresql_ops={"embedding": "vector_cosine_ops"}, postgresql_with={"m": 16, "ef_construction": 64}),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(Text)
    normalized_title: Mapped[str] = mapped_column(Text, index=True)
    category: Mapped[EventCategory] = mapped_column(Enum(EventCategory, name="eventcategory"), index=True)
    tags: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    date_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    date_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_min: Mapped[int | None] = mapped_column(Integer)
    city: Mapped[str] = mapped_column(String(120), index=True)
    venue: Mapped[str] = mapped_column(String(255), index=True)
    address: Mapped[str] = mapped_column(Text)
    lat: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    lon: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    description: Mapped[str] = mapped_column(Text)
    price_min: Mapped[int] = mapped_column(Integer, default=0)
    price_max: Mapped[int] = mapped_column(Integer, default=0)
    is_free: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    age_limit: Mapped[int] = mapped_column(Integer, default=0, index=True)
    language: Mapped[str | None] = mapped_column(String(64), index=True)
    org_link: Mapped[str | None] = mapped_column(Text)
    source_url: Mapped[str] = mapped_column(Text)
    source_type: Mapped[SourceType] = mapped_column(Enum(SourceType, name="sourcetype"))
    source_hash: Mapped[str] = mapped_column(String(64), unique=True)
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    confidence: Mapped[Decimal] = mapped_column(Numeric(3, 2), default=1)
    status: Mapped[EventStatus] = mapped_column(Enum(EventStatus, name="eventstatus"), default=EventStatus.PUBLISHED, index=True)
    dedup_key: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    is_disputed: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    dispute_reason: Mapped[str | None] = mapped_column(Text)
    tsv: Mapped[Any] = mapped_column(TSVECTOR, Computed("to_tsvector('russian'::regconfig, coalesce(title, '') || ' ' || coalesce(description, '') || ' ' || coalesce(venue, ''))", persisted=True))
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1536))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    raw_sources: Mapped[list["RawEventRecord"]] = relationship(back_populates="event", lazy="selectin")

    @property
    def sources(self) -> list["RawEventRecord"]:
        return self.raw_sources

    @property
    def cancelled_badge(self) -> str | None:
        if self.status == EventStatus.CANCELLED:
            return "Внимание: мероприятие отменено организатором"
        return None
