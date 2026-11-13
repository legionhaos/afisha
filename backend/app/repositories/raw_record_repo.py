from collections.abc import AsyncGenerator
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select, tuple_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import SourceType
from app.models.raw_record import RawEventRecord


class RawRecordRepository:
    """Репозиторий для изоляции и хранения сырых записей источников."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_hash(self, source_hash: str) -> RawEventRecord | None:
        """Проверяет наличие сырой записи по хешу (для 100% идемпотентности импорта)."""
        stmt = select(RawEventRecord).where(RawEventRecord.source_hash == source_hash)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def save_raw_record(
        self,
        source_type: SourceType,
        source_url: str,
        source_hash: str,
        raw_payload: dict[str, Any],
        imported_by: str | None = None,
        processed_event_id: UUID | None = None,
    ) -> RawEventRecord | None:
        """Атомарно сохраняет неизмененный источник или пропускает дубликат."""
        stmt = (insert(RawEventRecord).values(
            id=uuid4(), source_type=source_type, source_url=source_url,
            source_hash=source_hash, raw_payload=raw_payload, imported_by=imported_by,
            processed_event_id=processed_event_id,
        ).on_conflict_do_nothing(index_elements=[RawEventRecord.source_hash])
          .returning(RawEventRecord))
        return await self.session.scalar(stmt)

    async def update_processed_event_id(self, record_id: UUID, event_id: UUID) -> None:
        """Связывает сырую запись с обработанной карточкой Event."""
        record = await self.session.get(RawEventRecord, record_id)
        if record:
            record.processed_event_id = event_id
            await self.session.flush()

    async def list_all_for_replay(
        self,
        batch_size: int = 100,
    ) -> AsyncGenerator[list[RawEventRecord], None]:
        """Потоковая выгрузка сырых записей для переигрывания нормализации."""
        if batch_size < 1:
            raise ValueError("batch_size должен быть положительным")
        cursor = None
        while True:
            stmt = (select(RawEventRecord)
                    .order_by(RawEventRecord.created_at.asc(), RawEventRecord.id.asc())
                    .limit(batch_size))
            if cursor is not None:
                stmt = stmt.where(tuple_(RawEventRecord.created_at, RawEventRecord.id) > tuple_(*cursor))
            result = await self.session.execute(stmt)
            batch = list(result.scalars().all())
            if not batch:
                break
            cursor = (batch[-1].created_at, batch[-1].id)
            yield batch
