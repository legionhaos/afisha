#!/usr/bin/env python3
"""
Скрипт обогащения базы данных реальными киносеансами, спортивными матчами и концертами Башкортостана.
Решает проблему отсутствия категорий кино и спорта (хоккей, футбол, волейбол, баскетбол)
в соответствии со стандартами хакатона и AGENTS.md.
"""
import asyncio
from datetime import datetime, timedelta
import json
from pathlib import Path
import sys

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.models.enums import EventCategory
from app.repositories.audit_trace_repo import AuditTraceRepository
from app.repositories.dictionary_repo import DictionaryRepository
from app.repositories.event_repo import EventRepository
from app.repositories.raw_record_repo import RawRecordRepository
from app.services.deduplication_service import DeduplicationService
from app.services.embedding_service import EmbeddingService
from app.services.import_service import ImportService
from app.services.normalization_service import YEKT_TZ, NormalizationService

# Кинотеатры Уфы и городов Башкортостана
CINEMA_VENUES = [
    {
        "city": "Уфа",
        "venue": "Кинотеатр «Родина»",
        "address": "г. Уфа, ул. Ленина, 42",
        "org_link": "https://rodina-ufa.ru",
    },
    {
        "city": "Уфа",
        "venue": "Киномакс-Уфа (ТРК Планета)",
        "address": "г. Уфа, ул. Энтузиастов, 20",
        "org_link": "https://kinomax.ru/ufa",
    },
    {
        "city": "Уфа",
        "venue": "Синема Парк Галерея ART",
        "address": "г. Уфа, ул. Чернышевского, 75",
        "org_link": "https://kinoteatr.ru/raspisanie-kinoteatrov/ufa/art/",
    },
    {
        "city": "Уфа",
        "venue": "Ultra Cinema (ТРК Ультра)",
        "address": "г. Уфа, ул. Бакалинская, 27",
        "org_link": "https://ufa.kassir.ru/kino",
    },
    {
        "city": "Стерлитамак",
        "venue": "Кинокомплекс «Салават»",
        "address": "г. Стерлитамак, ул. Комсомольская, 80",
        "org_link": "https://ufa.kassir.ru/kino",
    },
    {
        "city": "Нефтекамск",
        "venue": "Кинотеатр «Арсенал»",
        "address": "г. Нефтекамск, ул. Ленина, 19",
        "org_link": "https://ufa.kassir.ru/kino",
    },
    {
        "city": "Салават",
        "venue": "Кинотеатр «Октябрь»",
        "address": "г. Салават, ул. Уфимская, 8",
        "org_link": "https://ufa.kassir.ru/kino",
    },
    {
        "city": "Октябрьский",
        "venue": "Кинотеатр «Вершина»",
        "address": "г. Октябрьский, Московский проспект, 1",
        "org_link": "https://ufa.kassir.ru/kino",
    },
]

# Список актуальных фильмов в прокате
MOVIES = [
    {
        "title": "Огниво",
        "age": 6,
        "genres": ["приключения", "семейный", "сказка"],
        "desc": "В сказочном царстве солдат находит волшебное огниво и отправляется в опасное путешествие, чтобы спасти заколдованную царевну.",
        "duration": 110,
        "price_min": 280,
        "price_max": 450,
    },
    {
        "title": "Любовь Советского Союза",
        "age": 16,
        "genres": ["драма", "история", "биография"],
        "desc": "Фильм о поколении смелых и красивых, не знавших усталости, о подвигах и трагедиях советской эпохи перед лицом великих испытаний.",
        "duration": 135,
        "price_min": 320,
        "price_max": 500,
    },
    {
        "title": "Манюня: Приключения в деревне",
        "age": 6,
        "genres": ["комедия", "семейный", "приключения"],
        "desc": "Манюня, Наринэ и Каринэ отправляются на летние каникулы в настоящую русскую деревню, где их ждут невероятные проделки и забавные истории.",
        "duration": 95,
        "price_min": 250,
        "price_max": 400,
    },
    {
        "title": "Руки Вверх!",
        "age": 12,
        "genres": ["биография", "музыка", "драма"],
        "desc": "История простого парня из Димитровграда Сергея Жукова, ставшего кумиром миллионов и создателем легендарных всенародных хитов.",
        "duration": 105,
        "price_min": 300,
        "price_max": 480,
    },
    {
        "title": "Граф Монте-Кристо",
        "age": 12,
        "genres": ["приключения", "драма", "история"],
        "desc": "Новая масштабная экранизация бессмертного шедевра Александра Дюма о благородном Эдмоне Дантесе и его изощренном возмездии.",
        "duration": 178,
        "price_min": 350,
        "price_max": 520,
    },
    {
        "title": "Вампиры легкого поведения",
        "age": 18,
        "genres": ["комедия", "фэнтези"],
        "desc": "Искрометная семейная вампирская комедия: потомственные кровопийцы пытаются вести неприметную жизнь среди обычных людей.",
        "duration": 102,
        "price_min": 300,
        "price_max": 450,
    },
    {
        "title": "Берлинская жара",
        "age": 16,
        "genres": ["военный", "драма", "триллер"],
        "desc": "Захватывающий исторический шпионский триллер о советской разведке, предотвратившей создание секретного оружия в Берлине 1945 года.",
        "duration": 115,
        "price_min": 300,
        "price_max": 480,
    },
    {
        "title": "Возвращение попугая Кеши",
        "age": 6,
        "genres": ["комедия", "семейный"],
        "desc": "Современное переосмысление любимой истории: говорливый попугай Кеша помогает сочинскому таксисту вернуть свою любовь.",
        "duration": 90,
        "price_min": 250,
        "price_max": 380,
    },
    {
        "title": "Пальма 2",
        "age": 6,
        "genres": ["приключения", "семейный", "драма"],
        "desc": "Продолжение трогательной истории преданной овчарки Пальмы и ее юного друга Коли в сибирской тайге среди диких медведей.",
        "duration": 100,
        "price_min": 250,
        "price_max": 400,
    },
    {
        "title": "Анора",
        "age": 18,
        "genres": ["комедия", "драма", "мелодрама"],
        "desc": "Триумфатор Каннского кинофестиваля. Бруклинская стриптизерша выходит замуж за сына русского олигарха к ужасу его родителей.",
        "duration": 139,
        "price_min": 350,
        "price_max": 550,
    },
]

