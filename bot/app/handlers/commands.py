import secrets
from typing import Any
from uuid import uuid4

from aiogram import F, Router
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.api_client import APIClient, APIError
from app.formatters.card_formatter import format_card
from app.keyboards.inline import choices, confirmation
from app.states import Flow

router = Router()
HELP = ('Команды: /catalog — поиск по каталогу, /subscribe — подписаться, '
        '/subscriptions — мои подписки, /unsubscribe — отписаться от всех, '
        '/cancel — отменить текущий сценарий, /help — помощь. '
        'Или отправьте вопрос о мероприятиях обычным текстом.')


def user_id(message: Message) -> str:
    return f'tg:{message.from_user.id}'


async def error(message: Message, exc: APIError) -> None:
    await message.answer(exc.user_message)


@router.message(CommandStart())
async def start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer('Здравствуйте! Это афиша мероприятий Башкортостана.\n' + HELP)


@router.message(Command('help'))
async def help_command(message: Message) -> None:
    await message.answer(HELP)


@router.message(Command('cancel'))
async def cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer('Текущий сценарий отменён. Для нового диалога отправьте вопрос.')


async def show_city(message: Message, state: FSMContext, api: APIClient, subscription: bool) -> None:
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
    await callback.message.answer('Выберите категорию:', reply_markup=choices(items))


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
        await callback.message.answer('Выберите период:', reply_markup=choices([('Все мероприятия', 'period:all'), ('Выходные', 'period:weekend')]))
    else:
        await state.set_state(Flow.date)
        await callback.message.answer('Выберите дату (UTC+5). «Выходные» — ближайшие суббота и воскресенье; «Неделя» — сегодня и следующие 7 дней.', reply_markup=choices([('Любая', 'date:all'), ('Сегодня', 'date:today'), ('Завтра', 'date:tomorrow'), ('Выходные', 'date:weekend'), ('Неделя', 'date:week')]))


@router.callback_query(F.data.startswith('date:'), StateFilter(Flow.date))
async def select_date(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    value = callback.data.split(':', 1)[1]
    if value not in ('all', 'today', 'tomorrow', 'weekend', 'week'):
        return
    await state.update_data(date_preset=None if value == 'all' else value)
    await state.set_state(Flow.price)
    await callback.message.answer('Выберите цену. Ограничение «до» применяется к минимальной цене билета; другие билеты могут стоить дороже.', reply_markup=choices([('Любая', 'price:all'), ('Бесплатно', 'price:free'), ('До 500 ₽', 'price:500'), ('До 1000 ₽', 'price:1000')]))


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
    await show_page(callback.message, state, api, 1)


async def show_page(message: Message, state: FSMContext, api: APIClient, page: int) -> None:
    data = await state.get_data()
    if 'filters' not in data or page < 1:
        await message.answer('Начните поиск заново: /catalog')
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
        await message.answer('\n'.join([text, *suggestions])[:4000])
        return
    page = result['page']
    await state.update_data(page_ids=[str(event['id']) for event in items], page=page)
    buttons = [(event['title'][:60], f"event:{event['id']}") for event in items]
    if page > 1:
        buttons.append(('Назад', f'page:{page - 1}'))
    if page * result['page_size'] < result['total']:
        buttons.append(('Далее', f'page:{page + 1}'))
    await message.answer(f"Найдено: {result['total']}. Страница {page}.", reply_markup=choices(buttons))


@router.callback_query(F.data.startswith('page:'))
async def page_callback(callback: CallbackQuery, state: FSMContext, api: APIClient) -> None:
    await callback.answer()
    value = callback.data.split(':', 1)[1]
    data = await state.get_data()
    if value.isdecimal() and abs(int(value) - data.get('page', 0)) == 1:
        await show_page(callback.message, state, api, int(value))


@router.callback_query(F.data.startswith('event:'))
async def event_callback(callback: CallbackQuery, state: FSMContext, api: APIClient) -> None:
    await callback.answer()
    event_id = callback.data.split(':', 1)[1]
    data = await state.get_data()
    if event_id not in data.get('page_ids', []):
        await callback.message.answer('Эта страница устарела. Начните поиск заново: /catalog')
        return
    try:
        event = await api.event(event_id)
        await callback.message.answer(format_card(event), disable_web_page_preview=True)
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
async def list_subscriptions(message: Message, api: APIClient) -> None:
    try:
        items = await api.subscriptions(user_id(message))
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
        await callback.message.answer('Подтверждение устарело или уже использовано.')
        return
    await state.update_data(pending=None)
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    if verb == 'reject':
        await callback.message.answer('Действие отменено.')
        return
    try:
        if pending['kind'] == 'subscribe':
            payload = pending['payload']
            result = await api.subscribe(payload)
            try:
                items = await api.subscriptions(payload['user_identifier'])
            except APIError:
                await callback.message.answer('Не удалось проверить сохранение подписки. Результат неизвестен; проверьте /subscriptions позже.')
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
                await callback.message.answer('Подписка активна с указанными параметрами.')
            else:
                await callback.message.answer('Ошибка: подписка с указанными параметрами не обнаружена при проверке. Изменение не подтверждено.')
        elif pending['kind'] == 'unsubscribe':
            user = pending['user']
            before = await api.subscriptions(user)
            if not before:
                await callback.message.answer('Активных подписок нет; удалять нечего.')
                return
            await api.unsubscribe(user)
            try:
                after = await api.subscriptions(user)
            except APIError:
                await callback.message.answer('Не удалось проверить удаление подписок. Результат неизвестен; проверьте /subscriptions позже.')
                return
            if after:
                await callback.message.answer('Ошибка: после удаления остались активные подписки. Изменение не подтверждено.')
            else:
                await callback.message.answer('Проверено: активных подписок больше нет.')
    except APIError as exc:
        if pending['kind'] in ('subscribe', 'unsubscribe') and (exc.status is None or exc.status >= 500):
            await callback.message.answer('Не удалось получить надёжный результат операции. Проверьте /subscriptions перед повторной попыткой.')
        else:
            await error(callback.message, exc)


async def send_chat(message: Message, state: FSMContext, api: APIClient, payload: dict[str, Any]) -> None:
    result = await api.chat(payload)
    text = result.get('reply_text') or ''
    for part in (result.get('clarifying_question'), result.get('fallback_notice')):
        if part and part not in text:
            text += '\n' + part
    if text.strip():
        await message.answer(text[:4000])
    for recommendation in result.get('recommendations', []):
        event = recommendation.get('event')
        if event:
            explanation = recommendation.get('constraint_match_explanation', '')
            await message.answer((format_card(event)[:3000] + ('\n\n' + explanation if explanation else ''))[:4000], disable_web_page_preview=True)
    if result.get('requires_confirmation'):
        await message.answer('Подтверждение действий через чат сейчас недоступно; действие не выполнено. Для подписки используйте /subscribe.')


@router.message(F.text, StateFilter(None))
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
    payload = {'thread_id': thread, 'user_identifier': user_id(message), 'message': message.text}
    try:
        await send_chat(message, state, api, payload)
    except APIError as exc:
        await error(message, exc)


@router.message()
async def other(message: Message) -> None:
    await message.answer('Используйте кнопки текущего сценария или /cancel для отмены.')


@router.callback_query()
async def stale(callback: CallbackQuery) -> None:
    await callback.answer('Кнопка устарела. Начните заново.', show_alert=True)
