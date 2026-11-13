from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from app.api.deps import get_agent_orchestrator, get_request_id, get_trusted_telegram_user
from app.agent.orchestrator import CulturalAgentOrchestrator
from app.schemas.chat import ChatMessageRequestDTO, ChatMessageResponseDTO

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post(
    "",
    response_model=ChatMessageResponseDTO,
    summary="Синхронный диалог с интеллектуальным агентом",
    description="Основной эндпоинт для Telegram-бота и синхронных клиентов. Возвращает ответ и проверенные карточки.",
)
async def chat_message_sync(
    req: ChatMessageRequestDTO,
    request: Request,
    orchestrator: Annotated[CulturalAgentOrchestrator, Depends(get_agent_orchestrator)],
    request_id: Annotated[str, Depends(get_request_id)],
    telegram_user: Annotated[str | None, Depends(get_trusted_telegram_user)],
) -> ChatMessageResponseDTO:
    return await orchestrator.invoke_chat(req, request_id, telegram_user=telegram_user)


@router.post(
    "/stream",
    summary="Потоковый Server-Sent Events (SSE) диалог с агентом",
    description="Потоковый вывод токенов и карточек для веб-интерфейса и виджета с отправкой heartbeat каждые 10 секунд.",
)
async def chat_message_stream(
    req: ChatMessageRequestDTO,
    request: Request,
    orchestrator: Annotated[CulturalAgentOrchestrator, Depends(get_agent_orchestrator)],
    request_id: Annotated[str, Depends(get_request_id)],
    telegram_user: Annotated[str | None, Depends(get_trusted_telegram_user)],
) -> StreamingResponse:
    generator = orchestrator.stream_chat_sse(req, request_id, telegram_user=telegram_user)
    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disables proxy buffering in Nginx
        },
    )