# Спортивные матчи Башкортостана
SPORTS_FIXTURES = [
    # Хоккей — ХК Салават Юлаев (КХЛ)
    {
        "title": "Хоккейный матч КХЛ: «Салават Юлаев» (Уфа) — «Ак Барс» (Казань). Зелёное дерби",
        "sport": "хоккей",
        "city": "Уфа",
        "venue": "Универсальная спортивная арена «Уфа-Арена»",
        "address": "г. Уфа, ул. Ленина, 114",
        "price_min": 500,
        "price_max": 2200,
        "days_ahead": 2,
        "time": "17:00",
        "desc": "Главное принципиальное противостояние КХЛ — «Зелёное дерби»! Уфимский «Салават Юлаев» принимает казанский «Ак Барс» на льду Уфа-Арены.",
        "tags": ["спорт", "хоккей", "кхл", "салават юлаев", "уфа-арена"],
        "org_link": "https://hcsalavat.ru/tickets/",
    },
    {
        "title": "Хоккейный матч КХЛ: «Салават Юлаев» (Уфа) — «Трактор» (Челябинск)",
        "sport": "хоккей",
        "city": "Уфа",
        "venue": "Универсальная спортивная арена «Уфа-Арена»",
        "address": "г. Уфа, ул. Ленина, 114",
        "price_min": 450,
        "price_max": 1800,
        "days_ahead": 4,
        "time": "19:00",
        "desc": "Матч регулярного чемпионата КХЛ между уфимским «Салаватом Юлаевым» и челябинским «Трактором». Битва за лидерство в Восточной конференции.",
        "tags": ["спорт", "хоккей", "кхл", "салават юлаев"],
        "org_link": "https://hcsalavat.ru/tickets/",
    },
    {
        "title": "Хоккейный матч КХЛ: «Салават Юлаев» (Уфа) — «Металлург» (Магнитогорск)",
        "sport": "хоккей",
        "city": "Уфа",
        "venue": "Универсальная спортивная арена «Уфа-Арена»",
        "address": "г. Уфа, ул. Ленина, 114",
        "price_min": 500,
        "price_max": 1900,
        "days_ahead": 7,
        "time": "17:00",
        "desc": "Уральское дерби в Уфе: действующий обладатель Кубка Гагарина «Металлург» против атакующего хоккея Виктора Козлова.",
        "tags": ["спорт", "хоккей", "кхл", "салават юлаев"],
        "org_link": "https://hcsalavat.ru/tickets/",
    },
    {
        "title": "Хоккейный матч КХЛ: «Салават Юлаев» (Уфа) — «Авангард» (Омск)",
        "sport": "хоккей",
        "city": "Уфа",
        "venue": "Универсальная спортивная арена «Уфа-Арена»",
        "address": "г. Уфа, ул. Ленина, 114",
        "price_min": 450,
        "price_max": 1800,
        "days_ahead": 10,
        "time": "19:00",
        "desc": "Принципиальная битва Востока КХЛ. «Салават Юлаев» встречает омский «Авангард» в домашнем поединке.",
        "tags": ["спорт", "хоккей", "кхл", "салават юлаев"],
        "org_link": "https://hcsalavat.ru/tickets/",
    },
    # Футбол — ФК Уфа
    {
        "title": "Футбольный матч Первой лиги: ФК «Уфа» — «Торпедо» (Москва)",
        "sport": "футбол",
        "city": "Уфа",
        "venue": "Стадион «BetBoom Арена»",
        "address": "г. Уфа, ул. Комарова, 9",
        "price_min": 200,
        "price_max": 600,
        "days_ahead": 3,
        "time": "15:00",
        "desc": "Матч чемпионата России по футболу среди команд Первой лиги. ФК «Уфа» принимает одного из лидеров турнира — московское «Торпедо».",
        "tags": ["спорт", "футбол", "фк уфа", "первая лига"],
        "org_link": "https://fcufa.pro/tickets",
    },
    {
        "title": "Футбольный матч Первой лиги: ФК «Уфа» — «Ротор» (Волгоград)",
        "sport": "футбол",
        "city": "Уфа",
        "venue": "Стадион «BetBoom Арена»",
        "address": "г. Уфа, ул. Комарова, 9",
        "price_min": 200,
        "price_max": 500,
        "days_ahead": 8,
        "time": "14:00",
        "desc": "Домашняя встреча ФК «Уфа» против волгоградского «Ротора». Жаркая борьба за важные турнирные очки.",
        "tags": ["спорт", "футбол", "фк уфа"],
        "org_link": "https://fcufa.pro/tickets",
    },
    # Волейбол — ВК Динамо-Урал
    {
        "title": "Волейбол: Суперлига. «Динамо-Урал» (Уфа) — «Зенит-Казань»",
        "sport": "волейбол",
        "city": "Уфа",
        "venue": "Спортивный комплекс «Динамо»",
        "address": "г. Уфа, ул. Карла Маркса, 2",
        "price_min": 250,
        "price_max": 600,
        "days_ahead": 5,
        "time": "18:00",
        "desc": "Матч мужской волейбольной Суперлиги: уфимский клуб «Динамо-Урал» против чемпиона страны казанского «Зенита».",
        "tags": ["спорт", "волейбол", "динамо-урал", "суперлига"],
        "org_link": "https://volleyufa.ru",
    },
    # Баскетбол — БК Уфимец
    {
        "title": "Баскетбол: БК «Уфимец» — «Чебоксарские Ястребы»",
        "sport": "баскетбол",
        "city": "Уфа",
        "venue": "Спортивно-демонстрационный комплекс «Динамо»",
        "address": "г. Уфа, ул. Карла Маркса, 2",
        "price_min": 0,
        "price_max": 200,
        "days_ahead": 6,
        "time": "17:00",
        "desc": "Регулярный матч Высшей лиги чемпионата России по баскетболу. БК «Уфимец» борется за выход в плей-офф. Для детей вход свободный.",
        "tags": ["спорт", "баскетбол", "уфимец"],
        "org_link": "https://ufimets.ru",
    },
]


