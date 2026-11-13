# AGENTS.md — Свод правил и архитектурный контракт бэкенда «Афиша Башкортостана»

Этот документ является обязательным контрактом для всех ИИ-агентов (Antigravity, Claude Code, Cursor, Copilot) и разработчиков. Изменять структуру папок, сигнатуры базовых интерфейсов или архитектурные соглашения без явного указания запрещено.

---

## 1. Финальная структура проекта

Используется исключительно финальная структура папок из ТЗ (часть 2):
```
backend/
├── Dockerfile
├── pyproject.toml
├── alembic.ini
├── migrations/                     # Папка миграций Alembic (не alembic/!)
│   ├── env.py
│   └── versions/
│       └── 0001_initial_schema.py
└── app/
    ├── main.py
    ├── core/                       # Системное ядро и инфраструктура
    │   ├── config.py
    │   ├── database.py
    │   ├── logging.py
    │   ├── exceptions.py
    │   ├── security.py
    │   └── circuit_breaker.py
    ├── models/                     # Модели SQLAlchemy 2.0 (папка app/models, не app/db/models!)
    │   ├── base.py
    │   ├── enums.py
    │   ├── event.py
    │   ├── dictionary.py
    │   ├── raw_record.py
    │   ├── user_data.py
    │   └── audit_trace.py
    ├── schemas/                    # Pydantic v2 DTO
    │   ├── common.py
    │   ├── event.py
    │   ├── dictionary.py
    │   ├── import_mod.py
    │   ├── subscription.py
    │   ├── feedback.py
    │   └── chat.py
    ├── repositories/               # Доступ к данным (только асинхронные методы)
    │   ├── base.py
    │   ├── event_repo.py
    │   ├── dictionary_repo.py
    │   ├── raw_record_repo.py
    │   ├── subscription_repo.py
    │   ├── feedback_repo.py
    │   └── audit_trace_repo.py
    ├── services/                   # Бизнес-логика, нормализация, дедупликация
    │   ├── embedding_service.py
    │   ├── normalization_service.py
    │   ├── deduplication_service.py
    │   ├── import_service.py
    │   ├── catalog_service.py
    │   └── fallback_search_service.py
    ├── agent/                      # Модуль ИИ-агента на LangGraph (backend/app/agent)
    │   ├── state.py
    │   ├── prompts.py
    │   ├── guardrails.py
    │   ├── tools.py
    │   ├── checkpointer.py
    │   └── orchestrator.py
    └── api/                        # Контроллеры FastAPI
        ├── deps.py
        └── v1/
            ├── router.py
            ├── events.py
            ├── dictionaries.py
            ├── chat.py
            ├── subscriptions.py
            ├── feedback.py
            ├── admin.py
            └── health.py
```

---

## 2. Жесткие правила стека и типизации

1. **Python 3.12+**: Строгая типизация (`from typing import ...`, Type Hints во всех аргументах и возвращаемых значениях). Никаких нетипизированных функций `def foo(x):`.
2. **FastAPI**: Асинхронные эндпоинты, внедрение зависимостей через `Depends()`, автоматическая документация OpenAPI 3.1 (`generate_unique_id_function`).
3. **SQLAlchemy 2.0**:
   - Только `AsyncSession`.
   - Настройка сессии: `expire_on_commit=False` для предотвращения `DetachedInstanceError`.
   - Использование `Mapped[...]` и `mapped_column(...)`.
   - Eager loading связанных сущностей через `selectinload`.
4. **Pydantic v2**:
   - `model_config = ConfigDict(from_attributes=True, populate_by_name=True)`.
   - Валидаторы через `@field_validator` и `@model_validator(mode="after")`.
   - Все даты строго типизированы через `pydantic.AwareDatetime` в часовом поясе `Asia/Yekaterinburg` (UTC+5).

---

## 3. База данных и LangGraph Checkpointer

1. **PostgreSQL 16**: Расширения `vector` (pgvector), `pg_trgm`, `btree_gist`.
2. **Идентификаторы пользователей Telegram**:
   - Хранятся строго как `BIGINT` (в моделях `BigInteger`, в DTO `int`), так как Telegram user_id превышают 32 бита.
