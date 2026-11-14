from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from app.handlers.commands import (city_page_callback, select_city, navigation_callback,
                                   show_city, show_page, chat_city_callback)
from app.keyboards.inline import paginated_cities
from app.states import Flow


@pytest.fixture
async def state():
    storage = MemoryStorage()
    yield FSMContext(storage, StorageKey(bot_id=1, chat_id=1, user_id=1))
    await storage.close()


def callback(message, data):
    return SimpleNamespace(message=message, data=data, answer=AsyncMock(), from_user=SimpleNamespace(id=1))


def message():
    return SimpleNamespace(answer=AsyncMock(), edit_text=AsyncMock(), from_user=SimpleNamespace(id=1), chat=SimpleNamespace(id=1))


def test_city_pages_cover_all_original_indices():
    cities = [f'Город {i}' for i in range(101)] + ['Уфа']
    seen = []
    for page in range(13):
        rows = paginated_cities(cities, page, 'city', True).inline_keyboard
        for row in rows:
            assert len(row) <= 2
            seen.extend(b.callback_data for b in row if b.callback_data.startswith('city:'))
    assert seen[:2] == ['city:101', 'city:all']
    assert set(seen) == {'city:all'} | {f'city:{i}' for i in range(102)}


@pytest.mark.asyncio
@pytest.mark.parametrize('subscription', [False, True])
async def test_last_city_and_back(state, subscription):
    cities = [f'Город {i}' for i in range(18)] + ['Уфа']
    api = SimpleNamespace(dictionaries=AsyncMock(side_effect=[{'cities': [{'name': c} for c in cities]}, {'categories': []}]))
    msg = message()
    await show_city(msg, state, api, subscription)
    await city_page_callback(callback(msg, 'citypage:1'), state)
    await city_page_callback(callback(msg, 'citypage:2'), state)
    await select_city(callback(msg, 'city:17'), state, api)
    api.dictionaries.assert_awaited_with('Город 17')
    assert (await state.get_data())['city'] == 'Город 17'
    await navigation_callback(callback(msg, 'nav:city'), state, api)
    assert (await state.get_data())['city_page'] == 2
    assert 'city:17' in str(msg.edit_text.await_args.kwargs['reply_markup'])
    assert await state.get_state() == (Flow.subscription_city.state if subscription else Flow.city.state)


@pytest.mark.asyncio
async def test_invalid_page_and_chat_last_city(state):
    cities = [f'Город {i}' for i in range(100)]
    await state.set_state(Flow.chat_city)
    await state.update_data(chat_cities=cities, chat_pending_message='концерт', city_page=0)
    msg = message()
    await city_page_callback(callback(msg, 'citypage:12'), state)
    assert (await state.get_data())['city_page'] == 0
    api = SimpleNamespace(chat=AsyncMock(return_value={'recommendations': []}))
    await chat_city_callback(callback(msg, 'chatcity:99'), state, api)
    assert api.chat.await_args.args[0]['message'] == 'концерт. Город: Город 99'
    assert await state.get_state() == Flow.assistant.state


@pytest.mark.asyncio
async def test_results_rows_and_server_page(state):
    await state.update_data(filters={'city': 'Уфа', 'page_size': 5})
    msg = message()
    events = [{'id': str(i), 'title': 'Д' * 100} for i in range(5)]
    api = SimpleNamespace(events=AsyncMock(return_value={'items': events, 'page': 2, 'page_size': 5, 'total': 20}))
    await show_page(msg, state, api, 2)
    api.events.assert_awaited_once_with({'city': 'Уфа', 'page_size': 5, 'page': 2})
    rows = msg.answer.await_args.kwargs['reply_markup'].inline_keyboard
    assert [len(row) for row in rows] == [2, 2, 1, 2, 1, 1]
    assert all(len(button.text) <= 60 for row in rows[:3] for button in row)
    assert [b.callback_data for b in rows[3]] == ['page:1', 'page:3']
    assert (await state.get_data())['page_ids'] == [str(i) for i in range(5)]
