"""State shared between LangGraph nodes."""

import operator
from typing import Annotated, Any, TypedDict

from langchain_core.messages import BaseMessage


class AgentGraphState(TypedDict):
    messages: Annotated[list[BaseMessage], operator.add]
    thread_id: str
    user_identifier: str
    request_id: str
    step_count: int
    plan_steps: list[str]
    tool_Executions: list[dict[str, Any]]
    grounding_event_ids: list[str]
    started_monotonic: float
    daily_spend_rub: float
    blocked_input: bool
    verified_cards_map: dict[str, dict[str, Any]]
    requires_confirmation: bool
    pending_action: dict[str, Any] | None
    prompt_tokens: int
    completion_tokens: int
    fallback_triggered: bool
    final_structured_output: dict[str, Any] | None
