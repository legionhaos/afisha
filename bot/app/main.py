import asyncio
import logging
import os

from aiogram import Bot, Dispatcher, F
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.fsm.storage.memory import SimpleEventIsolation

from app.api_client import APIClient
from app.config import Settings
from app.handlers.commands import router
from app.middlewares.error_middleware import unexpected_error


def create_dispatcher() -> Dispatcher:
    dispatcher = Dispatcher(events_isolation=SimpleEventIsolation())
    router.message.filter(F.chat.type == 'private')
    router.callback_query.filter(F.message.chat.type == 'private')
    dispatcher.errors.register(unexpected_error)
    dispatcher.include_router(router)
    return dispatcher


async def run() -> None:
    settings = Settings.load()
    logging.basicConfig(level=logging.INFO)
    api = APIClient(settings.api_base_url, settings.timeout)
    proxy = os.getenv('BOT_PROXY_URL', '').strip()
    bot = Bot(settings.token, session=AiohttpSession(proxy=proxy) if proxy else None)
    dispatcher = create_dispatcher()
    try:
        await dispatcher.start_polling(bot, api=api, handle_as_tasks=True)
    finally:
        await api.close()
        await bot.session.close()


def main() -> None:
    asyncio.run(run())


if __name__ == '__main__':
    main()
