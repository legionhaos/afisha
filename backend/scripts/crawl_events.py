#!/usr/bin/env python3
"""
Скрипт автономного сбора культурных мероприятий Республики Башкортостан (ТЗ раздел 6.5).
Источники: ufa.kassir.ru, rusdram.ru, ufa.kassy.ru

Использование:
    python scripts/crawl_events.py --save-seed
    python scripts/crawl_events.py --import-db --verify-urls
    python scripts/crawl_events.py --dry-run
"""
import argparse
import asyncio
import json
from pathlib import Path
import sys

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.repositories.audit_trace_repo import AuditTraceRepository
from app.repositories.dictionary_repo import DictionaryRepository
from app.repositories.event_repo import EventRepository
from app.repositories.raw_record_repo import RawRecordRepository
from app.services.crawler_service import CrawlerService
from app.services.deduplication_service import DeduplicationService
from app.services.embedding_service import EmbeddingService
from app.services.import_service import ImportService
from app.services.normalization_service import NormalizationService


async def main():
    parser = argparse.ArgumentParser(description="Краулер мероприятий Республики Башкортостан")
    parser.add_argument("--save-seed", action="store_true", help="Сохранить результат в data/seed_events.json")
    parser.add_argument("--import-db", action="store_true", help="Загрузить собранные события в базу данных")
    parser.add_argument("--verify-urls", action="store_true", help="Проверить отклик ссылок на источник (HEAD check)")
    parser.add_argument("--dry-run", action="store_true", help="Только собрать и показать статистику без сохранения")
    parser.add_argument("--limit", type=int, default=None, help="Ограничение количества событий на источник")
    args = parser.parse_args()

    # Дефолтное поведение, если флаги не переданы
    if not (args.save_seed or args.import_db or args.dry_run):
        args.save_seed = True

    print("=" * 60)
    print("🎭 Афиша Башкортостана: Запуск сбора реальных мероприятий")
    print(f"Параметры: save_seed={args.save_seed}, import_db={args.import_db}, verify_urls={args.verify_urls}, dry_run={args.dry_run}")
    print("=" * 60)

    # Инициализация сервиса краулера
    # Создаем dummy import_service для сбора, если БД не нужна
    norm_service = NormalizationService()
    dedup_service = DeduplicationService()
    emb_service = EmbeddingService()

    crawler_service = CrawlerService(
        import_service=None,  # type: ignore
        norm_service=norm_service,
    )

    print("\n🔍 Запуск краулеров (Kassir, Rusdram, Kassy)...")
    events = await crawler_service.crawl_all(
        verify_urls=args.verify_urls,
        limit_per_source=args.limit,
    )

    print(f"\n✅ Сбор завершен! Найдено уникальных мероприятий: {len(events)}")

    # Подсчет статистики
    by_city: dict[str, int] = {}
    by_category: dict[str, int] = {}
    by_status: dict[str, int] = {}
    by_source: dict[str, int] = {}

    for ev in events:
        c = ev.get("city", "Не указан")
        by_city[c] = by_city.get(c, 0) + 1

        cat = ev.get("category", "other")
        by_category[cat] = by_category.get(cat, 0) + 1

        st = ev.get("status", "published")
        by_status[st] = by_status.get(st, 0) + 1

        src = ev.get("source_name", "unknown")
        by_source[src] = by_source.get(src, 0) + 1

    print("\n📊 Статистика по источникам:")
    for src, cnt in sorted(by_source.items(), key=lambda x: -x[1]):
        print(f"  • {src}: {cnt}")

    print("\n🏙️ Статистика по городам Башкортостана:")
    for c, cnt in sorted(by_city.items(), key=lambda x: -x[1]):
        print(f"  • {c}: {cnt}")

    print("\n🏷️ Статистика по категориям:")
    for cat, cnt in sorted(by_category.items(), key=lambda x: -x[1]):
        print(f"  • {cat}: {cnt}")

    print("\n🚦 Статистика по статусам:")
    for st, cnt in sorted(by_status.items(), key=lambda x: -x[1]):
        print(f"  • {st}: {cnt}")

    seed_path = BASE_DIR / "data" / "seed_events.json"

    # Сохранение в seed_events.json
    if args.save_seed and not args.dry_run:
        seed_path.parent.mkdir(parents=True, exist_ok=True)
        with open(seed_path, "x", encoding="utf-8") as f:
            json.dump(events, f, ensure_ascii=False, indent=2)
        print(f"\n💾 Данные сохранены в {seed_path} ({len(events)} событий)")

    # Импорт в базу данных PostgreSQL
    if args.import_db and not args.dry_run:
        print("\n🚀 Подключение к PostgreSQL и импорт...")
        engine = create_async_engine(settings.DATABASE_URL, echo=False)
        session_maker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

        async with session_maker() as session:
            event_repo = EventRepository(session)
            raw_repo = RawRecordRepository(session)
            dict_repo = DictionaryRepository(session)
            audit_repo = AuditTraceRepository(session)

            # Наполнение справочника городов
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

            report = await import_service.import_file(
                file_bytes=json.dumps(events, ensure_ascii=False).encode("utf-8"),
                filename="crawler_feed.json",
                actor_id="cli_crawler",
                request_id="cli_crawl_run",
            )

            await session.commit()

            print("\n🏁 Результаты импорта в базу данных:")
            print(f"  • Всего обработано: {report.total_received}")
            print(f"  • Добавлено новых: {report.added_count}")
            print(f"  • Объединено дубликатов: {report.deduplicated_merged_count}")
            print(f"  • Обновлено: {report.updated_count}")
            print(f"  • Отправлено на модерацию: {report.flagged_for_moderation_count}")
            print(f"  • Отклонено с ошибкой: {report.rejected_count}")

        await engine.dispose()

    print("\n🎉 Готово!")


if __name__ == "__main__":
    asyncio.run(main())
