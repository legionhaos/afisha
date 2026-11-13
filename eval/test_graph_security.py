"""Security regressions exercised through the compiled agent graph."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.agent.orchestrator import CulturalAgentOrchestrator
from app.agent.tools import AgentToolsFactory
from app.models.enums import EventStatus


def run_graph(responses, *, confirmed_action_id=None, catalog=None):
    llm = Mock()
    bound = Mock()
    bound.ainvoke = AsyncMock(side_effect=responses)
    llm.bind_tools.return_value = bound
    audit = Mock()
    audit.get_user_daily_spend_rub = AsyncMock(return_value=0)
    breaker = Mock()
    breaker.can_execute.return_value = True

    async def call(fn):
        return await fn()

    breaker.call = AsyncMock(side_effect=call)
    sub_repo, feedback_repo = Mock(), Mock()
    sub_repo.upsert_subscription = AsyncMock()
    feedback_repo.create_feedback = AsyncMock()
    catalog = catalog or Mock()
    agent = CulturalAgentOrchestrator(
        event_repo=Mock(), dict_repo=Mock(), sub_repo=sub_repo,
        feedback_repo=feedback_repo, audit_repo=audit, catalog_service=catalog,
        fallback_service=Mock(),
        settings=SimpleNamespace(MAX_AGENT_STEPS=5, MAX_DAILY_USER_BUDGET_RUB=25),
        circuit_breaker=breaker,
    )
    agent._get_llm = Mock(return_value=llm)
    graph = agent.build_graph("user-1", confirmed_action_id=confirmed_action_id)
    state = asyncio.run(graph.ainvoke({
        "messages": [HumanMessage(content="Найди мероприятия")],
        "user_identifier": "user-1", "thread_id": "thread-1", "request_id": "request-1",
    }))
    return state, bound, sub_repo, feedback_repo


@pytest.mark.asyncio
async def test_get_event_rejects_draft_before_collecting():
    catalog = Mock()
    catalog.get_event_card = AsyncMock(return_value=SimpleNamespace(status=EventStatus.DRAFT))
    collector = Mock()
    factory = AgentToolsFactory(Mock(), Mock(), Mock(), Mock(), catalog, "user", on_card_fetched=collector)
    tool = next(t for t in factory.create_tools() if t.name == "get_event")
    result = json.loads(await tool.ainvoke({"event_id": "11111111-1111-1111-1111-111111111111"}))
    assert result == {"error": "EVENT_NOT_FOUND"}
    collector.assert_not_called()


def test_single_message_cannot_execute_more_than_five_tools():
    catalog = Mock()
    catalog.search_catalog = AsyncMock(return_value=SimpleNamespace(items=[], empty_explanation=None))
    calls = [{"name": "search_events", "args": {}, "id": f"call-{i}"} for i in range(7)]
    state, bound, _, _ = run_graph([
        AIMessage(content="", tool_calls=calls), AIMessage(content="Результаты готовы")
    ], catalog=catalog)
    assert catalog.search_catalog.await_count == 5
    assert state["tool_call_count"] == 5
    messages = [m for m in state["messages"] if isinstance(m, ToolMessage)]
    assert [m.tool_call_id for m in messages] == [c["id"] for c in calls]
    assert all(json.loads(m.content)["error"] == "TOOL_LIMIT_OR_CONFIRMATION_REQUIRED" for m in messages[5:])
    assert bound.ainvoke.await_count == 2


def test_unverified_model_prose_is_not_returned():
    invented = "Концерт на Марсе завтра бесплатно и билеты гарантированы"
    state, _, _, _ = run_graph([AIMessage(content=invented)])
    assert invented not in state["final_response_text"]
    assert state["recommendations"] == []
    assert state["final_response_text"] == "Не удалось подобрать мероприятия. Уточните запрос или повторите поиск."


@pytest.mark.parametrize("tool,args", [
    ("subscribe", {"city": "Уфа"}),
    ("save_feedback", {"message_text": "Обращение"}),
])
def test_arbitrary_confirmation_never_authorizes_mutations(tool, args):
    state, _, sub_repo, feedback_repo = run_graph([
        AIMessage(content="", tool_calls=[{"name": tool, "args": args, "id": "mutation"}]),
        AIMessage(content="Готово"),
    ], confirmed_action_id="arbitrary-attacker-controlled-id")
    result = next(m for m in state["messages"] if isinstance(m, ToolMessage))
    assert json.loads(result.content) == {"status": "UNAVAILABLE", "error": "SECURE_CONFIRMATION_STORE_REQUIRED"}
    sub_repo.upsert_subscription.assert_not_awaited()
    feedback_repo.create_feedback.assert_not_awaited()
    assert "Готово" not in state["final_response_text"]
    assert "недоступны" in state["final_response_text"]
