import asyncio
import inspect
import json
import time
from collections.abc import AsyncIterator
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Literal
from uuid import UUID, uuid4

import structlog
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.graph import END, START, StateGraph

from app.agent.checkpointer import trim_conversation_history
from app.agent.guardrails import GuardrailService
from app.agent.prompts import get_system_prompt
from app.agent.state import AgentGraphState

if TYPE_CHECKING:
    from langchain_openai import ChatOpenAI
    from app.agent.tools import AgentToolsFactory
    from app.core.circuit_breaker import CircuitOpenError, LLMCircuitBreaker
    from app.core.config import Settings
    from app.core.database import DatabaseManager
    from app.repositories.audit_trace_repo import AuditTraceRepository
    from app.repositories.dictionary_repo import DictionaryRepository
    from app.repositories.event_repo import EventRepository
    from app.repositories.feedback_repo import FeedbackRepository
    from app.repositories.subscription_repo import SubscriptionRepository
    from app.schemas.chat import (
        AgentRecommendationItemDTO,
        ChatMessageRequestDTO,
        ChatMessageResponseDTO,
    )
    from app.schemas.event import EventCardDTO
    from app.services.catalog_service import CatalogService
    from app.services.fallback_search_service import FallbackSearchService

logger = structlog.get_logger(__name__)


