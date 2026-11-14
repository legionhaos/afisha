from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from app.api_client import APIError
from app.handlers.commands import ask_confirmation, confirm, send_chat


@pytest.fixture
async def state():
    storage = MemoryStorage()
    yield FSMContext(storage, StorageKey(bot_id=1, chat_id=2, user_id=2))
    await storage.close()


def message():
    return SimpleNamespace(answer=AsyncMock(), edit_reply_markup=AsyncMock())


async def run_confirmation(state, msg, api, action):
    await ask_confirmation(msg, state, action, 'Подтвердите')
    token = (await state.get_data())['pending']['token']
    cb = SimpleNamespace(message=msg, answer=AsyncMock(), data='confirm:' + token)
    await confirm(cb, state, api)
    return msg.answer.await_args.args[0]


PAYLOAD = {'user_identifier': 'tg:2', 'telegram_chat_id': 2, 'city': 'Уфа', 'category': None, 'period_type': 'all'}
SUB = {'id': '1', **PAYLOAD, 'is_active': True}


@pytest.mark.parametrize('items,success', [([SUB], True), ([], False), ([{**SUB, 'period_type': 'weekend'}], False), ([{**SUB, 'id': '2'}], False), ([{**SUB, 'telegram_chat_id': None}], False)])
async def test_create_read_back(state, items, success):
    msg = message()
    api = SimpleNamespace(subscribe=AsyncMock(return_value=SUB), subscriptions=AsyncMock(return_value=items))
    text = await run_confirmation(state, msg, api, {'kind': 'subscribe', 'payload': PAYLOAD})
    api.subscriptions.assert_awaited_once_with('tg:2')
    assert ('Подписка активна' in text) is success
    if not success:
        assert 'Ошибка' in text


async def test_create_get_failure_is_unknown(state):
    msg = message()
    api = SimpleNamespace(subscribe=AsyncMock(return_value=SUB), subscriptions=AsyncMock(side_effect=APIError()))
    text = await run_confirmation(state, msg, api, {'kind': 'subscribe', 'payload': PAYLOAD})
    assert 'неизвестен' in text


@pytest.mark.parametrize('before,after,expected,called', [
    ([], [], 'удалять нечего', False),
    ([SUB], [], 'активных подписок больше нет', True),
    ([SUB], [SUB], 'Ошибка', True),
])
async def test_delete_read_back(state, before, after, expected, called):
    msg = message()
    api = SimpleNamespace(unsubscribe=AsyncMock(return_value={'deleted': 1}), subscriptions=AsyncMock(side_effect=[before, after]))
    text = await run_confirmation(state, msg, api, {'kind': 'unsubscribe', 'user': 'tg:2'})
    assert expected in text
    assert api.unsubscribe.await_count == int(called)
    assert api.subscriptions.await_count == (2 if called else 1)


@pytest.mark.parametrize('responses,deleted', [([APIError()], False), ([ [SUB], APIError()], True)])
async def test_delete_get_failure(state, responses, deleted):
    msg = message()
    api = SimpleNamespace(unsubscribe=AsyncMock(return_value={'deleted': 1}), subscriptions=AsyncMock(side_effect=responses))
    text = await run_confirmation(state, msg, api, {'kind': 'unsubscribe', 'user': 'tg:2'})
    assert api.unsubscribe.await_count == int(deleted)
    assert 'удалено' not in text.lower()
    if deleted:
        assert 'неизвестен' in text


async def test_mutation_timeout_warns_result_unknown(state):
    msg = message()
    api = SimpleNamespace(subscribe=AsyncMock(side_effect=APIError()))
    text = await run_confirmation(state, msg, api, {'kind': 'subscribe', 'payload': PAYLOAD})
    assert 'Проверьте /subscriptions' in text


async def test_agent_subscription_confirmation_disabled(state):
    msg = message()
    api = SimpleNamespace(chat=AsyncMock(return_value={'reply_text': 'Подтвердите', 'requires_confirmation': True, 'pending_action_id': 'sub_123', 'pending_action_summary': 'Подписаться?'}))
    await send_chat(msg, state, api, {'thread_id': 't', 'user_identifier': 'tg:2', 'message': 'подписка'})
    assert not (await state.get_data()).get('pending')
    assert '/subscribe' in msg.answer.await_args.args[0]
