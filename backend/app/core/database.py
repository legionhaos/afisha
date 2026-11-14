from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import Settings, get_settings


class DatabaseManager:
    """Manages SQLAlchemy 2.0 engine/sessions and psycopg_pool for LangGraph checkpointer."""

    def __init__(self) -> None:
        self._engine: AsyncEngine | None = None
        self._sessionmaker: async_sessionmaker[AsyncSession] | None = None
        self._checkpointer_pool: AsyncConnectionPool | None = None
        self._checkpointer: Any = None

    async def init_pools(self, settings: Settings | None = None) -> None:
        if settings is None:
            settings = get_settings()

        # 1. SQLAlchemy 2.0 AsyncEngine & sessionmaker
        # expire_on_commit=False is mandatory to prevent DetachedInstanceError
        self._engine = create_async_engine(
            settings.DATABASE_URL,
            pool_size=20,
            max_overflow=10,
            pool_pre_ping=True,
            echo=False,
        )
        self._sessionmaker = async_sessionmaker(
            bind=self._engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )

        # 2. psycopg_pool for LangGraph AsyncPostgresSaver
        # autocommit=True and row_factory=dict_row are mandatory for AsyncPostgresSaver
        self._checkpointer_pool = AsyncConnectionPool(
            conninfo=settings.CHECKPOINT_DB_URI,
            min_size=2,
            max_size=20,
            kwargs={
                "autocommit": True,
                "row_factory": dict_row,
            },
            open=False,
        )
        await self._checkpointer_pool.open()
        from app.agent.checkpointer import CheckpointerManager
        self._checkpointer = CheckpointerManager.get_checkpointer(self._checkpointer_pool)
        await self._checkpointer.setup()

    async def close_pools(self) -> None:
        if self._checkpointer_pool is not None:
            await self._checkpointer_pool.close()
            self._checkpointer_pool = None
            self._checkpointer = None

        if self._engine is not None:
            await self._engine.dispose()
            self._engine = None
            self._sessionmaker = None

    @property
    def sessionmaker(self) -> async_sessionmaker[AsyncSession]:
        if self._sessionmaker is None:
            raise RuntimeError("DatabaseManager is not initialized. Call init_pools() first.")
        return self._sessionmaker

    @property
    def checkpointer_pool(self) -> AsyncConnectionPool:
        if self._checkpointer_pool is None:
            raise RuntimeError("Checkpointer pool is not initialized. Call init_pools() first.")
        return self._checkpointer_pool

    async def get_db_session(self) -> AsyncGenerator[AsyncSession, None]:
        """FastAPI dependency for obtaining an AsyncSession."""
        if self._sessionmaker is None:
            raise RuntimeError("DatabaseManager is not initialized. Call init_pools() first.")
        async with self._sessionmaker() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()


db_manager = DatabaseManager()
