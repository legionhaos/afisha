from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from app.api_client import APIClient, APIError
from app.formatters.card_formatter import format_card
from app.handlers.commands import ask_confirmation, confirm, send_chat, show_page


@pytest.fixture
async def state():
    storage = MemoryStorage()
    yield FSMContext(storage, StorageKey(bot_id=1, chat_id=2, user_id=2))
    await storage.close()


def message():
    return SimpleNamespace(answer=AsyncMock(), edit_reply_markup=AsyncMock(), chat=SimpleNamespace(id=2), from_user=SimpleNamespace(id=2))


def callback(msg, data):
    return SimpleNamespace(message=msg, data=data, answer=AsyncMock(), from_user=SimpleNamespace(id=2))


@pytest.mark.asyncio
async def test_api_contract():
    requests = []
    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={'items': [], 'total': 0, 'page': 1, 'page_size': 5})
    api = APIClient('http://backend/api/v1', transport=httpx.MockTransport(handler))
    await api.events({'city': 'Уфа', 'page': 1, 'page_size': 5})
    assert requests[0].url.path == '/api/v1/events'
    assert requests[0].url.params['city'] == 'Уфа'
    await api.close()


@pytest.mark.asyncio
async def test_api_status_and_network_error():
    api = APIClient('http://backend/api/v1', transport=httpx.MockTransport(lambda request: httpx.Response(429)))
    with pytest.raises(APIError) as exc:
        await api.events({})
    assert 'много запросов' in exc.value.user_message
    await api.close()
    def fail(request):
        raise httpx.ConnectError('offline', request=request)
    api = APIClient('http://backend/api/v1', transport=httpx.MockTransport(fail))
    with pytest.raises(APIError) as exc:
        await api.events({})
    assert exc.value.status is None
    await api.close()


def test_card_uses_backend_fields():
    card = {'title': 'Событие', 'date_start': '2026-01-01T10:00:00Z', 'city': 'Уфа', 'venue': 'Зал', 'address': 'Адрес', 'is_free': True, 'age_limit': 6, 'source_url': 'https://example.org', 'status': 'cancelled'}
    text = format_card(card)
    assert '01.01.2026 15:00' in text
    assert 'Бесплатно' in text and 'отменено' in text and 'https://example.org' in text


@pytest.mark.asyncio
async def test_pagination_and_empty_explanation(state):
    msg = message()
    await state.update_data(filters={'city': 'Уфа', 'page_size': 5})
    api = SimpleNamespace(events=AsyncMock(return_value={'items': [{'id': '123', 'title': 'Тест'}], 'total': 6, 'page': 1, 'page_size': 5}))
    await show_page(msg, state, api, 1)
    api.events.assert_awaited_once_with({'city': 'Уфа', 'page_size': 5, 'page': 1})
    assert (await state.get_data())['page_ids'] == ['123']
    assert 'Далее' in str(msg.answer.await_args.kwargs['reply_markup'])
    api.events.return_value = {'items': [], 'empty_explanation': {'message': 'Ничего', 'suggested_relaxations': ['Смените дату']}}
    await show_page(msg, state, api, 1)
    assert 'Смените дату' in msg.answer.await_args.args[0]
    assert (await state.get_data())['page_ids'] == []


@pytest.mark.asyncio
async def test_confirmation_single_use_and_rejection(state):
    msg = message()
    payload = {'user_identifier': 'tg:2', 'telegram_chat_id': 2, 'city': 'Уфа', 'category': None, 'period_type': 'all'}
    subscription = {'id': 'sub-id', **payload, 'is_active': True}
    api = SimpleNamespace(subscribe=AsyncMock(return_value=subscription), unsubscribe=AsyncMock(), subscriptions=AsyncMock(return_value=[subscription]))
    await ask_confirmation(msg, state, {'kind': 'subscribe', 'payload': payload}, 'Подтвердить?')
    token = (await state.get_data())['pending']['token']
    await confirm(callback(msg, 'reject:' + token), state, api)
    await confirm(callback(msg, 'confirm:' + token), state, api)
    api.subscribe.assert_not_awaited()
    await ask_confirmation(msg, state, {'kind': 'subscribe', 'payload': payload}, 'Подтвердить?')
    token = (await state.get_data())['pending']['token']
    await confirm(callback(msg, 'confirm:' + token), state, api)
    await confirm(callback(msg, 'confirm:' + token), state, api)
    api.subscribe.assert_awaited_once_with(payload)


@pytest.mark.asyncio
@pytest.mark.parametrize('action_id', ['server-token', 'sub_123', None])
async def test_chat_confirmation_is_disabled(state, action_id):
    msg = message()
    api = SimpleNamespace(chat=AsyncMock(return_value={'reply_text': 'Подтвердите', 'requires_confirmation': True, 'pending_action_id': action_id}))
    payload = {'thread_id': 'thread', 'user_identifier': 'tg:2', 'message': 'Выполнить действие'}
    await send_chat(msg, state, api, payload)
    assert not (await state.get_data()).get('pending')
    assert 'недоступно' in msg.answer.await_args.args[0]
    api.chat.assert_awaited_once_with(payload)


def test_unknown_price_is_not_free():
    event = {'title': 'Событие', 'date_start': '2026-01-01T10:00:00Z', 'city': 'Уфа', 'venue': 'Зал', 'address': 'Адрес', 'is_free': False, 'price_min': 0, 'price_max': 0}
    assert 'Цена не указана' in format_card(event)
