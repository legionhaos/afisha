from datetime import datetime, timedelta, timezone
from typing import Any


def format_card(event: dict[str, Any]) -> str:
    date = datetime.fromisoformat(event['date_start'].replace('Z', '+00:00'))
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
    lines = [event['title'], f"{date_text} (UTC+5)", f"{event['city']}, {event['venue']}", event['address'], f"{price} · {event.get('age_limit', 0)}+"]
    if event.get('status') == 'cancelled':
        lines.append(event.get('cancelled_badge') or 'Мероприятие отменено')
    if event.get('description'):
        lines.append(event['description'][:1200])
    if event.get('source_url'):
        lines.append('Источник: ' + event['source_url'])
    if event.get('org_link'):
        lines.append('Организатор: ' + event['org_link'])
    return '\n'.join(lines)[:4000]