3. **Пул соединений для LangGraph Checkpointer**:
   - Для `AsyncPostgresSaver` создается отдельный пул `AsyncConnectionPool` из `psycopg_pool`.
   - Обязательные параметры пула: `autocommit=True` и `row_factory=dict_row` (иначе `AsyncPostgresSaver` падает с `TypeError` при обращении к колонкам по именам).
   - Флаг безопасности сериализации: `LANGGRAPH_STRICT_MSGPACK=true`.
4. **Дедупликация и Идемпотентность**:
   - `dedup_key = sha256(f"{city.lower()}::{venue.lower()}::{date_start.strftime('%Y-%m-%d %H:%M')}::{normalized_title[:60]}")`.
   - `source_hash = sha256(f"{source_url}|{title}|{date_start}")` — гарантирует 100% идемпотентность повторного импорта.
   - Сырые данные изолированы в таблице `raw_event_records` для переигровки нормализации (`replay_all_normalizations`).

---

## 4. Ошибки по RFC 7807 и Защита ПДн (152-ФЗ)

1. **Формат ошибок RFC 7807**:
   - Все ошибки API возвращаются с `Content-Type: application/problem+json`.
   - Структура `ProblemDetails`: `type`, `title`, `status`, `detail`, `instance`, `code`, `request_id`, `errors`.
   - Базовый класс `AppError(Exception)` и дочерние (`EventNotFoundError` (404), `ValidationFailedError` (422), `RateLimitExceededError` (429), `AgentBudgetExceededError` (503), `UnauthorizedAdminError` (401)).
2. **Логирование и ПДн**:
   - Использование `structlog` в формате JSON.
   - Процессор `PIIScrubberProcessor` вырезает/маскирует номера телефонов (+7..., 89...), email, IP-адреса, токены, пароли, заменяя на `[SCRUBBED]`.
   - Сквозной `request_id` прокидывается через `contextvars` во все логи и трассы.

---

## 5. Поиск и Интеллектуальный Агент

1. **Гибридный поиск (RRF)**:
   - Объединение полнотекстового поиска (`ts_rank` по `tsv` с русским словарем) и векторного (`embedding <=> :vector` по HNSW) по формуле:
     `RRF_Score = 0.4 / (60 + rank_text) + 0.6 / (60 + rank_vec)`.
   - Автоматическая деградация: при `query_embedding is None` поиск переключается на комбинацию FTS и триграммного поиска (`similarity(normalized_title, :q)`).
   - Фильтр `status == 'published'` обязателен для публичного каталога.
2. **Диагностика пустой выдачи**:
   - При 0 результатах вызывается `diagnose_blocking_constraints`, вычисляющий через условные `COUNT(*) FILTER (WHERE ...)` блокирующее ограничение (цена, дата, возраст, категория) с рекомендацией по ослаблению.
3. **Безопасность и Guardrails агента**:
   - Лимит шагов: не более 5 переходов ReAct.
   - Память: сохранение контекста не менее 5 реплик диалога.
   - Zero Hallucination: 100% фактов должны браться только из результатов инструментов. В ответе проверяется привязка (`verify_output_grounding`).
   - Защита от инъекций: входной текст проверяется `check_user_input`, описания из БД оборачиваются в `<untrusted_event_description>`.
   - Изменение данных (подписки, обратная связь) строго через двухфазное подтверждение: при отсутствии `confirmed_action_id` возвращается `CONFIRMATION_REQUIRED`.
4. **Отказоустойчивость и Fallback**:
   - `LLMCircuitBreaker`: при 3 ошибках или таймауте > 6.0 сек переводит состояние в `OPEN`.
   - При срабатывании предохранителя или превышении бюджета (5 руб. на диалог, 25 руб. в сутки на пользователя) запрос передается в `FallbackSearchService` (детерминированный поиск по регулярным выражениям и словарям без LLM).

---

## 6. Процедура верификации каждого шага

После генерации или модификации любого модуля:
1. Запустить проверку синтаксиса и импортов Python:
   ```bash
   python -c "import app.core.config, app.core.database; print('OK')"
   ```
2. Запустить автотесты pytest:
   ```bash
   pytest tests/
   ```
3. Любые ошибки импортов, опечатки в типах или сбои тестов должны быть устранены **до** перехода к следующему этапу.