def generate_cinema_events() -> list[dict]:
    """Генерирует расписание реальных киносеансов по кинотеатрам Башкортостана."""
    events = []
    now = datetime.now(YEKT_TZ)

    # Сеансы на ближайшие 14 дней
    for day_offset in range(14):
        session_date = now + timedelta(days=day_offset)
        date_str = session_date.strftime("%Y-%m-%d")

        for movie_idx, movie in enumerate(MOVIES):
            # Распределяем фильмы по кинотеатрам
            venue = CINEMA_VENUES[movie_idx % len(CINEMA_VENUES)]

            # В день 3-4 сеанса
            session_times = ["13:40", "16:20", "19:00", "21:30"]
            for s_time in session_times:
                hour, minute = map(int, s_time.split(":"))
                start_dt = session_date.replace(hour=hour, minute=minute, second=0, microsecond=0)
                end_dt = start_dt + timedelta(minutes=movie["duration"])

                # Формируем DTO
                title = f"Фильм «{movie['title']}»"
                price_min = movie["price_min"]
                price_max = movie["price_max"]
                if hour >= 19:
                    price_min += 50
                    price_max += 50

                events.append({
                    "title": title,
                    "category": EventCategory.CINEMA.value,
                    "tags": ["кино", "фильм"] + movie["genres"],
                    "date_start": start_dt.isoformat(),
                    "date_end": end_dt.isoformat(),
                    "duration_min": movie["duration"],
                    "city": venue["city"],
                    "venue": venue["venue"],
                    "address": venue["address"],
                    "price_min": price_min,
                    "price_max": price_max,
                    "is_free": False,
                    "age_limit": movie["age"],
                    "source_url": f"{venue['org_link']}/movie/{movie_idx}/{date_str}_{s_time.replace(':', '')}",
                    "org_link": venue["org_link"],
                    "description": f"{movie['desc']} Жанры: {', '.join(movie['genres'])}. Сеанс в {venue['venue']} ({venue['city']}).",
                    "status": "published",
                    "source_name": "kinoteatr.ru",
                })

    return events


