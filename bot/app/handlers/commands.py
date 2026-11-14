import re
import secrets
from typing import Any
from uuid import uuid4

from aiogram import F, Router
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.exceptions import TelegramBadRequest

from app.api_client import APIClient, APIError
from app.formatters.card_formatter import format_card
from app.keyboards.inline import choices, confirmation, main_menu_keyboard
from app.states import Flow

router = Router()
WELCOME = (
    '<b>🎭 Афиша Республики Башкортостан</b>\n\n'
    'Привет! Я помогу найти интересные события в Башкортостане: '
    'спектакли, концерты, выставки и фестивали.\n\n'
    'Выбери действие в меню ниже или открой <b>Mini App</b> для интерактивного просмотра. '
    'Для свободного вопроса нажми «Спросить помощника».'
)
HELP = (
    '<b>ℹ️ Как пользоваться ботом</b>\n\n'
    '✨ <b>Mini App</b> — интерактивная афиша с карточками и фильтрами.\n'
    '🔎 <b>«Найти событие»</b> — пошаговый поиск по городу, категории, дате и цене.\n'
    '💬 <b>«Спросить помощника»</b> — задай любой вопрос своими словами (ИИ-поиск).\n'
    '🔔 <b>«Подписки»</b> — настройка и просмотр персональных уведомлений.\n\n'
    '<code>/cancel</code> — отменить текущий поиск или начать новый диалог.\n'
    '<code>/start</code> — вернуться в главное меню.'
)


def main_menu():
    return main_menu_keyboard()


def subscriptions_menu():
    return choices([('➕ Оформить подписку', 'menu:subscribe'),
                    ('📋 Мои подписки', 'menu:list'),
                    ('🗑 Отписаться от всех', 'menu:unsubscribe'),
                    ('← Главное меню', 'menu:home')])


async def update_screen(message: Message, text: str, **kwargs: Any) -> None:
    """Edit a bot-owned callback message; fall back to a new message if unavailable."""
    if not hasattr(message, 'edit_text'):
        await message.answer(text[:4000], **kwargs)
        return
    try:
        await message.edit_text(text[:4000], **kwargs)
    except TelegramBadRequest as exc:
        if 'message is not modified' not in str(exc).lower():
            await message.answer(text[:4000], **kwargs)


def user_id(message: Message) -> str:
    return f'tg:{message.from_user.id}'


async def error(message: Message, exc: APIError) -> None:
    await message.answer(exc.user_message)


@router.message(CommandStart())
async def start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(WELCOME, reply_markup=main_menu())


@router.message(Command('help'))
async def help_command(message: Message) -> None:
    await message.answer(HELP, reply_markup=main_menu())


@router.message(Command('cancel'))
async def cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer('Готово, предыдущий сценарий отменён. Что будем искать?', reply_markup=main_menu())


async def show_city(message: Message, state: FSMContext, api: APIClient, subscription: bool, edit: bool = False) -> None:
    try:
        data = await api.dictionaries()
    except APIError as exc:
        await error(message, exc)
        return
    cities = [c['name'] for c in data.get('cities', [])]
    if not cities and subscription:
        await message.answer('В справочнике пока нет городов для подписки.')
        return
    await state.clear()
    await state.update_data(cities=cities)
    await state.set_state(Flow.subscription_city if subscription else Flow.city)
    items = [(name, f'city:{i}') for i, name in enumerate(cities[:90])]
    if not subscription:
        items.insert(0, ('Все города', 'city:all'))
    if edit:
        await update_screen(message, 'Выберите город:', reply_markup=choices(items))
    else:
        await message.answer('Выберите город:', reply_markup=choices(items))


@router.message(Command('catalog'))
async def catalog(message: Message, state: FSMContext, api: APIClient) -> None:
    await show_city(message, state, api, False)


@router.message(Command('subscribe'))
async def subscribe(message: Message, state: FSMContext, api: APIClient) -> None:
    await show_city(message, state, api, True)


