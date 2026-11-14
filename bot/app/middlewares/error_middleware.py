import logging

from aiogram import Router
from aiogram.types import ErrorEvent

router = Router()
logger = logging.getLogger(__name__)


@router.errors()
async def unexpected_error(event: ErrorEvent) -> bool:
    # Do not log user messages, backend responses, or Telegram tokens.
    logger.error('Unhandled bot error: %s', type(event.exception).__name__)
    update = event.update
    message = update.message or (update.callback_query.message if update.callback_query else None)
    if update.callback_query:
        try:
            await update.callback_query.answer()
        except Exception:
            pass
    if message:
        try:
            await message.answer('Произошла ошибка. Попробуйте ещё раз или используйте /cancel.')
        except Exception:
            pass
    return True
