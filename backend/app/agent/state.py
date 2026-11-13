import operator
from typing import Annotated, Any, TypedDict
from langchain_core.messages import BaseMessage


class AgentGraphState(TypedDict):
    """Типизированное состояние графа рассуждений агента LangGraph (ReAct)."""

    # Список сообщений с редьюсером operator.add для предотвращения перезаписи контекста
    messages: Annotated[list[BaseMessage], operator.add]

    thread_id: str
    user_identifier: str
    request_id: str

    # Счетчик шагов ReAct (жесткий лимит 5 шагов по ТЗ)
    step_count: int
    tool_call_count: int

    # Накопители трассировки выполнения
    plan_steps: Annotated[list[str], operator.add]
    tool_executions: Annotated[list[dict[str, Any]], operator.add]
    grounding_event_ids: Annotated[list[str], operator.add]

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
    recommendations: list[dict[str, Any]]
