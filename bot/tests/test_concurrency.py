import asyncio
from unittest.mock import AsyncMock

import pytest
from aiogram import Bot
from aiogram.types import Update

from app.handlers.commands import ask_confirmation, router
from app.main import create_dispatcher


def update(number, user, text=None, callback=None):
    person = {'id': user, 'is_bot': False, 'first_name': 'User'}
    chat = {'id': user, 'type': 'private'}
    if callback is not None:
        return Update.model_validate({'update_id': number, 'callback_query': {'id': str(number), 'from': person, 'chat_instance': '1', 'data': callback, 'message': {'message_id': 99, 'date': 1700000000, 'chat': chat, 'from': {'id': 123456, 'is_bot': True, 'first_name': 'Bot'}}}})
    return Update.model_validate({'update_id': number, 'message': {'message_id': number, 'date': 1700000000, 'chat': chat, 'from': person, 'text': text}})


@pytest.mark.asyncio
async def test_slow_user_does_not_block_other_user_but_same_user_is_serialized():
    bot = Bot('123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi')
    bot.session.make_request = AsyncMock()
    dp = create_dispatcher()
    entered = asyncio.Event()
    release = asyncio.Event()
    async def dictionaries():
        entered.set()
        await release.wait()
        return {'cities': [{'name': 'Уфа'}]}
    api = type('API', (), {'dictionaries': AsyncMock(side_effect=dictionaries)})()
    first = asyncio.create_task(dp.feed_update(bot, update(1, 2, '/catalog'), api=api))
    try:
        await asyncio.wait_for(entered.wait(), 2)
        same = asyncio.create_task(dp.feed_update(bot, update(2, 2, '/cancel'), api=api))
        other = asyncio.create_task(dp.feed_update(bot, update(3, 3, '/help'), api=api))
        await asyncio.wait_for(other, 2)
        assert not same.done()
        release.set()
        await asyncio.wait_for(asyncio.gather(first, same), 2)
        ctx = dp.fsm.get_context(bot=bot, chat_id=2, user_id=2)
        assert await ctx.get_state() is None
        assert await ctx.get_data() == {}
    finally:
        release.set()
        await dp.storage.close()
        await dp.fsm.events_isolation.close()
        await bot.session.close()
        dp.sub_routers.remove(router)
        router._parent_router = None


@pytest.mark.asyncio
async def test_double_confirmation_only_mutates_once():
    bot = Bot('123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi')
    bot.session.make_request = AsyncMock()
    dp = create_dispatcher()
    entered = asyncio.Event()
    release = asyncio.Event()
    payload = {'user_identifier': 'tg:2', 'telegram_chat_id': 2, 'city': 'Уфа', 'category': None, 'period_type': 'all'}
    sub = {'id': '1', **payload, 'is_active': True}
    async def subscribe(data):
        entered.set()
        await release.wait()
        return sub
    api = type('API', (), {'subscribe': AsyncMock(side_effect=subscribe), 'subscriptions': AsyncMock(return_value=[sub])})()
    ctx = dp.fsm.get_context(bot=bot, chat_id=2, user_id=2)
    msg = type('Message', (), {'answer': AsyncMock()})()
    await ask_confirmation(msg, ctx, {'kind': 'subscribe', 'payload': payload}, 'Подтвердить')
    token = (await ctx.get_data())['pending']['token']
    first = asyncio.create_task(dp.feed_update(bot, update(1, 2, callback='confirm:' + token), api=api))
    try:
        await asyncio.wait_for(entered.wait(), 2)
        second = asyncio.create_task(dp.feed_update(bot, update(2, 2, callback='confirm:' + token), api=api))
        await asyncio.sleep(0.05)
        assert not second.done()
        release.set()
        await asyncio.wait_for(asyncio.gather(first, second), 2)
        api.subscribe.assert_awaited_once_with(payload)
    finally:
        release.set()
        await dp.storage.close()
        await dp.fsm.events_isolation.close()
        await bot.session.close()
        dp.sub_routers.remove(router)
        router._parent_router = None
