from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from app.api_client import APIError
from app.handlers.commands import chat_city_callback, idle_text, menu_callback, send_chat, start
from app.states import Flow


@pytest.fixture
async def state():
    storage = MemoryStorage()
    yield FSMContext(storage, StorageKey(bot_id=1, chat_id=2, user_id=2))
    await storage.close()


def make_message():
    return SimpleNamespace(answer=AsyncMock(), from_user=SimpleNamespace(id=999), chat=SimpleNamespace(id=2))


def make_callback(message, action):
    return SimpleNamespace(message=message, data=f'menu:{action}', answer=AsyncMock(), from_user=SimpleNamespace(id=2))


@pytest.mark.asyncio
async def test_start_has_navigation(state):
    message = make_message()
    await start(message, state)
    call = message.answer.await_args
    assert 'Привет!' in call.args[0]
    assert 'menu:catalog' in str(call.kwargs['reply_markup'])
    assert 'menu:subscriptions' in str(call.kwargs['reply_markup'])


@pytest.mark.asyncio
async def test_menu_actions_use_clicking_user(state):
    message = make_message()
    api = SimpleNamespace(subscriptions=AsyncMock(return_value=[]))
    await menu_callback(make_callback(message, 'list'), state, api)
    api.subscriptions.assert_awaited_once_with('tg:2')
    await menu_callback(make_callback(message, 'unsubscribe'), state, api)
    assert (await state.get_data())['pending']['user'] == 'tg:2'


@pytest.mark.asyncio
async def test_catalog_offline_is_explained(state):
    message = make_message()
    api = SimpleNamespace(dictionaries=AsyncMock(side_effect=APIError()))
    await menu_callback(make_callback(message, 'catalog'), state, api)
    assert 'недоступен' in message.answer.await_args.args[0]


@pytest.mark.asyncio
async def test_chat_menu_clears_previous_flow(state):
    await state.set_state('Flow:city')
    message = make_message()
    await menu_callback(make_callback(message, 'chat'), state, SimpleNamespace())
    assert await state.get_state() == Flow.assistant.state
    assert 'Напиши' in message.answer.await_args.args[0]


@pytest.mark.asyncio
async def test_fallback_asks_city_before_showing_unrelated_cards(state):
    message = make_message()
    api = SimpleNamespace(chat=AsyncMock(return_value={'is_fallback_mode': True, 'clarifying_question': 'В каком городе?', 'recommendations': []}), dictionaries=AsyncMock(return_value={'cities': [{'name': 'Уфа'}, {'name': 'Белебей'}]}))
    await send_chat(message, state, api, {'message': 'куда сходить'})
    assert await state.get_state() == Flow.chat_city.state
    assert message.answer.await_count == 1
    assert 'В каком городе' in message.answer.await_args.args[0]


@pytest.mark.asyncio
async def test_city_selection_preserves_query_and_rejects_other_cities(state):
    await state.set_state(Flow.chat_city)
    await state.update_data(chat_pending_message='бесплатный концерт', chat_cities=['Уфа'])
    message = make_message()
    api = SimpleNamespace(chat=AsyncMock(return_value={'is_fallback_mode': True, 'recommendations': [{'event': {'city': 'Белебей'}}]}))
    await chat_city_callback(make_callback(message, 'unused').__class__(message=message, data='chatcity:0', answer=AsyncMock(), from_user=SimpleNamespace(id=2)), state, api)
    payload = api.chat.await_args.args[0]
    assert 'бесплатный концерт' in payload['message'] and 'Уфа' in payload['message']
    assert payload['user_identifier'] == 'tg:2'
    assert 'ничего не нашлось' in message.answer.await_args.args[0]


@pytest.mark.asyncio
async def test_idle_message_does_not_start_assistant():
    message = make_message()
    await idle_text(message)
    assert 'нажми «Спросить помощника»' in message.answer.await_args.args[0]
    assert 'menu:chat' in str(message.answer.await_args.kwargs['reply_markup'])


@pytest.mark.asyncio
async def test_city_fallback_sends_single_notice_and_keeps_assistant_mode(state):
    await state.set_state(Flow.chat_city)
    await state.update_data(chat_pending_message='хочу на концерт', chat_cities=['Уфа'])
    message = make_message()
    event = {'title': '[ДЕМО] Концерт', 'date_start': '2027-01-01T10:00:00Z', 'city': 'Уфа', 'venue': 'Демо', 'address': 'Демо', 'is_free': True, 'age_limit': 6}
    api = SimpleNamespace(chat=AsyncMock(return_value={'is_fallback_mode': True, 'recommendations': [{'event': event}]}))
    callback = SimpleNamespace(message=message, data='chatcity:0', answer=AsyncMock(), from_user=SimpleNamespace(id=2))
    await chat_city_callback(callback, state, api)
    messages = [call.args[0] for call in message.answer.await_args_list]
    assert sum('упрощённый поиск' in text.lower() for text in messages) == 1
    assert await state.get_state() == Flow.assistant.state
    assert any('[ДЕМО] Концерт' in text for text in messages)


@pytest.mark.asyncio
async def test_menu_callback_edits_existing_message(state):
    message = make_message()
    message.edit_text = AsyncMock()
    await menu_callback(make_callback(message, 'chat'), state, SimpleNamespace())
    message.edit_text.assert_awaited_once()
    message.answer.assert_not_awaited()
    assert await state.get_state() == Flow.assistant.state


@pytest.mark.asyncio
async def test_fallback_with_city_does_not_ask_city_again(state):
    message = make_message()
    api = SimpleNamespace(chat=AsyncMock(return_value={'is_fallback_mode': True, 'reply_text': 'Ничего не найдено', 'recommendations': []}), dictionaries=AsyncMock())
    await send_chat(message, state, api, {'message': 'концерты в уфе'})
    api.dictionaries.assert_not_awaited()
    assert 'Ничего не найдено' in message.answer.await_args.args[0]


@pytest.mark.asyncio
async def test_rock_or_hockey_prompts_city_buttons(state):
    message = make_message()
    api = SimpleNamespace(chat=AsyncMock(return_value={'is_fallback_mode': True, 'clarifying_question': 'В каком городе ищем события?', 'recommendations': []}), dictionaries=AsyncMock(return_value={'cities': [{'name': 'Уфа'}, {'name': 'Салават'}]}))
    await send_chat(message, state, api, {'message': 'хочу посмотреть хоккей'})
    assert await state.get_state() == Flow.chat_city.state
    assert 'Уфа' in str(message.answer.await_args.kwargs['reply_markup'])
    assert (await state.get_data())['chat_pending_message'] == 'хочу посмотреть хоккей'