@router.callback_query(F.data.startswith('city:'), StateFilter(Flow.city, Flow.subscription_city))
async def select_city(callback: CallbackQuery, state: FSMContext, api: APIClient) -> None:
    await callback.answer()
    current = await state.get_state()
    data = await state.get_data()
    value = callback.data.split(':', 1)[1]
    if value == 'all' and current == Flow.city.state:
        city = None
    elif value.isdecimal() and int(value) < min(len(data['cities']), 90):
        city = data['cities'][int(value)]
    else:
        return
    try:
        dictionaries = await api.dictionaries(city)
    except APIError as exc:
        await error(callback.message, exc)
        return
    categories = dictionaries.get('categories', [])
    await state.update_data(city=city, categories=categories)
    await state.set_state(Flow.subscription_category if current == Flow.subscription_city.state else Flow.category)
    items = [('Все категории', 'category:all')] + [(c['title_ru'], f'category:{i}') for i, c in enumerate(categories[:90])]
    await update_screen(callback.message, 'Выберите категорию:', reply_markup=choices(items))


@router.callback_query(F.data.startswith('category:'), StateFilter(Flow.category, Flow.subscription_category))
async def select_category(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    current = await state.get_state()
    data = await state.get_data()
    value = callback.data.split(':', 1)[1]
    if value == 'all':
        category = None
    elif value.isdecimal() and int(value) < min(len(data['categories']), 90):
        category = data['categories'][int(value)]['category']
    else:
        return
    await state.update_data(category=category)
    if current == Flow.subscription_category.state:
        await state.set_state(Flow.subscription_period)
        await update_screen(callback.message, 'Выберите период:', reply_markup=choices([('Все мероприятия', 'period:all'), ('Выходные', 'period:weekend')]))
    else:
        await state.set_state(Flow.date)
        await update_screen(callback.message, 'Выберите дату (UTC+5). «Выходные» — ближайшие суббота и воскресенье; «Неделя» — сегодня и следующие 7 дней.', reply_markup=choices([('Любая', 'date:all'), ('Сегодня', 'date:today'), ('Завтра', 'date:tomorrow'), ('Выходные', 'date:weekend'), ('Неделя', 'date:week')]))


@router.callback_query(F.data.startswith('date:'), StateFilter(Flow.date))
async def select_date(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    value = callback.data.split(':', 1)[1]
    if value not in ('all', 'today', 'tomorrow', 'weekend', 'week'):
        return
    await state.update_data(date_preset=None if value == 'all' else value)
    await state.set_state(Flow.price)
    await update_screen(callback.message, 'Выберите цену. Ограничение «до» применяется к минимальной цене билета; другие билеты могут стоить дороже.', reply_markup=choices([('Любая', 'price:all'), ('Бесплатно', 'price:free'), ('До 500 ₽', 'price:500'), ('До 1000 ₽', 'price:1000')]))


@router.callback_query(F.data.startswith('price:'), StateFilter(Flow.price))
async def select_price(callback: CallbackQuery, state: FSMContext, api: APIClient) -> None:
    await callback.answer()
    value = callback.data.split(':', 1)[1]
    if value not in ('all', 'free', '500', '1000'):
        return
    data = await state.get_data()
    filters = {key: data[key] for key in ('city', 'category', 'date_preset') if data.get(key)}
    if value == 'free':
        filters['is_free'] = 'true'
    elif value != 'all':
        filters['price_max'] = int(value)
    filters['page_size'] = 5
    await state.update_data(filters=filters)
    await state.set_state(None)
    await state.update_data(last_catalog_city=data.get('city'))
    await show_page(callback.message, state, api, 1, edit=True)


async def show_page(message: Message, state: FSMContext, api: APIClient, page: int, edit: bool = False) -> None:
    async def display(text: str, **kwargs: Any) -> None:
        if edit:
            await update_screen(message, text, **kwargs)
        else:
            await message.answer(text, **kwargs)
    data = await state.get_data()
    if 'filters' not in data or page < 1:
        await display('Начните поиск заново: /catalog')
        return
    try:
        result = await api.events({**data['filters'], 'page': page})
    except APIError as exc:
        await error(message, exc)
        return
    items = result.get('items', [])
    if not items:
        await state.update_data(page_ids=[], page=page)
        explanation = result.get('empty_explanation') or {}
        text = explanation.get('message') or 'Мероприятий не найдено.'
        suggestions = explanation.get('suggested_relaxations') or []
        await display('\n'.join([text, *suggestions])[:4000], reply_markup=main_menu())
        return
    page = result['page']
    await state.update_data(page_ids=[str(event['id']) for event in items], page=page)
    buttons = [(event['title'][:60], f"event:{event['id']}") for event in items]
    if page > 1:
        buttons.append(('Назад', f'page:{page - 1}'))
    if page * result['page_size'] < result['total']:
        buttons.append(('Далее', f'page:{page + 1}'))
    await display(f"Найдено: {result['total']}. Страница {page}.", reply_markup=choices(buttons))


@router.callback_query(F.data.startswith('page:'))
async def page_callback(callback: CallbackQuery, state: FSMContext, api: APIClient) -> None:
    await callback.answer()
    value = callback.data.split(':', 1)[1]
    data = await state.get_data()
    if value.isdecimal() and abs(int(value) - data.get('page', 0)) <= 1 and int(value) >= 1:
        await show_page(callback.message, state, api, int(value), edit=True)


@router.callback_query(F.data.startswith('event:'))
async def event_callback(callback: CallbackQuery, state: FSMContext, api: APIClient) -> None:
    await callback.answer()
    event_id = callback.data.split(':', 1)[1]
    data = await state.get_data()
    if event_id not in data.get('page_ids', []):
        await update_screen(callback.message, 'Эта страница устарела. Начните поиск заново: /catalog')
        return
    try:
        event = await api.event(event_id)
        await update_screen(callback.message, format_card(event), disable_web_page_preview=True, reply_markup=choices([('← К результатам', f"page:{data.get('page', 1)}"), ('⌂ Главное меню', 'menu:home')]))
    except APIError as exc:
        await error(callback.message, exc)


async def ask_confirmation(message: Message, state: FSMContext, action: dict[str, Any], summary: str) -> None:
    token = secrets.token_urlsafe(12)
    await state.update_data(pending={'token': token, **action})
    await message.answer(summary[:3800], reply_markup=confirmation(token))


@router.callback_query(F.data.startswith('period:'), StateFilter(Flow.subscription_period))
async def select_period(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    value = callback.data.split(':', 1)[1]
    if value not in ('all', 'weekend'):
        return
    data = await state.get_data()
    payload = {'user_identifier': user_id(callback.message), 'telegram_chat_id': callback.message.chat.id,
               'city': data['city'], 'category': data.get('category'), 'period_type': value}
    # callback.message.from_user is the bot, not the person who clicked.
    payload['user_identifier'] = f'tg:{callback.from_user.id}'
    await state.set_state(None)
    await ask_confirmation(callback.message, state, {'kind': 'subscribe', 'payload': payload},
                           f"Оформить подписку: {data['city']}, {data.get('category') or 'все категории'}, {'выходные' if value == 'weekend' else 'все мероприятия'}?")


@router.message(Command('subscriptions'))
async def list_subscriptions(message: Message, api: APIClient, identifier: str | None = None) -> None:
    try:
        items = await api.subscriptions(identifier or user_id(message))
    except APIError as exc:
        await error(message, exc)
        return
    if not items:
        await message.answer('Активных подписок нет.')
        return
    text = '\n'.join(f"{item['city']} · {item.get('category') or 'все категории'} · {item['period_type']}" for item in items)
    await message.answer(('Ваши подписки:\n' + text + '\nДля удаления всех подписок: /unsubscribe')[:4000])


@router.message(Command('unsubscribe'))
async def unsubscribe(message: Message, state: FSMContext) -> None:
    await state.set_state(None)
    await ask_confirmation(message, state, {'kind': 'unsubscribe', 'user': user_id(message)}, 'Удалить все ваши подписки?')


@router.callback_query(F.data.startswith(('confirm:', 'reject:')))
async def confirm(callback: CallbackQuery, state: FSMContext, api: APIClient) -> None:
    await callback.answer()
    verb, token = callback.data.split(':', 1)
    data = await state.get_data()
    pending = data.get('pending')
    if not pending or not secrets.compare_digest(token, pending['token']):
        await update_screen(callback.message, 'Подтверждение устарело или уже использовано.')
        return
    await state.update_data(pending=None)
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    if verb == 'reject':
        await update_screen(callback.message, 'Действие отменено.')
        return
    try:
        if pending['kind'] == 'subscribe':
            payload = pending['payload']
            result = await api.subscribe(payload)
            try:
                items = await api.subscriptions(payload['user_identifier'])
            except APIError:
                await update_screen(callback.message, 'Не удалось проверить сохранение подписки. Результат неизвестен; проверьте /subscriptions позже.')
                return
            matching = any(
                item.get('id') == result.get('id') and result.get('id') is not None
                and item.get('user_identifier') == payload['user_identifier']
                and item.get('city') == payload['city']
                and item.get('category') == payload['category']
                and item.get('period_type') == payload['period_type']
                and item.get('telegram_chat_id') == payload['telegram_chat_id']
                and item.get('is_active') is True
                for item in items
            )
            if matching:
                await update_screen(callback.message, 'Подписка активна с указанными параметрами.')
            else:
                await update_screen(callback.message, 'Ошибка: подписка с указанными параметрами не обнаружена при проверке. Изменение не подтверждено.')
        elif pending['kind'] == 'unsubscribe':
            user = pending['user']
            before = await api.subscriptions(user)
            if not before:
                await update_screen(callback.message, 'Активных подписок нет; удалять нечего.')
                return
            await api.unsubscribe(user)
            try:
                after = await api.subscriptions(user)
            except APIError:
                await update_screen(callback.message, 'Не удалось проверить удаление подписок. Результат неизвестен; проверьте /subscriptions позже.')
                return
            if after:
                await update_screen(callback.message, 'Ошибка: после удаления остались активные подписки. Изменение не подтверждено.')
            else:
                await update_screen(callback.message, 'Проверено: активных подписок больше нет.')
    except APIError as exc:
        if pending['kind'] in ('subscribe', 'unsubscribe') and (exc.status is None or exc.status >= 500):
            await update_screen(callback.message, 'Не удалось получить надёжный результат операции. Проверьте /subscriptions перед повторной попыткой.')
        else:
            await error(callback.message, exc)


async def send_chat(message: Message, state: FSMContext, api: APIClient, payload: dict[str, Any]) -> None:
    result = await api.chat(payload)
    if result.get('is_fallback_mode'):
        await state.update_data(last_fallback_query=payload['message'])
    else:
        await state.update_data(last_fallback_query=None)
    question = (result.get('clarifying_question') or '')
    if 'город' in question.lower() and not result.get('recommendations'):
        try:
            dictionaries = await api.dictionaries()
        except APIError:
            await message.answer('Сейчас не удалось уточнить город. Попробуй позже или выбери поиск через /catalog.')
            return
        cities = [city['name'] for city in dictionaries.get('cities', []) if city.get('name')]
        if not cities:
            await message.answer('Сейчас не удалось получить список городов. Попробуй позже.')
            return
        previous_city = (await state.get_data()).get('last_catalog_city')
        await state.update_data(chat_pending_message=payload['message'], chat_cities=cities)
        await state.set_state(Flow.chat_city)
        keyboard = []
        if previous_city in cities:
            keyboard.append((f'📍 {previous_city} (из прошлого поиска)', f"chatcity:{cities.index(previous_city)}"))
        keyboard.extend((name, f'chatcity:{i}') for i, name in enumerate(cities[:90]) if name != previous_city)
        await message.answer('В каком городе ищем? Выбери из списка — тогда покажу подходящие события.', reply_markup=choices(keyboard, 2))
        return
    text = result.get('reply_text') or ''
    for part in (result.get('clarifying_question'),):
        if part and part not in text:
            text += '\n' + part
    cards = [format_card(item['event']) for item in result.get('recommendations', []) if item.get('event')]
    if cards:
        text += '\n\n' + '\n\n──────────\n\n'.join(cards)
    if result.get('requires_confirmation'):
        text += '\n\nПодтверждение действий через чат недоступно; действие не выполнено. Используй /subscribe.'
    if text.strip():
        await message.answer(text[:4000], disable_web_page_preview=True, reply_markup=choices([('← Главное меню', 'menu:home')]))


@router.callback_query(F.data.startswith('chatcity:'), StateFilter(Flow.chat_city))
async def chat_city_callback(callback: CallbackQuery, state: FSMContext, api: APIClient) -> None:
    await callback.answer()
    data = await state.get_data()
    index = callback.data.split(':', 1)[1]
    cities = data.get('chat_cities', [])
    if not index.isdecimal() or int(index) >= min(len(cities), 90):
        await update_screen(callback.message, 'Не удалось выбрать город. Попробуй /start.')
        return
    city = cities[int(index)]
    original = data.get('chat_pending_message', '')
    await state.set_state(Flow.assistant)
    await state.update_data(confirmed_city=None, chat_pending_message=None, chat_cities=[])
    await update_screen(callback.message, f'Ищу события: {city}.')
    try:
        result = await api.chat({'thread_id': str(uuid4()), 'user_identifier': f'tg:{callback.from_user.id}', 'message': f'{original}. Город: {city}'})
        items = [entry['event'] for entry in result.get('recommendations', []) if entry.get('event') and entry['event'].get('city', '').casefold() == city.casefold()]
        intro = result.get('reply_text') or ('Вот что удалось найти.' if items else 'По запросу ничего не нашлось.')
        if not items and result.get('recommendations'):
            intro = 'В выбранном городе ничего не нашлось по запросу.'
        if result.get('is_fallback_mode') and items:
            intro = 'Нашёл подходящие события в каталоге. Сейчас работает упрощённый поиск.'
        text = intro + ('\n\n' + '\n\n──────────\n\n'.join(format_card(event) for event in items) if items else '')
        await update_screen(callback.message, text, disable_web_page_preview=True, reply_markup=choices([('← Главное меню', 'menu:home')]))
    except APIError as exc:
        await error(callback.message, exc)


@router.callback_query(F.data.startswith('menu:'))
async def menu_callback(callback: CallbackQuery, state: FSMContext, api: APIClient) -> None:
    await callback.answer()
    action = callback.data.split(':', 1)[1]
    if action == 'home':
        await state.clear()
        await update_screen(callback.message, WELCOME, reply_markup=main_menu())
    elif action == 'catalog':
        await state.clear()
        await show_city(callback.message, state, api, False, edit=True)
    elif action == 'chat':
        previous = await state.get_data()
        await state.clear()
        await state.update_data(last_catalog_city=previous.get('last_catalog_city'))
        await state.set_state(Flow.assistant)
        await update_screen(callback.message, 'Напиши, какое событие ищешь. Например: «Концерт в Уфе на выходных».', reply_markup=choices([('← Главное меню', 'menu:home')]))
    elif action == 'subscriptions':
        await state.clear()
        await update_screen(callback.message, '🔔 Подписки\n\nВыбери действие:', reply_markup=subscriptions_menu())
    elif action == 'subscribe':
        await state.clear()
        await show_city(callback.message, state, api, True, edit=True)
    elif action == 'list':
        await state.clear()
        await list_subscriptions(callback.message, api, f'tg:{callback.from_user.id}')
    elif action == 'unsubscribe':
        await state.clear()
        await ask_confirmation(callback.message, state, {'kind': 'unsubscribe', 'user': f'tg:{callback.from_user.id}'}, 'Удалить все ваши подписки?')
    elif action == 'help':
        await update_screen(callback.message, HELP, reply_markup=main_menu())


@router.message(F.text, StateFilter(Flow.assistant))
async def chat(message: Message, state: FSMContext, api: APIClient) -> None:
    if message.text.startswith('/'):
        await message.answer('Неизвестная команда. /help — список команд.')
        return
    if len(message.text) > 2000:
        await message.answer('Сообщение должно содержать не более 2000 символов.')
        return
    data = await state.get_data()
    thread = data.get('thread_id') or str(uuid4())
    await state.update_data(thread_id=thread, pending=None)
    text = message.text.strip()
    previous = data.get('last_fallback_query')
    if previous and re.fullmatch(r'(?:а\s+)?(?:на\s+)?следующ(?:ей|ую)\s*(?:неделе|неделю)?[?!.\s]*', text, re.IGNORECASE):
        previous = re.sub(r'\b(?:на\s+)?(?:этой|следующей)\s+неделе\b', '', previous, flags=re.IGNORECASE)
        previous = re.sub(r'\b(?:сегодня|завтра|на\s+выходных|в\s+субботу|в\s+воскресенье)\b', '', previous, flags=re.IGNORECASE)
        text = f'{previous.strip()} на следующей неделе'[:2000]
    payload = {'thread_id': thread, 'user_identifier': user_id(message), 'message': text}
    try:
        await send_chat(message, state, api, payload)
    except APIError as exc:
        await error(message, exc)


@router.message(F.text, StateFilter(Flow.chat_city))
async def chat_city_text(message: Message, state: FSMContext, api: APIClient) -> None:
    data = await state.get_data()
    text = message.text.strip().lower().replace('ё', 'е')
    words = set(re.findall(r'[а-яa-z-]+', text))
    city = None
    for name in data.get('chat_cities', []):
        normalized = name.lower().replace('ё', 'е')
        forms = {normalized}
        if normalized == 'уфа':
            forms.update({'уфе', 'уфу', 'уфы'})
        elif normalized.endswith('а') and len(normalized) > 4:
            forms.update({normalized[:-1] + suffix for suffix in ('е', 'у', 'ы')})
        elif normalized.endswith('й') and len(normalized) > 4:
            forms.update({normalized[:-1] + suffix for suffix in ('ом', 'ого')})
        elif len(normalized) > 4 and normalized[-1] not in 'оеьы':
            forms.update({normalized + suffix for suffix in ('е', 'а', 'у', 'ом')})
        if forms & words or (' ' in normalized and re.search(rf'(?<!\w){re.escape(normalized)}(?!\w)', text)):
            city = name
            break
    if not city:
        await message.answer('Не нашёл такой город. Напиши его название или выбери кнопку; /cancel отменяет поиск.')
        return
    original = data.get('chat_pending_message', '')
    await state.set_state(Flow.assistant)
    await state.update_data(chat_pending_message=None, chat_cities=[])
    payload = {'thread_id': data.get('thread_id') or str(uuid4()), 'user_identifier': user_id(message),
               'message': f'{original}. Город: {city}'}
    try:
        await send_chat(message, state, api, payload)
    except APIError as exc:
        await error(message, exc)


@router.message(F.text, StateFilter(None))
async def idle_text(message: Message, state: FSMContext, api: APIClient) -> None:
    if message.text.startswith('/'):
        await message.answer('Неизвестная команда. /help — список команд.')
        return
    await state.set_state(Flow.assistant)
    await chat(message, state, api)


@router.message()
async def other(message: Message) -> None:
    await message.answer('Используйте кнопки текущего сценария или /cancel для отмены.')


@router.callback_query()
async def stale(callback: CallbackQuery) -> None:
    await callback.answer('Кнопка устарела. Начните заново.', show_alert=True)
