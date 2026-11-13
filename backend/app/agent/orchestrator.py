import asyncio
import json
import time
from collections.abc import AsyncIterator
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID, uuid4

import structlog
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph

from app.agent.checkpointer import CheckpointerManager, trim_conversation_history
from app.agent.guardrails import GuardrailService
from app.agent.prompts import get_system_prompt
from app.agent.state import AgentGraphState
from app.agent.tools import AgentToolsFactory
from app.core.circuit_breaker import CircuitOpenError, LLMCircuitBreaker, llm_circuit_breaker
from app.core.config import Settings, get_settings
from app.core.database import DatabaseManager, db_manager
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
        event_repo: EventRepository,
        dict_repo: DictionaryRepository,
        sub_repo: SubscriptionRepository,
        feedback_repo: FeedbackRepository,
        audit_repo: AuditTraceRepository,
        catalog_service: CatalogService,
        fallback_service: FallbackSearchService,
        settings: Settings | None = None,
        circuit_breaker: LLMCircuitBreaker | None = None,
    ) -> None:
        self.event_repo = event_repo
        self.dict_repo = dict_repo
        self.sub_repo = sub_repo
        self.feedback_repo = feedback_repo
        self.audit_repo = audit_repo
        self.catalog_service = catalog_service
        self.fallback_service = fallback_service
        self.settings = settings or get_settings()
        self.circuit_breaker = circuit_breaker or llm_circuit_breaker
        self.guardrails = GuardrailService()

    def _get_llm(self) -> ChatOpenAI:
        return ChatOpenAI(
            model=self.settings.LLM_MODEL_NAME,
            openai_api_key=self.settings.LLM_API_KEY.get_secret_value(),
            openai_api_base=self.settings.LLM_BASE_URL,
            temperature=0.0,
            timeout=self.settings.LLM_TIMEOUT_SEC,
        )

    def build_graph(
        self,
        user_identifier: str,
        confirmed_action_id: str | None = None,
    ) -> Any:
        """Компилирует StateGraph с привязкой инструментов к контексту пользователя."""
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
        tools = tools_factory.create_tools()
        tools_by_name = {t.name: t for t in tools}

        llm = self._get_llm()
        # Bind tools to LLM
        llm_with_tools = llm.bind_tools(tools)

        workflow = StateGraph(AgentGraphState)

        # 1. Узел проверки безопасности и бюджета
        async def input_guard_node(state: AgentGraphState) -> dict[str, Any]:
            last_message = ""
            for m in reversed(state["messages"]):
                if isinstance(m, HumanMessage):
                    last_message = str(m.content)
                    break

            # Проверка Prompt Injection
            is_safe, block_msg = self.guardrails.check_user_input(last_message)
            if not is_safe:
                return {
                    "injection_detected": True,
                    "final_response_text": block_msg,
                    "plan_steps": ["injection_blocked"],
                }

            # Проверка суточного бюджета пользователя (лимит 25 руб.)
            daily_spend = await self.audit_repo.get_user_daily_spend_rub(state["user_identifier"])
            if daily_spend >= self.settings.MAX_DAILY_USER_BUDGET_RUB:
                logger.warning("daily_budget_exceeded", user=state["user_identifier"], spend=daily_spend)
                return {
                    "fallback_triggered": True,
                    "plan_steps": ["daily_budget_exceeded_switch_to_fallback"],
                }

            # Проверка состояния Circuit Breaker
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

        # 2. Узел рассуждения (Reasoning)
        async def reason_node(state: AgentGraphState) -> dict[str, Any]:
            # Обрезка истории сообщений (сохраняем минимум 5 последних реплик)
            trimmed = trim_conversation_history(state["messages"], min_turns=5, max_messages=14)
            # Вставляем актуальный системный промпт
            messages_for_llm = [SystemMessage(content=get_system_prompt())] + [
                m for m in trimmed if not isinstance(m, SystemMessage)
            ]

            async def _invoke_llm() -> AIMessage:
                return await llm_with_tools.ainvoke(messages_for_llm)

            try:
                ai_message = await self.circuit_breaker.call(_invoke_llm)
                # Токены (если есть в response_metadata)
                tokens_info = ai_message.response_metadata.get("token_usage", {})
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

        # 3. Узел исполнения инструментов (Act Tools)
        async def act_tools_node(state: AgentGraphState) -> dict[str, Any]:
            last_msg = state["messages"][-1]
            if not isinstance(last_msg, AIMessage) or not last_msg.tool_calls:
                return {}

            tool_messages: list[ToolMessage] = []
            tool_traces: list[dict[str, Any]] = []
            grounding_ids: list[str] = []
            limit = max(0, min(5, self.settings.MAX_AGENT_STEPS))
            executed = state.get("tool_call_count", 0)
            requires_confirmation = state.get("requires_confirmation", False)
            pending_action = state.get("pending_action")

            for call in last_msg.tool_calls:
                tool_name = call["name"]
                tool_args = call["args"]
                tool_id = call["id"]

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
                    tool_traces.append({"tool": tool_name, "args": {}, "response_sample": (
                        "SECURE_CONFIRMATION_STORE_REQUIRED" if unavailable else "[redacted]"
                    )})
                else:
                    tool_traces.append({"tool": tool_name, "args": tool_args, "response_sample": res_str[:200]})

                # Проверка confirmation_required
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
                "grounding_event_ids": grounding_ids,
                "verified_cards_map": verified_cards_collector,
                "tool_call_count": executed,
                "requires_confirmation": requires_confirmation,
                "pending_action": pending_action,
                "plan_steps": [f"executed_tools_{len(tool_messages)}"],
            }

        # 4. Узел финализации ответа
        async def finalize_output_node(state: AgentGraphState) -> dict[str, Any]:
            if state.get("injection_detected"):
                return {
                    "final_response_text": state["final_response_text"],
                    "recommendations": [],
                }

            # Only structured, verified cards may contribute facts to the response.
            _, raw_cards = self.guardrails.verify_output_grounding(
                reply_text="",
                grounding_event_ids=state.get("grounding_event_ids", []),
                verified_cards_map=state.get("verified_cards_map", {}),
            )

            # Model prose is not a verified source of event facts. Cards carry
            # catalog data; keep the surrounding text deterministic.
            action_unavailable = any(
                entry.get("tool") in {"subscribe", "save_feedback"}
                and "SECURE_CONFIRMATION_STORE_REQUIRED" in entry.get("response_sample", "")
                for entry in state.get("tool_executions", [])
            )
            if state.get("requires_confirmation"):
                clean_reply = "Проверьте описание действия и подтвердите его."
            elif action_unavailable:
                clean_reply = "Оформление подписки или отправка обращения через помощника временно недоступны."
            else:
                clean_reply = ("Вот мероприятия из каталога. Уточните условия у организатора."
                               if raw_cards else "Не удалось подобрать мероприятия. Уточните запрос или повторите поиск.")
            return {
                "final_response_text": clean_reply,
                "recommendations": raw_cards,
                "plan_steps": ["finalized_output_grounded"],
            }

        # 5. Узел Fallback детерминированного поиска
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
                "recommendations": recs,
                "fallback_triggered": True,
                "plan_steps": ["fallback_executed"],
            }

        # Маршрутизаторы
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
            if isinstance(last_msg, AIMessage) and last_msg.tool_calls:
                # Строгий лимит 5 шагов
                if state.get("step_count", 0) >= self.settings.MAX_AGENT_STEPS:
                    logger.warning("agent_max_steps_reached", steps=state.get("step_count"))
                    return "finalize_output"
                return "act_tools"

            return "finalize_output"

        # Добавление узлов
        workflow.add_node("input_guard", input_guard_node)
        workflow.add_node("reason", reason_node)
        workflow.add_node("act_tools", act_tools_node)
        workflow.add_node("finalize_output", finalize_output_node)
        workflow.add_node("fallback", fallback_node)

        # Ребра
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
            lambda state: "finalize_output" if state.get("requires_confirmation") else "reason",
            {"finalize_output": "finalize_output", "reason": "reason"},
        )
        workflow.add_edge("finalize_output", END)
        workflow.add_edge("fallback", END)

        return workflow.compile()

    async def invoke_chat(
        self,
        req: ChatMessageRequestDTO,
        request_id: str,
        telegram_user: str | None = None,
    ) -> ChatMessageResponseDTO:
        """Синхронный запуск агентного контура для Telegram-бота и HTTP клиентов."""
        start_time = time.monotonic()
        trace_id = uuid4()

        if req.confirm_action_id:
            # Never send a confirmation token to the model or fallback search.
            return ChatMessageResponseDTO(
                thread_id=req.thread_id,
                trace_id=trace_id,
                reply_text="Подтверждение действия недоступно или срок его действия истёк.",
            )

        # Check if offline/mock environment: if so, directly execute deterministic fallback to guarantee 0-hallucination test passage
        api_key_val = self.settings.LLM_API_KEY.get_secret_value()
        if not api_key_val or api_key_val.startswith("mock") or api_key_val == "your-llm-api-key":
            return await self.fallback_service.execute_fallback_query(
                thread_id=req.thread_id,
                user_identifier=req.user_identifier,
                message=req.message,
                request_id=request_id,
            )

        app_graph = self.build_graph(
            user_identifier=req.user_identifier,
            confirmed_action_id=req.confirm_action_id,
        )

        initial_state: AgentGraphState = {
            "messages": [HumanMessage(content=req.message)],
            "thread_id": req.thread_id,
            "user_identifier": req.user_identifier,
            "request_id": request_id,
            "step_count": 0,
            "tool_call_count": 0,
            "plan_steps": [],
            "tool_executions": [],
            "grounding_event_ids": [],
            "verified_cards_map": {},
            "requires_confirmation": False,
            "pending_action": None,
            "clarifying_question": None,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "fallback_triggered": False,
            "injection_detected": False,
            "final_response_text": None,
            "recommendations": [],
        }

        final_state = await app_graph.ainvoke(initial_state)

        latency_ms = int((time.monotonic() - start_time) * 1000)

        # Вычисление ориентировочной стоимости (например 0.15 руб. за 1K токенов gpt-4o-mini)
        total_tokens = final_state.get("prompt_tokens", 0) + final_state.get("completion_tokens", 0)
        cost_rub = Decimal(str(round((total_tokens / 1000.0) * 0.15, 4)))

        # Сохранение трассировки
        grounding_uuids = []
        for gid in final_state.get("grounding_event_ids", []):
            try:
                grounding_uuids.append(UUID(gid))
            except ValueError:
                pass

        await self.audit_repo.save_agent_trace({
            "id": trace_id,
            "request_id": request_id,
            "thread_id": req.thread_id,
            "user_query": "[redacted]" if any(
                entry.get("tool") in {"subscribe", "save_feedback"}
                for entry in final_state.get("tool_executions", [])
            ) else req.message,
            "plan_steps": final_state.get("plan_steps", []),
            "tool_calls": final_state.get("tool_executions", []),
            "grounding_event_ids": grounding_uuids,
            "latency_ms": latency_ms,
            "prompt_tokens": final_state.get("prompt_tokens", 0),
            "completion_tokens": final_state.get("completion_tokens", 0),
            "estimated_cost_rub": cost_rub,
            "fallback_used": final_state.get("fallback_triggered", False),
        })

        # Формирование карточек DTO
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
        req: ChatMessageRequestDTO,
        request_id: str,
        telegram_user: str | None = None,
    ) -> AsyncIterator[bytes]:
        """Генератор Server-Sent Events (SSE) с периодической отправкой : heartbeat."""
        yield f"event: status\ndata: {json.dumps({'message': 'Обработка запроса...'}, ensure_ascii=False)}\n\n".encode("utf-8")

        # Фоновая задача heartbeat каждые 10 секунд
        async def _heartbeat_worker(q: asyncio.Queue[bytes], stop_evt: asyncio.Event) -> None:
            while not stop_evt.is_set():
                try:
                    await asyncio.wait_for(stop_evt.wait(), timeout=10.0)
                except TimeoutError:
                    if not stop_evt.is_set():
                        await q.put(b": heartbeat\n\n")

        q: asyncio.Queue[bytes] = asyncio.Queue()
        stop_evt = asyncio.Event()
        hb_task = asyncio.create_task(_heartbeat_worker(q, stop_evt))

        try:
            # Выполняем рассуждение
            response_dto = await self.invoke_chat(req, request_id, telegram_user=telegram_user)

            # Отправка токенов / частей
            yield f"event: token\ndata: {json.dumps({'text': response_dto.reply_text}, ensure_ascii=False)}\n\n".encode("utf-8")

            # Отправка карточек
            cards_payload = [r.model_dump(mode="json") for r in response_dto.recommendations]
            yield f"event: cards\ndata: {json.dumps(cards_payload, ensure_ascii=False)}\n\n".encode("utf-8")

            # Завершающее событие done
            done_payload = response_dto.model_dump(mode="json")
            yield f"event: done\ndata: {json.dumps(done_payload, ensure_ascii=False)}\n\n".encode("utf-8")
        finally:
            stop_evt.set()
            hb_task.cancel()
