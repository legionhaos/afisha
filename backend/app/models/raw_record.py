from datetime import datetime
from typing import Any
from uuid import UUID, uuid4
from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.enums import SourceType


class RawEventRecord(Base):
    """Сырые данные источника, изолированные от нормализованных карточек.

    Позволяет переигрывать нормализацию без повторного сбора с внешних сайтов.
    """
    __tablename__ = "raw_event_records"
    __table_args__ = (Index("ix_raw_event_records_replay_cursor", "created_at", "id"),)

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    source_type: Mapped[SourceType] = mapped_column(
        Enum(SourceType, name="source_type_enum", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    source_url: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    source_hash: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        nullable=False,
        index=True,
    )
    raw_payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
    )
    imported_by: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    processed_event_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("events.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
