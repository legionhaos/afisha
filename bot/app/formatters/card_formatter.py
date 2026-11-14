import html
from datetime import datetime, timedelta, timezone
from typing import Any


def format_card(event: dict[str, Any]) -> str:
    raw_date = event.get('date_start', '')
    date = datetime.fromisoformat(str(raw_date).replace('Z', '+00:00'))
    date_text = date.astimezone(timezone(timedelta(hours=5))).strftime('%d.%m.%Y %H:%M')
    if event.get('is_free'):
        price = 'Бесплатно'
    elif not event.get('price_min') and not event.get('price_max'):
        price = 'Цена не указана'
    elif event.get('price_min') == event.get('price_max'):
        price = f"{event['price_min']} ₽"
    elif not event.get('price_min'):
        price = f"До {event['price_max']} ₽"
    elif not event.get('price_max'):
        price = f"От {event['price_min']} ₽"
    else:
        price = f"{event['price_min']}–{event['price_max']} ₽"

    title = html.escape(str(event.get('title', 'Без названия')))
    city = html.escape(str(event.get('city', '')))
    venue = html.escape(str(event.get('venue', '')))
    address = html.escape(str(event.get('address', '')))
    age = event.get('age_limit', 0)

    image_banner = f'<a href="{html.escape(str(event["image_url"]))}">&#8205;</a>' if event.get("image_url") else ""

    lines = [
        f"{image_banner}<b>🎭 {title}</b>",
        f"📅 <b>Дата:</b> {date_text} (UTC+5)",
        f"📍 <b>Место:</b> {city}, {venue}",
        f"🏢 <b>Адрес:</b> {address}",
        f"💳 <b>Билеты:</b> {price} · {age}+",
    ]
    if event.get('status') == 'cancelled':
        badge = html.escape(event.get('cancelled_badge') or 'Мероприятие отменено')
        lines.append(f"⚠️ <b>{badge}</b>")
    if event.get('description'):
        clean_desc = html.escape(str(event['description'])[:1200])
        lines.append(f"<blockquote>{clean_desc}</blockquote>")
    if event.get('source_url') and event['source_url'] != 'https://example.org/demo':
        src = html.escape(event['source_url'])
        lines.append(f'🔗 Источник: <a href="{src}">{src}</a>')
    if event.get('org_link'):
        org = html.escape(event['org_link'])
        lines.append(f'🎟 Организатор: <a href="{org}">{org}</a>')
    return '\n'.join(lines)[:4000]

