from typing import Any, Generic, TypeVar
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from app.models.base import Base

ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType]):
    """Базовый асинхронный репозиторий для операций с БД."""

    def __init__(self, session: AsyncSession, model: type[ModelType]) -> None:
        self.session = session
        self.model = model

    async def get_by_id(self, entity_id: UUID) -> ModelType | None:
        stmt = select(self.model).where(self.model.id == entity_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def delete_by_id(self, entity_id: UUID) -> bool:
        stmt = delete(self.model).where(self.model.id == entity_id)
        result = await self.session.execute(stmt)
        return result.rowcount > 0
