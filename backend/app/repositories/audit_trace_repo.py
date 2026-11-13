from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_trace import AgentTrace, AuditLog


class AuditTraceRepository:
    """Репозиторий аудита изменений и трассировки ответов ИИ-агента."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def log_change(
        self,
        request_id: str,
        actor_id: str,
        action: str,
        entity_type: str,
        entity_id: UUID,
        changes: dict[str, Any],
    ) -> AuditLog:
        """Записывает изменение в неизменяемый журнал аудита."""
        log_entry = AuditLog(
            id=uuid4(),
            request_id=request_id,
            actor_id=actor_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            changes=changes,
        )
        self.session.add(log_entry)
        await self.session.flush()
        return log_entry

    async def list_audit_logs(
        self,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[AuditLog], int]:
        """Возвращает журнал аудита для панели администратора."""
        count_stmt = select(func.count(AuditLog.id))
        total_res = await self.session.execute(count_stmt)
        total = total_res.scalar() or 0

        offset = (page - 1) * page_size
        stmt = (
            select(AuditLog)
            .order_by(AuditLog.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all()), total

    async def save_agent_trace(self, trace_data: dict[str, Any]) -> AgentTrace:
        """Сохраняет полную трассу шагов рассуждения и инструментов агента."""
        trace = AgentTrace(
            id=trace_data.get("id") or uuid4(),
            request_id=trace_data["request_id"],
            thread_id=trace_data["thread_id"],
            user_query=trace_data["user_query"],
            plan_steps=trace_data.get("plan_steps", []),
            tool_calls=trace_data.get("tool_calls", []),
            grounding_event_ids=trace_data.get("grounding_event_ids", []),
            latency_ms=trace_data.get("latency_ms", 0),
            prompt_tokens=trace_data.get("prompt_tokens", 0),
            completion_tokens=trace_data.get("completion_tokens", 0),
            estimated_cost_rub=trace_data.get("estimated_cost_rub", Decimal("0.0000")),
            fallback_used=trace_data.get("fallback_used", False),
        )
        self.session.add(trace)
        await self.session.flush()
        return trace

    async def get_agent_trace(self, trace_id: UUID) -> AgentTrace | None:
        """Возвращает запись трассировки по ID для проверки обоснованности фактов."""
        stmt = select(AgentTrace).where(AgentTrace.id == trace_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_user_daily_spend_rub(self, user_thread_prefix: str) -> float:
        """Считает сумму расходов пользователя за текущие сутки для контроля лимита 25 рублей."""
        today_start = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        stmt = select(func.coalesce(func.sum(AgentTrace.estimated_cost_rub), Decimal("0.0000"))).where(
            AgentTrace.thread_id.like(f"%{user_thread_prefix}%"),
            AgentTrace.created_at >= today_start,
        )
        result = await self.session.execute(stmt)
        val = result.scalar() or Decimal("0.0000")
        return float(val)
