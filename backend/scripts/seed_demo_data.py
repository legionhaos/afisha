#!/usr/bin/env python3
"""
Скрипт начального наполнения (сидинга) базы данных реальными мероприятиями Башкортостана.
Запуск: python scripts/seed_demo_data.py
Или: make seed
"""
import asyncio
import os
import sys
from pathlib import Path

# Добавляем пути в sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app.core.config import settings
from app.core.database import db_manager
from app.repositories.audit_trace_repo import AuditTraceRepository
from app.repositories.dictionary_repo import DictionaryRepository
from app.repositories.event_repo import EventRepository
from app.repositories.raw_record_repo import RawRecordRepository
from app.services.deduplication_service import DeduplicationService
from app.services.embedding_service import EmbeddingService
from app.services.import_service import ImportService
from app.services.normalization_service import NormalizationService


async def seed():
    seed_file = BASE_DIR / "data" / "seed_events.json"
    if not seed_file.exists():
        print(f"❌ Файл сидов не найден: {seed_file}")
        sys.exit(1)

    print("🚀 Инициализация подключения к PostgreSQL...")
    try:
        await db_manager.init_pools()
    except Exception as e:
        print(f"❌ Не удалось подключиться к БД: {e}")
        print("💡 Убедитесь, что база данных запущена (например, через 'make up' или docker compose)")
        sys.exit(1)

    print(f"📦 Чтение данных из {seed_file.name}...")
    with open(seed_file, "rb") as f:
        file_bytes = f.read()

    async with db_manager.get_session() as session:
        # Репозитории
        event_repo = EventRepository(session)
        raw_repo = RawRecordRepository(session)
        dict_repo = DictionaryRepository(session)
        audit_repo = AuditTraceRepository(session)

        # Сначала наполняем города Башкортостана
        print("🏙️ Заполнение справочника городов Республики Башкортостан...")
        bash_cities = ["Уфа", "Стерлитамак", "Салават", "Нефтекамск", "Октябрьский", "Сибай", "Белорецк", "Ишимбай"]
        for cname in bash_cities:
            await dict_repo.get_or_create_city(cname)

        await session.commit()

        # Сервисы
        norm_service = NormalizationService()
        dedup_service = DeduplicationService()
        emb_service = EmbeddingService()

        import_service = ImportService(
            event_repo=event_repo,
            raw_repo=raw_repo,
            dict_repo=dict_repo,
            audit_repo=audit_repo,
            norm_service=norm_service,
            dedup_service=dedup_service,
            emb_service=emb_service,
        )

        print("⚡ Выполнение импорта и дедупликации мероприятий...")
        report = await import_service.import_file(
            file_bytes=file_bytes,
            filename=seed_file.name,
            actor_id="system_seeder",
            request_id="seed_initial_setup",
        )

        await session.commit()

        print("\n" + "=" * 60)
        print("📊 ОТЧЕТ О НАЧАЛЬНОМ СИДИНГЕ МЕРОПРИЯТИЙ В БД:")
        print("=" * 60)
        print(f" Всего прочитано записей:  {report.total_received}")
        print(f" ✅ Успешно добавлено:     {report.added_count}")
        print(f" 🔄 Сведено дубликатов:    {report.deduplicated_count}")
        print(f" ⚠️ Отклонено (ошибки):   {report.rejected_count}")

        if report.errors:
            print("\nСписок отклоненных строк:")
            for err in report.errors:
                print(f"  - Строка {err.row_index} ({err.raw_title}): {err.reason}")

        print("=" * 60)
        print("🎉 База данных успешно наполнена реальными событиями!")

    await db_manager.close_pools()


if __name__ == "__main__":
    asyncio.run(seed())
