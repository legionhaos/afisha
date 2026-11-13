from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import FeedbackStatus
from app.models.user_data import FeedbackRequest


class FeedbackRepository:
    """Репозиторий обращений организаторов и жителей."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_feedback(
        self,
        sender_identifier: str,
        message_text: str,
        event_id: UUID | None = None,
    ) -> FeedbackRequest:
        """Сохраняет обращение от жителя или организатора."""
        ticket = FeedbackRequest(
            id=uuid4(),
            event_id=event_id,
            sender_identifier=sender_identifier,
            message_text=message_text,
            status=FeedbackStatus.NEW,
        )
        self.session.add(ticket)
        await self.session.flush()
        return ticket

    async def list_feedback(
        self,
        status: FeedbackStatus | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[FeedbackRequest], int]:
        """Возвращает список обращений с фильтрацией по статусу."""
        stmt_count = select(func.count(FeedbackRequest.id))
        if status:
            stmt_count = stmt_count.where(FeedbackRequest.status == status)
        total_res = await self.session.execute(stmt_count)
        total = total_res.scalar() or 0

        offset = (page - 1) * page_size
        stmt = select(FeedbackRequest)
        if status:
            stmt = stmt.where(FeedbackRequest.status == status)
        stmt = stmt.order_by(FeedbackRequest.created_at.desc()).offset(offset).limit(page_size)

        result = await self.session.execute(stmt)
        return list(result.scalars().all()), total

    async def update_status(
        self,
        feedback_id: UUID,
        new_status: FeedbackStatus,
    ) -> FeedbackRequest | None:
        """Обновляет статус обработки тикета."""
        ticket = await self.session.get(FeedbackRequest, feedback_id)
        if ticket:
            ticket.status = new_status
            await self.session.flush()
        return ticket
