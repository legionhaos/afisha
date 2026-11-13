#!/usr/bin/env python3
"""Load explicitly fictional events into a local test database, never production.

Run from backend: python scripts/seed_hackathon_demo.py
The operation inserts only missing fixed demo records and does not alter existing data.
Cities: https://ru.wikipedia.org/wiki/Городские_населённые_пункты_Башкортостана
(21 cities, including the closed city Межгорье; excludes two urban-type settlements).
"""
import asyncio
import hashlib
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.models.dictionary import City
from app.models.enums import EventCategory, EventStatus, SourceType
from app.models.event import Event

CITIES = (
    'Агидель', 'Баймак', 'Белебей', 'Белорецк', 'Бирск', 'Благовещенск',
    'Давлеканово', 'Дюртюли', 'Ишимбай', 'Кумертау', 'Межгорье', 'Мелеуз',
    'Нефтекамск', 'Октябрьский', 'Салават', 'Сибай', 'Стерлитамак',
    'Туймазы', 'Уфа', 'Учалы', 'Янаул',
)
TEMPLATES = (
    (EventCategory.CONCERT, 'Музыкальный вечер', 0, True, 6),
    (EventCategory.THEATER, 'Семейный спектакль', 350, False, 6),
    (EventCategory.EXHIBITION, 'Выставка народного творчества', 0, True, 0),
)
PREFIX = 'afisha-local-demo-v1:'


async def seed() -> None:
    engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    created_cities = created_events = 0
    try:
        async with session_factory() as session:
            existing_cities = set((await session.execute(select(City.name))).scalars())
            for name in CITIES:
                if name not in existing_cities:
                    session.add(City(name=name, normalized_name=name.casefold()))
                    created_cities += 1
            now = datetime.now(timezone.utc)
            local_now = now.astimezone(timezone(timedelta(hours=5)))
            # Fixed month slots make repeat runs idempotent while keeping the demo upcoming.
            first_day = local_now.replace(day=1, hour=14, minute=0, second=0, microsecond=0)
            for city in CITIES:
                for index, (category, title, price, free, age) in enumerate(TEMPLATES):
                    key = f'{PREFIX}{city}:{category.value}:{first_day:%Y-%m}'
                    event_id = uuid5(NAMESPACE_URL, key)
                    if await session.get(Event, event_id):
                        continue
                    date_start = first_day + timedelta(days=35 + index * 2)
                    label = f'[ДЕМО] {title} — {city}'
                    digest = hashlib.sha256(key.encode('utf-8')).hexdigest()
                    session.add(Event(
                        id=event_id, title=label, normalized_title=label.casefold(),
                        category=category, tags=['демо', 'тест'], date_start=date_start,
                        date_end=date_start + timedelta(hours=2), duration_min=120,
                        city=city, venue='Демонстрационная площадка',
                        address=f'{city}, адрес вымышленный — демо',
                        description='ДЕМО: вымышленное мероприятие для проверки работы сервиса. Не является реальным событием.',
                        price_min=price, price_max=price, is_free=free, age_limit=age,
                        source_url='https://example.org/demo', source_type=SourceType.MANUAL,
                        source_hash=digest, verified_at=now, confidence=1.0,
                        status=EventStatus.PUBLISHED, is_disputed=False, dedup_key=digest,
                    ))
                    created_events += 1
            await session.commit()
        print(f'Городов в справочнике: {len(CITIES)}; добавлено городов: {created_cities}; добавлено ДЕМО-событий: {created_events}.')
    finally:
        await engine.dispose()


if __name__ == '__main__':
    asyncio.run(seed())
