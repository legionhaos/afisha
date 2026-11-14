import os
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo


def choices(items: list[tuple[str, str]], columns: int = 1) -> InlineKeyboardMarkup:
    buttons = [InlineKeyboardButton(text=text, callback_data=data) for text, data in items]
    return InlineKeyboardMarkup(inline_keyboard=[buttons[i:i + columns] for i in range(0, len(buttons), columns)])


def confirmation(token: str) -> InlineKeyboardMarkup:
    return choices([('Подтвердить', f'confirm:{token}'), ('Отмена', f'reject:{token}')], 2)


def main_menu_keyboard(webapp_url: str | None = None) -> InlineKeyboardMarkup:
    url = webapp_url or os.getenv("WEBAPP_URL", "http://localhost:3000/miniapp").strip()
    rows = []
    if url:
        rows.append([InlineKeyboardButton(text="✨ Открыть Афишу (Mini App)", web_app=WebAppInfo(url=url))])
    rows.append([
        InlineKeyboardButton(text="🔎 Найти событие", callback_data="menu:catalog"),
        InlineKeyboardButton(text="💬 Спросить помощника", callback_data="menu:chat"),
    ])
    rows.append([
        InlineKeyboardButton(text="🔔 Подписки", callback_data="menu:subscriptions"),
        InlineKeyboardButton(text="ℹ️ Как пользоваться", callback_data="menu:help"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)

