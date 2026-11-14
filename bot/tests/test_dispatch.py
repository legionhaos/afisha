from unittest.mock import AsyncMock

import pytest
from aiogram import Bot, Dispatcher
from aiogram.types import Update

from app.handlers.commands import router


@pytest.mark.asyncio
async def test_real_dispatch_start_and_filter_flow():
    bot = Bot('123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi')
    bot.session.make_request = AsyncMock()
    dp = Dispatcher()
    dp.include_router(router)
    api = type('API', (), {})()
    api.dictionaries = AsyncMock(side_effect=[{'cities': [{'name': 'Уфа'}]}, {'categories': [{'category': 'theater', 'title_ru': 'Театр'}]}])
    api.events = AsyncMock(return_value={'items': [], 'total': 0, 'page': 1, 'page_size': 5, 'empty_explanation': {'message': 'Не найдено'}})
    user = {'id': 2, 'is_bot': False, 'first_name': 'User'}
    chat = {'id': 2, 'type': 'private'}
    async def text(update_id, content):
        update = Update.model_validate({'update_id': update_id, 'message': {'message_id': update_id, 'date': 1700000000, 'chat': chat, 'from': user, 'text': content}})
        await dp.feed_update(bot, update, api=api)
    async def click(update_id, content):
        update = Update.model_validate({'update_id': update_id, 'callback_query': {'id': str(update_id), 'from': user, 'chat_instance': '1', 'data': content, 'message': {'message_id': 99, 'date': 1700000000, 'chat': chat, 'from': {'id': 123456, 'is_bot': True, 'first_name': 'Bot'}}}})
        await dp.feed_update(bot, update, api=api)
    try:
        await text(1, '/start')
        await text(2, '/catalog')
        await click(3, 'city:0')
        await click(4, 'category:0')
        await click(5, 'date:weekend')
        await click(6, 'price:free')
        api.events.assert_awaited_once_with({'city': 'Уфа', 'category': 'theater', 'date_preset': 'weekend', 'is_free': 'true', 'page_size': 5, 'page': 1})
        api.dictionaries = AsyncMock(return_value={'cities': [{'name': 'Уфа'}]})
        api.chat = AsyncMock(side_effect=[
            {'clarifying_question': 'В каком городе?', 'recommendations': []},
            {'reply_text': 'Результаты поиска', 'recommendations': []},
        ])
        await text(7, '/catalog')
        await text(8, '/cancel')
        await text(9, 'выставка')
        await text(10, 'уфа')
        assert api.chat.await_count == 2
        assert api.chat.await_args.args[0]['message'] == 'выставка. Город: Уфа'
        assert any('отменён' in str(call) for call in bot.session.make_request.await_args_list)
    finally:
        await dp.storage.close()
        await bot.session.close()
        dp.sub_routers.remove(router)
        router._parent_router = None
