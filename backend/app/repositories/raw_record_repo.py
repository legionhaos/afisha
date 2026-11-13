from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert

from app.models.enums import SourceType
from app.models.raw_record import RawEventRecord


class RawRecordRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_hash(self, source_hash: str) -> RawEventRecord | None:
        return await self.session.scalar(select(RawEventRecord).where(RawEventRecord.source_hash == source_hash))

    async def save_raw_record(self, source_type: SourceType, source_url: str, source_hash: str, raw_payload: dict[str, Any], imported_by: str) -> RawEventRecord | None:
        stmt = (
            insert(RawEventRecord)
            .values(source_type=source_type, source_url=source_url, source_hash=source_hash, raw_payload=raw_payload)
            .on_conflict_do_nothing(index_elements=[RawEventRecord.source_hash])
            .returning(RawEventRecord)
        )
        return await self.session.scalar(stmt)

    async def list_all_for_replay(self, batch_size: int = 100) -> AsyncGenerator[list[RawEventRecord], None]:
        if batch_size < 1:
            raise ValueError("batch_size must be positive")
        result = await self.session.stream_scalars(
            select(RawEventRecord).order_by(RawEventRecord.ingested_at, RawEventRecord.id)
            .execution_options(yield_per=batch_size)
        )
        try:
            async for batch in result.partitions(batch_size):
                yield list(batch)
        finally:
            await result.close()
