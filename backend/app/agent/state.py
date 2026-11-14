from typing import Annotated, Any, TypedDict
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class AgentGraphState(TypedDict):
    """Типизированное состояние графа рассуждений агента LangGraph (ReAct)."""

    # История обновляется по ID сообщений, что позволяет ограничивать размер диалога.
    messages: Annotated[list[BaseMessage], add_messages]

    thread_id: str
    user_identifier: str
    request_id: str

    # Счетчик шагов ReAct (жесткий лимит 5 шагов по ТЗ)
    step_count: int
    tool_call_count: int
    search_complete: bool

    # Накопители трассировки выполнения
    plan_steps: list[str]
    tool_executions: list[dict[str, Any]]
    grounding_event_ids: list[str]

    # Словарь проверенных карточек, полученных строго из БД через инструменты: {event_id_str: event_dict}
    verified_cards_map: dict[str, dict[str, Any]]

    # Флаги двухфазного подтверждения модифицирующих действий
    requires_confirmation: bool
    pending_action: dict[str, Any] | None

    # Ровно 1 уточняющий вопрос при неоднозначности
    clarifying_question: str | None

    # Метрики токенов и расходов
    prompt_tokens: int
    completion_tokens: int

    # Флаги маршрутизации и безопасности
    fallback_triggered: bool
    injection_detected: bool

    # Финальные результаты
    final_response_text: str | None
    final_structured_output: dict[str, Any] | None
    recommendations: list[dict[str, Any]]