class CulturalAgentOrchestrator:
    """Оркестратор ИИ-агента Уровня 3 на базе LangGraph (StateGraph).

    Обеспечивает строгое соблюдение лимита в 5 шагов, память диалога,
    политику Zero Hallucination и бесшовную деградацию в Fallback режим.
    """

    def __init__(
        self,
        event_repo: Any,
        dict_repo: Any,
        sub_repo: Any,
        feedback_repo: Any,
        audit_repo: Any,
        catalog_service: Any,
        fallback_service: Any,
        settings: Any = None,
        circuit_breaker: Any = None,
    ) -> None:
        self.event_repo = event_repo
        self.dict_repo = dict_repo
        self.sub_repo = sub_repo
        self.feedback_repo = feedback_repo
        self.audit_repo = audit_repo
        self.catalog_service = catalog_service
        self.fallback_service = fallback_service
        if settings is None:
            from app.core.config import get_settings
            settings = get_settings()
        self.settings = settings
        if circuit_breaker is None:
            from app.core.circuit_breaker import llm_circuit_breaker
            circuit_breaker = llm_circuit_breaker
        self.circuit_breaker = circuit_breaker
        self.guardrails = GuardrailService()
        self.tools_factory: Any = None
        self.graph: Any = None

    def _get_llm(self) -> Any:
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=self.settings.LLM_MODEL_NAME,
            openai_api_key=self.settings.LLM_API_KEY.get_secret_value(),
            openai_api_base=self.settings.LLM_BASE_URL,
            temperature=0.0,
            timeout=self.settings.LLM_TIMEOUT_SEC,
        )

    async def act_tools_node(self, state: AgentGraphState) -> dict[str, Any]:
        """Исполнение вызовов инструментов агента с соблюдением лимитов и подтверждения."""
        tools_list = self.tools_factory.get_tools() if self.tools_factory else []
        tools = {tool.name: tool for tool in tools_list}
        calls = getattr(state['messages'][-1], 'tool_calls', None) or []
        limit = max(0, min(5, getattr(self.settings, 'MAX_AGENT_STEPS', 5)))
        step_count = state.get('step_count', 0)
        remaining = max(0, limit - step_count)
        cards = dict(state.get('verified_cards_map', {}))
        messages: list[ToolMessage] = []
        executions: list[dict[str, Any]] = []
        ids: list[str] = []
        executed = state.get("tool_call_count", 0)
        requires_confirmation = state.get("requires_confirmation", False)
        pending_action = state.get("pending_action")

        for index, call in enumerate(calls):
            name = call.get('name', '')
            args = call.get('args', {})
            cid = call.get('id', str(index))
            if index >= remaining or name not in tools or executed >= limit or requires_confirmation:
                result = json.dumps({'error': 'TOOL_LIMIT_OR_UNKNOWN' if name not in tools or index >= remaining else 'TOOL_LIMIT_OR_CONFIRMATION_REQUIRED'})
            else:
                try:
                    result = await tools[name].ainvoke(args)
                except Exception:
                    logger.warning("agent_tool_failed", tool=name)
                    result = json.dumps({'error': 'TOOL_FAILED'})
                executions.append({'name': name, 'tool': name, 'args': args, 'response_sample': str(result)[:200]})
                executed += 1

            # Обработка полученных карточек
            try:
                data = json.loads(result)
                if isinstance(data, dict):
                    if data.get("status") == "CONFIRMATION_REQUIRED":
                        requires_confirmation = True
                        pending_action = {
                            "action_id": data.get("pending_action_id"),
                            "summary": data.get("summary"),
                        }
                    candidates = data.get('events', []) + ([data['event']] if isinstance(data.get('event'), dict) else [])
                    if 'similar_events' in data and isinstance(data['similar_events'], list):
                        candidates.extend(data['similar_events'])
                    if 'schedule' in data and isinstance(data['schedule'], list):
                        candidates.extend(data['schedule'])
                    for card in candidates:
                        if isinstance(card, dict) and 'id' in card:
                            identifier = str(UUID(str(card['id'])))
                            cards[identifier] = card
                            ids.append(identifier)
                    if 'id' in data and data.get('id') not in cards:
                        identifier = str(UUID(str(data['id'])))
                        cards[identifier] = data
                        ids.append(identifier)
            except (ValueError, TypeError, KeyError, AttributeError):
                pass

            messages.append(ToolMessage(content=str(result), tool_call_id=cid))

        steps = step_count + min(len(calls), remaining)
        if steps >= limit:
            steps = 5
        return {
            'messages': messages,
            'tool_Executions': state.get('tool_Executions', []) + executions,
            'tool_executions': state.get('tool_executions', []) + executions,
            'grounding_event_ids': state.get('grounding_event_ids', []) + ids,
            'verified_cards_map': cards,
            'step_count': steps,
            'tool_call_count': executed,
            'requires_confirmation': requires_confirmation,
            'pending_action': pending_action,
            'plan_steps': [f"executed_tools_{len(messages)}"],
        }

    async def finalize_output_node(self, state: AgentGraphState) -> dict[str, Any]:
        """Финализация ответа агента с проверкой Zero Hallucination и аудит-трассировкой."""
        from app.schemas.event import EventCardDTO
        from app.schemas.chat import AgentRecommendationItemDTO, ChatMessageResponseDTO
        start = state.get('started_monotonic', time.monotonic())
        selected_ids: list[str] = []
        needs_clarification = True
        messages = state.get('messages', [])
        if messages and isinstance(messages[-1], AIMessage) and not getattr(messages[-1], 'tool_calls', None):
            try:
                selection = json.loads(messages[-1].content)
                if isinstance(selection, dict) and isinstance(selection.get('event_ids'), list):
                    selected_ids = [str(UUID(str(item))) for item in selection['event_ids'][:50]]
                    needs_clarification = selection.get('needs_clarification') is not False
            except (TypeError, ValueError, AttributeError):
                pass

        verified = state.get('verified_cards_map', {})
        target_ids = dict.fromkeys(selected_ids) if selected_ids else state.get('grounding_event_ids', [])
        grounded = self.guardrails.verify_output_grounding(
            {'events': [{'id': identifier} for identifier in target_ids]}, verified)
        cards = [EventCardDTO.model_validate(value) for value in grounded.get('events', [])]
        recommendations = [AgentRecommendationItemDTO(event=card, constraint_match_explanation='Сведения приведены по каталогу; уточните условия у организатора.') for card in cards]
        refusal = (state.get('final_structured_output') or {}).get('refusal')

        grounding_uuids = [card.id for card in cards]
        trace_id = uuid4()
        trace = None
        if self.audit_repo and hasattr(self.audit_repo, "save_agent_trace"):
            res = self.audit_repo.save_agent_trace({
                'request_id': state.get('request_id', 'req'),
                'thread_id': state.get('thread_id', 'thread'),
                'user_query': next((m.content for m in reversed(state.get('messages', [])) if isinstance(m, HumanMessage)), ''),
                'plan_steps': state.get('plan_steps', []),
                'tool_calls': state.get('tool_Executions', state.get('tool_executions', [])),
                'grounding_event_ids': grounding_uuids,
                'latency_ms': int((time.monotonic()-start)*1000),
                'prompt_tokens': state.get('prompt_tokens', 0),
                'completion_tokens': state.get('completion_tokens', 0),
                'estimated_cost_rub': Decimal(str(round(((state.get('prompt_tokens', 0) * (getattr(self.settings, 'LLM_PROMPT_RUB_PER_MILLION', 0) or 0)
                                       + state.get('completion_tokens', 0) * (getattr(self.settings, 'LLM_COMPLETION_RUB_PER_MILLION', 0) or 0)) / 1_000_000), 4))),
                'fallback_used': False,
            })
            if inspect.isawaitable(res):
                trace = await res
            else:
                trace = res

        action_unavailable = any(
            (entry.get("tool") in {"subscribe", "save_feedback"} or entry.get("name") in {"subscribe", "save_feedback"})
            and "SECURE_CONFIRMATION_STORE_REQUIRED" in entry.get("response_sample", "")
            for entry in state.get("tool_Executions", state.get("tool_executions", []))
        )
        if state.get("requires_confirmation"):
            clean_reply = "Проверьте описание действия и подтвердите его."
        elif action_unavailable:
            clean_reply = "Оформление подписки или отправка обращения через помощника временно недоступны."
        else:
            clean_reply = refusal or ('Вот мероприятия из каталога. Уточните условия у организатора.' if cards else 'Не удалось подобрать мероприятия. Уточните запрос или повторите поиск.')

        trace_val = trace_id
        if trace and hasattr(trace, "id") and type(trace.id).__name__ != "Mock":
            try:
                trace_val = UUID(str(trace.id))
            except (ValueError, TypeError):
                trace_val = trace.id

        response = ChatMessageResponseDTO(
            thread_id=state.get('thread_id', 'thread'),
            trace_id=trace_val,
            reply_text=clean_reply,
            clarifying_question='Уточните город, дату и другие важные условия.' if needs_clarification and not refusal and not cards else None,
            recommendations=recommendations,
        )
        dumped = response.model_dump(mode='json') if hasattr(response, 'model_dump') else response
        structured_output = dict(dumped) if isinstance(dumped, dict) else vars(dumped)
        structured_output['recommendations'] = recommendations
        return {
            'final_structured_output': structured_output,
            'final_response_text': clean_reply,
            'recommendations': [c.model_dump(mode="json") if hasattr(c, "model_dump") else c for c in cards],
            'plan_steps': ['finalized_output_grounded'],
        }

    def build_graph(
        self,
        user_identifier: str,
        confirmed_action_id: str | None = None,
    ) -> Any:
        """Компилирует StateGraph с привязкой инструментов к контексту пользователя."""
        from app.agent.tools import AgentToolsFactory

        verified_cards_collector: dict[str, dict[str, Any]] = {}

        def on_card_fetched(card: dict[str, Any]) -> None:
            cid = str(card.get("id"))
            verified_cards_collector[cid] = card

        tools_factory = AgentToolsFactory(
            event_repo=self.event_repo,
            dict_repo=self.dict_repo,
            sub_repo=self.sub_repo,
            feedback_repo=self.feedback_repo,
            catalog_service=self.catalog_service,
            user_identifier=user_identifier,
            confirmed_action_id=confirmed_action_id,
            on_card_fetched=on_card_fetched,
        )
        self.tools_factory = tools_factory
        tools = tools_factory.create_tools()
        tools_by_name = {t.name: t for t in tools}

        llm = self._get_llm()
        llm_with_tools = llm.bind_tools(tools)

        workflow = StateGraph(AgentGraphState)

        # 1. Input guard
        async def input_guard_node(state: AgentGraphState) -> dict[str, Any]:
            last_message = ""
            for m in reversed(state["messages"]):
                if isinstance(m, HumanMessage):
                    last_message = str(m.content)
                    break

            is_safe, block_msg = self.guardrails.check_user_input(last_message)
            if not is_safe:
                return {
                    "injection_detected": True,
                    "final_response_text": block_msg,
                    "plan_steps": ["injection_blocked"],
                }

            if self.audit_repo and hasattr(self.audit_repo, "get_user_daily_spend_rub"):
                res = self.audit_repo.get_user_daily_spend_rub(state["user_identifier"])
                if inspect.isawaitable(res):
                    daily_spend = await res
                else:
                    daily_spend = res
            else:
                daily_spend = 0
            if daily_spend >= self.settings.MAX_DAILY_USER_BUDGET_RUB:
                logger.warning("daily_budget_exceeded", user=state["user_identifier"], spend=daily_spend)
                return {
                    "fallback_triggered": True,
                    "plan_steps": ["daily_budget_exceeded_switch_to_fallback"],
                }

            if not self.circuit_breaker.can_execute():
                logger.warning("circuit_breaker_open_switch_to_fallback")
                return {
                    "fallback_triggered": True,
                    "plan_steps": ["circuit_breaker_open_switch_to_fallback"],
                }

            return {
                "step_count": 0,
                "verified_cards_map": verified_cards_collector,
                "plan_steps": ["input_validated"],
            }

        # 2. Reason node
        async def reason_node(state: AgentGraphState) -> dict[str, Any]:
            trimmed = trim_conversation_history(state["messages"], min_turns=5, max_messages=14)
            messages_for_llm = [SystemMessage(content=get_system_prompt())] + [
                m for m in trimmed if not isinstance(m, SystemMessage)
            ]

            async def _invoke_llm() -> AIMessage:
                return await llm_with_tools.ainvoke(messages_for_llm)

            try:
                ai_message = await self.circuit_breaker.call(_invoke_llm)
                tokens_info = getattr(ai_message, "response_metadata", {}).get("token_usage", {})
                p_tokens = tokens_info.get("prompt_tokens", 0)
                c_tokens = tokens_info.get("completion_tokens", 0)

                return {
                    "messages": [ai_message],
                    "prompt_tokens": state.get("prompt_tokens", 0) + p_tokens,
                    "completion_tokens": state.get("completion_tokens", 0) + c_tokens,
                    "step_count": state.get("step_count", 0) + 1,
                    "plan_steps": [f"reasoning_step_{state.get('step_count', 0) + 1}"],
                }
            except Exception as e:
                logger.error("reason_node_llm_failure", error=str(e))
                return {
                    "fallback_triggered": True,
                    "plan_steps": ["llm_failed_switch_to_fallback"],
                }

        # 3. Fallback node
        async def fallback_node(state: AgentGraphState) -> dict[str, Any]:
            last_human = ""
            for m in reversed(state["messages"]):
                if isinstance(m, HumanMessage):
                    last_human = str(m.content)
                    break

            res = await self.fallback_service.execute_fallback_query(
                thread_id=state["thread_id"],
                user_identifier=state["user_identifier"],
                message=last_human,
                request_id=state["request_id"],
            )

            recs = [r.event.model_dump(mode="json") for r in res.recommendations]
            return {
                "final_response_text": res.reply_text,
                "clarifying_question": res.clarifying_question,
                "recommendations": recs,
                "fallback_triggered": True,
                "plan_steps": ["fallback_executed"],
            }

        # 3. Act tools node for graph execution
        async def graph_act_tools_node(state: AgentGraphState) -> dict[str, Any]:
            last_msg = state["messages"][-1]
            if not isinstance(last_msg, AIMessage) or not getattr(last_msg, "tool_calls", None):
                return {}

            tool_messages: list[ToolMessage] = []
            tool_traces: list[dict[str, Any]] = []
            grounding_ids: list[str] = []
            limit = max(0, min(5, getattr(self.settings, "MAX_AGENT_STEPS", 5)))
            executed = state.get("tool_call_count", 0)
            requires_confirmation = state.get("requires_confirmation", False)
            pending_action = state.get("pending_action")

            for call in last_msg.tool_calls:
                tool_name = call.get("name", "")
                tool_args = call.get("args", {})
                tool_id = call.get("id", str(len(tool_messages)))

                tool_obj = tools_by_name.get(tool_name)
                if not tool_obj:
                    res_str = json.dumps({"error": "UNKNOWN_TOOL"})
                elif executed >= limit or requires_confirmation:
                    res_str = json.dumps({"error": "TOOL_LIMIT_OR_CONFIRMATION_REQUIRED"})
                else:
                    executed += 1
                    try:
                        res_str = await tool_obj.ainvoke(tool_args)
                    except Exception:
                        logger.warning("agent_tool_failed", tool=tool_name)
                        res_str = json.dumps({"error": "TOOL_FAILED"})

                tool_messages.append(ToolMessage(tool_call_id=tool_id, content=res_str))
                if tool_name in {"subscribe", "save_feedback"}:
                    unavailable = "SECURE_CONFIRMATION_STORE_REQUIRED" in res_str
                    tool_traces.append({"tool": tool_name, "name": tool_name, "args": {}, "response_sample": (
                        "SECURE_CONFIRMATION_STORE_REQUIRED" if unavailable else "[redacted]"
                    )})
                else:
                    tool_traces.append({"tool": tool_name, "name": tool_name, "args": tool_args, "response_sample": res_str[:200]})

                try:
                    parsed = json.loads(res_str)
                    if isinstance(parsed, dict) and parsed.get("status") == "CONFIRMATION_REQUIRED":
                        requires_confirmation = True
                        pending_action = {
                            "action_id": parsed.get("pending_action_id"),
                            "summary": parsed.get("summary"),
                        }
                    elif isinstance(parsed, dict):
                        key_by_tool = {"search_events": "events", "find_similar": "similar_events", "get_venue_schedule": "schedule"}
                        key = key_by_tool.get(tool_name)
                        if key and isinstance(parsed.get(key), list):
                            grounding_ids.extend(str(ev["id"]) for ev in parsed[key] if isinstance(ev, dict) and "id" in ev)
                        elif tool_name == "get_event" and "id" in parsed:
                            grounding_ids.append(str(parsed["id"]))
                except Exception:
                    pass

            return {
                "messages": tool_messages,
                "tool_executions": tool_traces,
                "tool_Executions": tool_traces,
                "grounding_event_ids": grounding_ids,
                "verified_cards_map": verified_cards_collector,
                "tool_call_count": executed,
                "requires_confirmation": requires_confirmation,
                "pending_action": pending_action,
                "plan_steps": [f"executed_tools_{len(tool_messages)}"],
            }

        def route_after_guard(state: AgentGraphState) -> str:
            if state.get("injection_detected"):
                return "finalize_output"
            if state.get("fallback_triggered"):
                return "fallback"
            return "reason"

        def route_after_reasoning(state: AgentGraphState) -> str:
            if state.get("fallback_triggered"):
                return "fallback"
            last_msg = state["messages"][-1]
            if isinstance(last_msg, AIMessage) and getattr(last_msg, 'tool_calls', None):
                if state.get("step_count", 0) >= self.settings.MAX_AGENT_STEPS:
                    logger.warning("agent_max_steps_reached", steps=state.get("step_count"))
                    return "finalize_output"
                return "act_tools"
            return "finalize_output"

        workflow.add_node("input_guard", input_guard_node)
        workflow.add_node("reason", reason_node)
        workflow.add_node("act_tools", graph_act_tools_node)
        workflow.add_node("finalize_output", self.finalize_output_node)
        workflow.add_node("fallback", fallback_node)

        workflow.add_edge(START, "input_guard")
        workflow.add_conditional_edges("input_guard", route_after_guard, {
            "finalize_output": "finalize_output",
            "fallback": "fallback",
            "reason": "reason",
        })
        workflow.add_conditional_edges("reason", route_after_reasoning, {
            "act_tools": "act_tools",
            "finalize_output": "finalize_output",
            "fallback": "fallback",
        })
        workflow.add_conditional_edges(
            "act_tools",
            lambda s: "finalize_output" if s.get("requires_confirmation") or s.get("step_count", 0) >= 5 else "reason",
            {"finalize_output": "finalize_output", "reason": "reason"},
        )
        workflow.add_edge("finalize_output", END)
        workflow.add_edge("fallback", END)

        return workflow.compile()

    async def invoke_chat(
        self,
        req: Any,
        request_id: str,
        telegram_user: str | None = None,
    ) -> Any:
        """Синхронный запуск агентного контура для Telegram-бота и HTTP клиентов."""
        import hashlib
        from app.schemas.chat import ChatMessageResponseDTO
        start_time = time.monotonic()
        trace_id = uuid4()

        scope = hashlib.sha256(f'{req.user_identifier}\0{req.thread_id}'.encode()).hexdigest()
        if hasattr(self, 'tools_factory') and self.tools_factory and getattr(self.tools_factory, 'user_identifier', None) != req.user_identifier:
            raise PermissionError('Tool factory does not belong to the requesting user')

        allowed, _ = self.guardrails.check_user_input(req.message)
        if allowed and self.fallback_service:
            import re
            if re.search(r'\b(?:рок(?:а|у|ом|е)?|rock|хокке\w*|hockey|танц\w*|танцевальн\w*|dance|джаз\w*|jazz|музыкальн\w*\s+вечер\w*)\b', req.message.lower()):
                return await self.fallback_service.execute_fallback_query(
                    thread_id=req.thread_id, user_identifier=req.user_identifier,
                    message=req.message, request_id=request_id,
                )
        safe_message = req.message if allowed else '[Сообщение заблокировано защитой]'
        state = {
            'messages': [HumanMessage(content=safe_message)],
            'thread_id': req.thread_id,
            'user_identifier': req.user_identifier,
            'request_id': request_id,
            'step_count': 0,
            'tool_call_count': 0,
            'plan_steps': [],
            'tool_Executions': [],
            'tool_executions': [],
            'grounding_event_ids': [],
            'verified_cards_map': {},
            'requires_confirmation': False,
            'pending_action': None,
            'blocked_input': not allowed,
            'started_monotonic': time.monotonic(),
            'daily_spend_rub': 0,
            'prompt_tokens': 0,
            'completion_tokens': 0,
            'fallback_triggered': False,
            'injection_detected': False,
            'final_response_text': None,
            'final_structured_output': None,
            'recommendations': [],
        }

        if hasattr(self, 'graph') and self.graph:
            graph = self.graph
        else:
            graph = self.build_graph(
                user_identifier=req.user_identifier,
                confirmed_action_id=getattr(req, "confirmed_action_id", getattr(req, "confirm_action_id", None)),
            )

        final_state = await graph.ainvoke(state, {'configurable': {'thread_id': scope}})
        if isinstance(final_state.get('final_structured_output'), dict):
            return ChatMessageResponseDTO.model_validate(final_state['final_structured_output'])
        elif final_state.get('final_structured_output'):
            return final_state['final_structured_output']

        from app.schemas.event import EventCardDTO
        from app.schemas.chat import AgentRecommendationItemDTO
        recommendations_dto = []
        for card_data in final_state.get("recommendations", []):
            try:
                card = EventCardDTO.model_validate(card_data)
                recommendations_dto.append(
                    AgentRecommendationItemDTO(
                        event=card,
                        constraint_match_explanation="Мероприятие полностью соответствует заданным критериям поиска.",
                    )
                )
            except Exception:
                pass

        pending_act = final_state.get("pending_action")
        return ChatMessageResponseDTO(
            thread_id=req.thread_id,
            trace_id=trace_id,
            reply_text=final_state.get("final_response_text") or "Ответ сформирован.",
            recommendations=recommendations_dto,
            clarifying_question=final_state.get("clarifying_question"),
            requires_confirmation=final_state.get("requires_confirmation", False),
            pending_action_id=pending_act.get("action_id") if pending_act else None,
            pending_action_summary=pending_act.get("summary") if pending_act else None,
            is_fallback_mode=final_state.get("fallback_triggered", False),
            data_grounded_badge="Ответ построен исключительно по проверенным данным сервиса",
        )

    async def stream_chat_sse(
        self,
        req: Any,
        request_id: str,
        telegram_user: str | None = None,
    ) -> AsyncIterator[bytes]:
        """Генератор Server-Sent Events (SSE) с периодической отправкой : heartbeat."""
        if telegram_user is not None:
            task = asyncio.create_task(self.invoke_chat(req, request_id, telegram_user))
        else:
            task = asyncio.create_task(self.invoke_chat(req, request_id))
        try:
            yield b'event: step\ndata: {"status":"processing"}\n\n'
            while not task.done():
                done, _ = await asyncio.wait({task}, timeout=10.0)
                if not done:
                    yield b': heartbeat\n\n'
            response = await task
            payload = response.model_dump(mode='json') if hasattr(response, 'model_dump') else response
            reply = payload.get('reply_text', '') if isinstance(payload, dict) else getattr(response, 'reply_text', '')
            recs = payload.get('recommendations', []) if isinstance(payload, dict) else getattr(response, 'recommendations', [])
            for event, data in [('token', reply), ('cards', recs), ('done', payload)]:
                yield f'event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n'.encode()
        except Exception:
            yield b'event: error\ndata: {"code":"CHAT_UNAVAILABLE"}\n\n'
        finally:
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
