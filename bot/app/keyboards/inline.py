from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def choices(items: list[tuple[str, str]], columns: int = 1) -> InlineKeyboardMarkup:
    buttons = [InlineKeyboardButton(text=text, callback_data=data) for text, data in items]
    return InlineKeyboardMarkup(inline_keyboard=[buttons[i:i + columns] for i in range(0, len(buttons), columns)])


def confirmation(token: str) -> InlineKeyboardMarkup:
    return choices([('Подтвердить', f'confirm:{token}'), ('Отмена', f'reject:{token}')], 2)
