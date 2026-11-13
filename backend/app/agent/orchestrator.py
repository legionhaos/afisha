"""LangGraph orchestration with database-grounded responses."""
import asyncio
import json
import time
from typing import Any, AsyncIterator, Literal
from uuid import UUID

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.graph import END, START, StateGraph

from app.agent.checkpointer import trim_conversation_history
from app.agent.prompts import SYSTEM_PROMPT
from app.agent.state import AgentGraphState
from app.schemas.chat import AgentRecommendationItemDTO, ChatMessageResponseDTO


def route_after_reasoning(state: AgentGraphState) -> Literal['act_tools', 'fallback', 'finalize_output']:
    if state.get('fallback_triggered'):
        return 'fallback'
    if state.get('step_count', 0) >= 5:
        return 'finalize_output'
    messages = state.get('messages', [])
    if messages and getattr(messages[-1], 'tool_calls', None):
        return 'act_tools'
    return 'finalize_output'


class CulturalAgentOrchestrator:
    def __init__(self, llm: Any, tools_factory: Any, guardrails: Any, circuit_breaker: Any,
                 audit_repo: Any, fallback_service: Any, checkpointer: Any, settings: Any) -> None:
        self.llm, self.tools_factory, self.guardrails = llm, tools_factory, guardrails
        self.circuit_breaker, self.audit_repo = circuit_breaker, audit_repo
        self.fallback_service, self.checkpointer, self.settings = fallback_service, checkpointer, settings
        builder = StateGraph(AgentGraphState)
        for name in ('input_guard', 'reason', 'act_tools', 'finalize_output', 'fallback'):
            builder.add_node(name, getattr(self, name + '_node'))
        builder.add_edge(START, 'input_guard')
        builder.add_conditional_edges('input_guard', lambda s: 'finalize_output' if s.get('final_structured_output') else ('fallback' if s.get('fallback_triggered') else 'reason'))
        builder.add_conditional_edges('reason', route_after_reasoning)
        builder.add_conditional_edges('act_tools', lambda s: 'finalize_output' if s.get('step_count', 0) >= 5 else 'reason')
        builder.add_edge('fallback', END)
        builder.add_edge('finalize_output', END)
        self.graph = builder.compile(checkpointer=checkpointer)

    async def input_guard_node(self, state: AgentGraphState) -> dict[str, Any]:
        if state.get('blocked_input'):
            return {'final_structured_output': {'refusal': 'Я помогаю только с поиском культурных мероприятий Башкортостана и не могу выполнить эту инструкцию.'}}
        allowed, reason = self.guardrails.check_user_input(state['messages'][-1].content)
        if not allowed:
            return {'final_structured_output': {'refusal': reason}}
        spend = await self.audit_repo.get_user_daily_spend_rub(state['user_identifier'])
        # Unknown provider tariffs cannot be treated as zero-cost calls.
        prices_known = all(isinstance(getattr(self.settings, field, None), (int, float))
                           and getattr(self.settings, field) >= 0 for field in
                           ('LLM_PROMPT_RUB_PER_MILLION', 'LLM_COMPLETION_RUB_PER_MILLION'))
        # Spend reservations must be atomic and reconciled even if a call fails.
        # Until the shared persistence layer supplies that contract, fail closed.
        budget_ready = False
        return {'fallback_triggered': not budget_ready or not prices_known or spend >= self.settings.MAX_DAILY_USER_BUDGET_RUB, 'daily_spend_rub': spend}

    async def reason_node(self, state: AgentGraphState) -> dict[str, Any]:
        prompt_price = self.settings.LLM_PROMPT_RUB_PER_MILLION
        completion_price = self.settings.LLM_COMPLETION_RUB_PER_MILLION
        cost = (state.get('prompt_tokens', 0) * prompt_price + state.get('completion_tokens', 0) * completion_price) / 1_000_000
        if (cost >= self.settings.MAX_DIALOG_COST_RUB or
                float(state.get('daily_spend_rub', 0)) + cost >= self.settings.MAX_DAILY_USER_BUDGET_RUB):
            return {'fallback_triggered': True}
        messages = trim_conversation_history(state['messages'])
        try:
            model = self.llm.bind_tools(self.tools_factory.get_tools())
            response = await self.circuit_breaker.call(model.ainvoke, [SystemMessage(content=SYSTEM_PROMPT), *messages])
            usage = getattr(response, 'usage_metadata', None) or {}
            if 'input_tokens' not in usage or 'output_tokens' not in usage:
                return {'fallback_triggered': True}
            return {'messages': [response], 'prompt_tokens': state.get('prompt_tokens', 0) + usage.get('input_tokens', 0),
                    'completion_tokens': state.get('completion_tokens', 0) + usage.get('output_tokens', 0)}
        except Exception:
            return {'fallback_triggered': True}

    async def act_tools_node(self, state: AgentGraphState) -> dict[str, Any]:
        tools = {tool.name: tool for tool in self.tools_factory.get_tools()}
        calls = state['messages'][-1].tool_calls
        remaining = max(0, min(5, getattr(self.settings, 'MAX_AGENT_STEPS', 5)) - state.get('step_count', 0))
        cards = dict(state.get('verified_cards_map', {}))
        messages, executions, ids = [], [], []
        for index, call in enumerate(calls):
            name = call.get('name', '')
            if index >= remaining or name not in tools:
                result = json.dumps({'error': 'TOOL_LIMIT_OR_UNKNOWN'})
            else:
                try:
                    result = await tools[name].ainvoke(call.get('args', {}))
                except Exception:
                    result = json.dumps({'error': 'TOOL_FAILED'})
                executions.append({'name': name, 'args': call.get('args', {})})
            try:
                data = json.loads(result)
                candidates = data.get('events', []) + ([data['event']] if isinstance(data.get('event'), dict) else [])
                for card in candidates:
                    identifier = str(UUID(str(card['id'])))
                    cards[identifier] = card
                    ids.append(identifier)
            except (ValueError, TypeError, KeyError, AttributeError):
                pass
            messages.append(ToolMessage(content=str(result), tool_call_id=call['id']))
        steps = state.get('step_count', 0) + min(len(calls), remaining)
        if steps >= min(5, getattr(self.settings, 'MAX_AGENT_STEPS', 5)):
            steps = 5
        return {'messages': messages, 'tool_Executions': state.get('tool_Executions', []) + executions,
                'grounding_event_ids': state.get('grounding_event_ids', []) + ids,
                'verified_cards_map': cards, 'step_count': steps}

    async def finalize_output_node(self, state: AgentGraphState) -> dict[str, Any]:
        from app.schemas.event import EventCardDTO
        start = state.get('started_monotonic', time.monotonic())
        selected_ids: list[str] = []
        needs_clarification = True
        messages = state.get('messages', [])
        if messages and isinstance(messages[-1], AIMessage) and not messages[-1].tool_calls:
            try:
                selection = json.loads(messages[-1].content)
                if isinstance(selection, dict) and isinstance(selection.get('event_ids'), list):
                    selected_ids = [str(UUID(str(item))) for item in selection['event_ids'][:50]]
                    needs_clarification = selection.get('needs_clarification') is not False
            except (TypeError, ValueError, AttributeError):
                pass
        verified = state.get('verified_cards_map', {})
        # A malformed model response never turns intermediate search results into recommendations.
        grounded = self.guardrails.verify_output_grounding(
            {'events': [{'id': identifier} for identifier in dict.fromkeys(selected_ids)]}, verified)
        cards = [EventCardDTO.model_validate(value) for value in grounded.get('events', [])]
        recommendations = [AgentRecommendationItemDTO(event=card, constraint_match_explanation='Сведения приведены по каталогу; уточните условия у организатора.') for card in cards]
        refusal = (state.get('final_structured_output') or {}).get('refusal')
        trace = await self.audit_repo.save_agent_trace({'request_id': state['request_id'], 'thread_id': state['thread_id'],
            'user_query': next((m.content for m in reversed(state['messages']) if isinstance(m, HumanMessage)), ''),
            'plan_steps': state.get('plan_steps', []), 'tool_calls': state.get('tool_Executions', []),
            'grounding_event_ids': [card.id for card in cards], 'latency_ms': int((time.monotonic()-start)*1000),
            'prompt_tokens': state.get('prompt_tokens', 0), 'completion_tokens': state.get('completion_tokens', 0),
            'estimated_cost_rub': (state.get('prompt_tokens', 0) * (getattr(self.settings, 'LLM_PROMPT_RUB_PER_MILLION', None) or 0)
                                   + state.get('completion_tokens', 0) * (getattr(self.settings, 'LLM_COMPLETION_RUB_PER_MILLION', None) or 0)) / 1_000_000,
            'fallback_used': False})
        response = ChatMessageResponseDTO(thread_id=state['thread_id'], trace_id=trace.id,
            reply_text=refusal or ('Найдены мероприятия в каталоге.' if cards else 'Не удалось подобрать подтверждённые мероприятия. Уточните запрос.'),
            clarifying_question='Уточните город, дату и другие важные условия.' if needs_clarification and not refusal else None,
            recommendations=recommendations)
        return {'final_structured_output': response.model_dump(mode='json')}

    async def fallback_node(self, state: AgentGraphState) -> dict[str, Any]:
        message = next((m.content for m in reversed(state['messages']) if isinstance(m, HumanMessage)), '')
        response = await self.fallback_service.execute_fallback_query(state['thread_id'], state['user_identifier'], message, state['request_id'])
        return {'final_structured_output': response.model_dump(mode='json')}

    async def invoke_chat(self, req: Any, request_id: str) -> ChatMessageResponseDTO:
        # Namespacing prevents different users from sharing a checkpoint by choosing the same thread ID.
        import hashlib
        scope = hashlib.sha256(f'{req.user_identifier}\0{req.thread_id}'.encode()).hexdigest()
        if self.tools_factory.user_identifier != req.user_identifier:
            raise PermissionError('Tool factory does not belong to the requesting user')
        allowed, _ = self.guardrails.check_user_input(req.message)
        safe_message = req.message if allowed else '[Сообщение заблокировано защитой]'
        state = {'messages': [HumanMessage(content=safe_message)], 'thread_id': req.thread_id,
            'user_identifier': req.user_identifier, 'request_id': request_id, 'step_count': 0,
            'plan_steps': [], 'tool_Executions': [], 'grounding_event_ids': [], 'verified_cards_map': {},
            'requires_confirmation': False, 'pending_action': None, 'blocked_input': not allowed,
            'started_monotonic': time.monotonic(), 'daily_spend_rub': 0, 'prompt_tokens': 0,
            'completion_tokens': 0, 'fallback_triggered': False, 'final_structured_output': None}
        result = await self.graph.ainvoke(state, {'configurable': {'thread_id': scope}})
        return ChatMessageResponseDTO.model_validate(result['final_structured_output'])

    async def stream_chat_sse(self, req: Any, request_id: str) -> AsyncIterator[bytes]:
        task = asyncio.create_task(self.invoke_chat(req, request_id))
        try:
            yield b'event: step\ndata: {"status":"processing"}\n\n'
            while not task.done():
                done, _ = await asyncio.wait({task}, timeout=10)
                if not done:
                    yield b': heartbeat\n\n'
            response = await task
            payload = response.model_dump(mode='json')
            for event, data in [('token', payload.get('reply_text', '')), ('cards', payload.get('recommendations', [])), ('done', payload)]:
                yield f'event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n'.encode()
        except Exception:
            yield b'event: error\ndata: {"code":"CHAT_UNAVAILABLE"}\n\n'
        finally:
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
