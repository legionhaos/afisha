from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def choices(items: list[tuple[str, str]], columns: int = 1) -> InlineKeyboardMarkup:
    buttons = [InlineKeyboardButton(text=text, callback_data=data) for text, data in items]
    return InlineKeyboardMarkup(inline_keyboard=[buttons[i:i + columns] for i in range(0, len(buttons), columns)])


def confirmation(token: str) -> InlineKeyboardMarkup:
    return choices([('Подтвердить', f'confirm:{token}'), ('Отмена', f'reject:{token}')], 2)


def main_menu_keyboard() -> InlineKeyboardMarkup:
    rows = []
    rows.append([
        InlineKeyboardButton(text="🔎 Найти событие", callback_data="menu:catalog"),
        InlineKeyboardButton(text="💬 Спросить помощника", callback_data="menu:chat"),
    ])
    rows.append([
        InlineKeyboardButton(text="🔔 Подписки", callback_data="menu:subscriptions"),
        InlineKeyboardButton(text="ℹ️ Как пользоваться", callback_data="menu:help"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)



def paginated_cities(cities: list[str], page: int, prefix: str, all_cities: bool = False) -> InlineKeyboardMarkup:
    """Keep original indices in callbacks, independent of display order."""
    indexed = list(enumerate(cities))
    indexed.sort(key=lambda item: item[1].casefold() != 'уфа')
    entries = [(name[:40], f'{prefix}:{index}') for index, name in indexed]
    if all_cities:
        entries.insert(1 if indexed and indexed[0][1].casefold() == 'уфа' else 0, ('Все города', f'{prefix}:all'))
    total_pages = max(1, (len(entries) + 7) // 8)
    page = max(0, min(page, total_pages - 1))
    markup = choices(entries[page * 8:page * 8 + 8], 2)
    nav = []
    if page:
        nav.append(InlineKeyboardButton(text='← Назад', callback_data=f'citypage:{page - 1}'))
    if page + 1 < total_pages:
        nav.append(InlineKeyboardButton(text='Далее →', callback_data=f'citypage:{page + 1}'))
    if nav:
        markup.inline_keyboard.append(nav)
    markup.inline_keyboard.append([InlineKeyboardButton(text='⌂ Главное меню', callback_data='menu:home')])
    return markup

