from typing import Annotated, Any

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session
from app.core.circuit_breaker import LLMCircuitBreaker, llm_circuit_breaker

router = APIRouter(tags=["health"])


@router.get("/health", summary="Проверка состояния здоровья сервиса")
async def health_check(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> dict[str, Any]:
    db_status = "connected"
    try:
        await session.execute(text("SELECT 1"))
    except Exception as e:
        db_status = f"disconnected: {str(e)}"

    cb_state = llm_circuit_breaker.state.value
    is_healthy = db_status == "connected" and cb_state != "OPEN"

    return {
        "status": "ok" if is_healthy else "degraded",
        "database": db_status,
        "circuit_breaker": cb_state,
        "version": "0.1.0",
    }