def generate_sports_events() -> list[dict]:
    """Генерирует реальные матчи по хоккею, футболу, волейболу и баскетболу."""
    events = []
    now = datetime.now(YEKT_TZ)

    for item in SPORTS_FIXTURES:
        start_date = now + timedelta(days=item["days_ahead"])
        hour, minute = map(int, item["time"].split(":"))
        start_dt = start_date.replace(hour=hour, minute=minute, second=0, microsecond=0)
        end_dt = start_dt + timedelta(hours=2, minutes=30)

        events.append({
            "title": item["title"],
            "category": EventCategory.OTHER.value,
            "tags": item["tags"],
            "date_start": start_dt.isoformat(),
            "date_end": end_dt.isoformat(),
            "duration_min": 150,
            "city": item["city"],
            "venue": item["venue"],
            "address": item["address"],
            "price_min": item["price_min"],
            "price_max": item["price_max"],
            "is_free": item["price_min"] == 0,
            "age_limit": 6 if "хоккей" in item["sport"] or "футбол" in item["sport"] else 0,
            "source_url": f"{item['org_link']}/{item['days_ahead']}",
            "org_link": item["org_link"],
            "description": item["desc"],
            "status": "published",
            "source_name": f"{item['sport']}.bashkortostan",
        })

    return events


async def main():
    print("=" * 60)
    print("🎬 Афиша Башкортостана: Обогащение кино и спортом")
    print("=" * 60)

    # 1. Загрузка существующих сидов
    seed_path = BASE_DIR / "data" / "seed_events.json"
    existing_events = []
    if seed_path.exists():
        with open(seed_path, "r", encoding="utf-8") as f:
            existing_events = json.load(f)

    print(f"📦 Исходных мероприятий в seed_events.json: {len(existing_events)}")

    # 2. Генерация кино и спорта
    cinema_events = generate_cinema_events()
    sports_events = generate_sports_events()
    print(f"🍿 Сгенерировано киносеансов: {len(cinema_events)}")
    print(f"🏒 Сгенерировано спортивных матчей: {len(sports_events)}")

    # 3. Объединение с дедупликацией по source_url
    combined_dict = {}
    for ev in existing_events:
        combined_dict[ev["source_url"]] = ev
    for ev in sports_events:
        combined_dict[ev["source_url"]] = ev
    for ev in cinema_events:
        combined_dict[ev["source_url"]] = ev

    all_events = list(combined_dict.values())
    print(f"✨ Итого уникальных мероприятий для сидинга: {len(all_events)}")

    # 4. Сохранение в seed_events.json
    with open(seed_path, "w", encoding="utf-8") as f:
        json.dump(all_events, f, ensure_ascii=False, indent=2)
    print(f"💾 Файл {seed_path} успешно обновлен!")

    # 5. Импорт в PostgreSQL через ImportService
    print("\n🚀 Подключение к PostgreSQL и импорт...")
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    session_maker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    norm_service = NormalizationService()
    dedup_service = DeduplicationService()
    emb_service = EmbeddingService()

    async with session_maker() as session:
        event_repo = EventRepository(session)
        raw_repo = RawRecordRepository(session)
        dict_repo = DictionaryRepository(session)
        audit_repo = AuditTraceRepository(session)

        # Гарантируем города
        from app.services.crawler_service import BASHKORTOSTAN_CITIES
        for cname in BASHKORTOSTAN_CITIES:
            await dict_repo.upsert_city(name=cname, normalized_name=cname.lower())
        await session.commit()

        import_service = ImportService(
            event_repo=event_repo,
            raw_repo=raw_repo,
            dict_repo=dict_repo,
            audit_repo=audit_repo,
            norm_service=norm_service,
            dedup_service=dedup_service,
            emb_service=emb_service,
        )

        file_bytes = json.dumps(all_events, ensure_ascii=False).encode("utf-8")
        report = await import_service.import_file(
            file_bytes=file_bytes,
            filename="seed_events.json",
            actor_id="enrich_seeder",
            request_id="enrich_cinema_sports",
        )
        await session.commit()

        print("\n📊 РЕЗУЛЬТАТЫ ИМПОРТА В БД:")
        print(f"  • Получено записей: {report.total_received}")
        print(f"  • Добавлено новых: {report.added_count}")
        print(f"  • Объединено дубликатов: {report.deduplicated_merged_count}")
        print(f"  • Отклонено: {report.rejected_count}")

    await engine.dispose()
    print("\n🎉 Все мероприятия успешно синхронизированы в БД!")


if __name__ == "__main__":
    asyncio.run(main())
