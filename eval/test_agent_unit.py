"""Unit tests for agent boundaries, without optional backend dependencies."""
import importlib.util
import json
import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, Mock, patch
from uuid import UUID, uuid4

# The main checkout contains the modified production files under test. Override
# AGENT_SOURCE_ROOT to run against another checkout.
import os
ROOT = Path(os.environ.get('AGENT_SOURCE_ROOT', Path(__file__).resolve().parents[1]))


def module(name, **attrs):
    result = types.ModuleType(name)
    result.__dict__.update(attrs)
    return result


class Message:
    def __init__(self, content='', **kwargs):
        self.content = content
        self.__dict__.update(kwargs)


class AIMessage(Message):
    def __init__(self, content='', tool_calls=None, **kwargs):
        super().__init__(content, tool_calls=tool_calls or [], **kwargs)


class Tool:
    def __init__(self, fn):
        self.name, self.fn = fn.__name__, fn

    async def ainvoke(self, args):
        return await self.fn(**args)


class DTO:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)

    @classmethod
    def model_validate(cls, value):
        return cls(**(value if isinstance(value, dict) else vars(value)))

    def model_dump(self, **kwargs):
        return self.__dict__


def load_modules():
    stubs = {
        'langchain_core': module('langchain_core'),
        'langchain_core.tools': module('langchain_core.tools', tool=Tool),
        'langchain_core.messages': module('langchain_core.messages', AIMessage=AIMessage, HumanMessage=Message, SystemMessage=Message, ToolMessage=Message),
        'langgraph': module('langgraph'),
        'langgraph.graph': module('langgraph.graph', END='end', START='start', StateGraph=object),
        'app': module('app'), 'app.agent': module('app.agent'), 'app.schemas': module('app.schemas'),
        'app.agent.checkpointer': module('app.agent.checkpointer', trim_conversation_history=lambda m: m),
        'app.agent.prompts': module('app.agent.prompts', SYSTEM_PROMPT='system'),
        'app.agent.state': module('app.agent.state', AgentGraphState=dict),
        'app.schemas.chat': module('app.schemas.chat', AgentRecommendationItemDTO=DTO, ChatMessageResponseDTO=DTO),
        'app.schemas.event': module('app.schemas.event', EventCardDTO=DTO, EventSearchFilterDTO=DTO),
    }
    patcher = patch.dict(sys.modules, stubs)
    patcher.start()
    try:
        loaded = []
        for name in ('tools', 'orchestrator'):
            spec = importlib.util.spec_from_file_location('_test_agent_' + name, ROOT / 'backend' / 'app' / 'agent' / (name + '.py'))
            obj = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(obj)
            loaded.append(obj)
        return *loaded, patcher
    except BaseException:
        patcher.stop()
        raise


class AgentTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tools, self.orch, patcher = load_modules()
        self.addCleanup(patcher.stop)
        self.repo = NS(get_by_id=AsyncMock(), find_similar_events=AsyncMock(), get_venue_schedule=AsyncMock())
        self.sub, self.feedback = Mock(), Mock()
        self.factory = self.tools.AgentToolsFactory(self.repo, Mock(), self.sub, self.feedback, Mock(), NS(sanitize_untrusted_event_data=lambda x: x), 'user', 'confirmed')
        self.toolset = {t.name: t for t in self.factory.get_tools()}

    def orchestrator(self, limit=5):
        obj = self.orch.CulturalAgentOrchestrator.__new__(self.orch.CulturalAgentOrchestrator)
        obj.settings = NS(MAX_AGENT_STEPS=limit, LLM_PROMPT_RUB_PER_MILLION=1, LLM_COMPLETION_RUB_PER_MILLION=1)
        obj.tools_factory = self.factory
        obj.guardrails = NS(check_user_input=lambda text: (True, None),
                            verify_output_grounding=lambda output, cards: {'events': [cards[e['id']] for e in output['events'] if e['id'] in cards]})
        return obj

    async def test_confirmation_fails_closed_without_mutations(self):
        for name, args in [('subscribe', {'city': 'Moscow'}), ('save_feedback', {'message_text': 'hello'})]:
            result = json.loads(await self.toolset[name].ainvoke(args))
            self.assertEqual(result, {'status': 'UNAVAILABLE', 'error': 'SECURE_CONFIRMATION_STORE_REQUIRED'})
        self.assertEqual(self.sub.mock_calls, [])
        self.assertEqual(self.feedback.mock_calls, [])

    async def test_get_event_rejects_drafts(self):
        identifier = str(uuid4())
        for status in ('DRAFT', 'PUBLISHED', 'CANCELLED'):
            self.repo.get_by_id.return_value = NS(id=identifier, status=status)
            result = json.loads(await self.toolset['get_event'].ainvoke({'event_id': identifier}))
            self.assertEqual('event' in result, status != 'DRAFT')
            self.repo.get_by_id.assert_awaited_with(UUID(identifier), include_cancelled=True)

    async def test_similar_and_schedule_filter_unpublished(self):
        identifier = str(uuid4())
        self.repo.get_by_id.return_value = NS(id=identifier, status='PUBLISHED')
        events = [NS(id=str(uuid4()), status=s) for s in ('PUBLISHED', 'DRAFT', 'CANCELLED')]
        self.repo.find_similar_events.return_value = events
        self.repo.get_venue_schedule.return_value = events
        for name, args in [('find_similar', {'event_id': identifier}), ('get_venue_schedule', {'venue': 'v', 'date_from': '2026-01-01', 'date_to': '2026-01-02'})]:
            result = json.loads(await self.toolset[name].ainvoke(args))
            self.assertEqual([e['id'] for e in result['events']], [events[0].id])

    async def test_tool_limit_counts_calls_and_grounds_results(self):
        obj = self.orchestrator(2)
        event_id = str(uuid4())
        self.repo.get_by_id.return_value = NS(id=event_id, status='PUBLISHED')
        calls = [{'name': 'get_event', 'args': {'event_id': event_id}, 'id': str(i)} for i in range(4)]
        result = await obj.act_tools_node({'messages': [Message(tool_calls=calls)], 'step_count': 0})
        self.assertEqual(self.repo.get_by_id.await_count, 2)
        self.assertEqual(result['step_count'], 5)
        self.assertEqual(len(result['tool_Executions']), 2)
        self.assertEqual(result['grounding_event_ids'], [event_id, event_id])
        self.assertEqual(list(result['verified_cards_map']), [event_id])
        self.assertEqual(json.loads(result['messages'][2].content)['error'], 'TOOL_LIMIT_OR_UNKNOWN')

    async def test_finalize_only_recommends_verified_cards(self):
        obj = self.orchestrator()
        obj.audit_repo = NS(save_agent_trace=AsyncMock(return_value=NS(id='trace')))
        event_id = str(uuid4())
        result = await obj.finalize_output_node({'request_id': 'r', 'thread_id': 't', 'messages': [Message(content='query'), AIMessage(content=json.dumps({'event_ids': [event_id, str(uuid4())], 'needs_clarification': False}))], 'grounding_event_ids': [str(uuid4())], 'verified_cards_map': {event_id: {'id': event_id}}})
        self.assertEqual([r.event.id for r in result['final_structured_output']['recommendations']], [event_id])
        self.assertEqual(obj.audit_repo.save_agent_trace.await_args.args[0]['grounding_event_ids'], [event_id])

    async def test_sse_returns_verified_response_and_generic_errors(self):
        obj = self.orchestrator()
        obj.invoke_chat = AsyncMock(return_value=DTO(reply_text='Безопасно', recommendations=[]))
        events = [part async for part in obj.stream_chat_sse(None, 'request')]
        self.assertEqual([event.split(b'\n', 1)[0] for event in events],
                         [b'event: step', b'event: token', b'event: cards', b'event: done'])
        obj.invoke_chat = AsyncMock(side_effect=ValueError('sensitive provider detail'))
        events = [part async for part in obj.stream_chat_sse(None, 'request')]
        self.assertIn(b'event: error', events[-1])
        self.assertNotIn(b'sensitive', events[-1])

    async def test_rejected_input_is_not_checkpointed(self):
        obj = self.orchestrator()
        obj.guardrails = NS(check_user_input=lambda text: (False, 'refused'))
        obj.graph = NS(ainvoke=AsyncMock(return_value={'final_structured_output': {'reply_text': 'refused'}}))
        req = NS(user_identifier='user', thread_id='thread', message='malicious instruction')
        await obj.invoke_chat(req, 'r')
        state = obj.graph.ainvoke.await_args.args[0]
        self.assertTrue(state['blocked_input'])
        self.assertNotIn('malicious instruction', state['messages'][0].content)

    async def test_invoke_resets_state_and_scopes_checkpoint(self):
        obj = self.orchestrator()
        obj.graph = NS(ainvoke=AsyncMock(return_value={'final_structured_output': {'reply_text': 'ok'}}))
        req = NS(user_identifier='user', thread_id='thread', message='hello')
        await obj.invoke_chat(req, 'r1')
        await obj.invoke_chat(req, 'r2')
        first, second = obj.graph.ainvoke.await_args_list
        for call in (first, second):
            for key, expected in {'step_count': 0, 'plan_steps': [], 'tool_Executions': [], 'grounding_event_ids': [], 'verified_cards_map': {}, 'requires_confirmation': False, 'pending_action': None, 'prompt_tokens': 0, 'completion_tokens': 0, 'fallback_triggered': False, 'final_structured_output': None}.items():
                self.assertEqual(call.args[0][key], expected, key)
        self.assertEqual(first.args[1], second.args[1])
        self.assertNotEqual(first.args[1]['configurable']['thread_id'], req.thread_id)
        obj.tools_factory.user_identifier = 'other'
        with self.assertRaises(PermissionError):
            await obj.invoke_chat(req, 'r3')


if __name__ == '__main__':
    unittest.main()
