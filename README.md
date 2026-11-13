# Афиша культуры Башкортостана (Bashkortostan Cultural Events Platform)

Интеллектуальная платформа-агрегатор и рекомендательный сервис культурных мероприятий Республики Башкортостан (Уфа, Стерлитамак, Салават, Нефтекамск, Октябрьский и др.).

Сервис построен на базе **автономного ИИ-агента (Level 3)** с диалоговым ReAct-циклом на LangGraph, гибридным поиском (Reciprocal Rank Fusion по полнотекстовым индексам PostgreSQL и векторным эмбеддингам pgvector), строгим соблюдением 152-ФЗ (маскирование ПДн) и стандарта RFC 7807 для обработки ошибок.

---

## 🌟 Ключевые возможности бэкенда

- **Автономный ИИ-ассистент (LangGraph ReAct):**
  - Поддержка многошаговых рассуждений (до 5 шагов ReAct на запрос) с сохранением контекста диалога в PostgreSQL (`AsyncPostgresSaver`).
  - 6 специализированных инструментов: гибридный поиск мероприятий, карточка события, поиск похожих событий, расписание площадки, подписка и обратная связь.
  - Двухфазное подтверждение (`Two-Phase Confirmation`) для всех мутирующих операций (подписка, фидбек) — защита от непреднамеренных действий.
  - Потоковая передача ответов через **Server-Sent Events (SSE)** с периодическим `heartbeat` (каждые 10 секунд).
  - **Zero-Hallucination Guardrails:** строгая проверка привязки фактов (`verify_output_grounding`), предотвращение инъекций (`check_user_input`) и спотлайтинг стороннего контента через `<untrusted_event_description>`.
  - **Автоматический Fallback:** детерминированный поиск по регулярным выражениям и морфологическим словарям (`FallbackSearchService`) при отказе LLM или исчерпании лимитов бюджета (Circuit Breaker).
- **Гибридный поиск мероприятий (RRF — Reciprocal Rank Fusion):**
  - Объединение ранжирования PostgreSQL FTS (`ts_rank` со словарем `russian`) и векторного поиска по косинусному расстоянию (`embedding <=> :vector` через HNSW-индекс).
  - Формула: $RRF = \frac{0.4}{60 + \text{rank}_{text}} + \frac{0.6}{60 + \text{rank}_{vec}}$.
  - Автоматическая плавная деградация до полнотекстового и триграммного поиска (`similarity` $\ge 0.15$) при недоступности эмбеддингов.
  - **Диагностика пустой выдачи:** при 0 результатах метод `diagnose_blocking_constraints` автоматически определяет блокирующий критерий (цена, дата, категория, возраст) и формирует рекомендацию по его ослаблению.
- **Нечеткий гео-поиск площадок и городов:**
  - Коррекция опечаток в названиях городов через триграммы `pg_trgm` с порогом схожести $\ge 0.45$.
- **Нормализация и дедупликация данных:**
  - Генерация детерминированного ключа дедупликации `dedup_key = sha256(...)`.
  - Безопасное слияние дубликатов из разных источников (`merge_event_fields`) с подсчетом уровня доверия и выставлением флага диспута при расхождении критических параметров (цена, дата).
  - Изоляция сырых данных (`raw_event_records`) и возможность 100% переигровки нормализации (`replay_all_normalizations`).
- **Безопасность и соответствие 152-ФЗ:**
  - Маскирование персональных данных (телефоны, email, IP-адреса, токены) в логах через процессор `PIIScrubberProcessor`.
  - Форматирование всех ошибок в `application/problem+json` по спецификации RFC 7807 (`ProblemDetails`).
  - Жесткий контроль расходов на LLM (Circuit Breaker: лимит 5 руб. на диалог, 25 руб. в сутки на пользователя, таймаут 6 сек).

---

## 🏗️ Архитектурный стек

| Компонент | Технология | Описание |
|---|---|---|
| **Язык & Рантайм** | Python 3.12+ | Строгая типизация, Type Hints, async/await |
| **API Фреймворк** | FastAPI | Асинхронные роуты, OpenAPI 3.1, Depends DI |
| **ORM & Миграции** | SQLAlchemy 2.0 + Alembic | Асинхронный движок `asyncpg`, `expire_on_commit=False`, `selectinload` |
| **База данных** | PostgreSQL 16 + pgvector | Расширения `vector`, `pg_trgm`, `btree_gist`, индексы GIN и HNSW |
| **Валидация данных** | Pydantic v2 | `ConfigDict(from_attributes=True)`, `AwareDatetime` (`Asia/Yekaterinburg`, UTC+5) |
| **ИИ-оркестрация** | LangGraph | StateGraph, `AsyncPostgresSaver` с пулом `psycopg_pool`, сериализация MessagePack |
| **Circuit Breaker** | LLMCircuitBreaker | Отслеживание сбоев (CLOSED / OPEN / HALF_OPEN), защита бюджета |
| **Шлюз / Reverse Proxy** | Nginx 1.27 Alpine | Маршрутизация, отключение буферизации для SSE (`proxy_buffering off`) |
| **Логирование** | Structlog | JSON-логи, трейс сквозного `request_id`, маскирование ПДн |

---

## 📂 Структура проекта

```
afisha/
├── AGENTS.md                  # Архитектурный контракт и свод правил для AI-разработки
├── CLAUDE.md                  # Руководство для ассистента Claude
├── docker-compose.yml         # Запуск PostgreSQL (pgvector) + Backend + Nginx
├── Makefile                   # Утилиты автоматизации сборки, тестов и миграций
├── nginx/
│   └── nginx.conf             # Конфигурация Nginx с proxy_buffering off для SSE
├── openapi.json               # Актуальная экспортированная спецификация OpenAPI 3.1
└── backend/
    ├── Dockerfile             # Сборка контейнера бэкенда на Python 3.12-slim
    ├── pyproject.toml         # Зависимости проекта и настройки линтеров/pytest
    ├── alembic.ini            # Конфигурация миграций Alembic
    ├── migrations/            # Папка миграций
    │   ├── env.py
    │   └── versions/
    │       └── 0001_initial_schema.py # Начальная схема с GIN и HNSW индексами
    ├── tests/                 # Модульные и интеграционные автотесты (30 тестов)
    └── app/
        ├── main.py            # Точка входа FastAPI, Lifespan, CORS, CSP
        ├── core/              # Системное ядро и инфраструктура
        │   ├── config.py      # Настройки приложения (Settings на pydantic-settings)
        │   ├── database.py    # Пул SQLAlchemy AsyncEngine и пул psycopg_pool
        │   ├── logging.py     # Structlog, PIIScrubberProcessor (152-ФЗ)
        │   ├── exceptions.py  # RFC 7807 исключения (AppError, rfc7807_exception_handler)
        │   ├── security.py    # SHA-256 хеширование, Sliding Window Rate Limiting
        │   └── circuit_breaker.py # LLMCircuitBreaker (CLOSED, OPEN, HALF_OPEN)
        ├── models/            # SQLAlchemy 2.0 модели данных
        │   ├── base.py        # Базовый декларативный класс с mapped_column
        │   ├── enums.py       # Перечисления (EventCategory, SourceType, EventStatus...)
        │   ├── dictionary.py  # Справочники городов (City) и площадок (Venue)
        │   ├── raw_record.py  # Сырые данные импорта (RawEventRecord)
        │   ├── event.py       # Мероприятия (Event: tsv, embedding, dedup_key) и EventSource
        │   ├── user_data.py   # Подписки (Subscription) и фидбек (FeedbackRequest)
        │   └── audit_trace.py # Трассировка агента (AgentTrace) и аудит (AuditLog)
        ├── schemas/           # Pydantic v2 DTO
        │   ├── common.py      # ProblemDetails (RFC 7807), пагинация
        │   ├── event.py       # EventCardDTO (cancelled_badge), фильтры, диагностика
        │   ├── dictionary.py  # Справочники CityDTO, VenueDTO
        │   ├── subscription.py# DTO подписок с BIGINT telegram_chat_id
        │   ├── feedback.py    # DTO обратной связи организаторов
        │   ├── import_mod.py  # DTO отчетов импорта CSV/JSON
        │   └── chat.py        # DTO сообщений чата, рекомендаций и подтверждений
        ├── repositories/      # Асинхронный слой доступа к данным
        │   ├── base.py        # Базовый репозиторий
        │   ├── dictionary_repo.py # Поиск городов по pg_trgm similarity >= 0.45
        │   ├── event_repo.py  # Гибридный поиск RRF, diagnose_blocking_constraints
        │   ├── raw_record_repo.py
        │   ├── subscription_repo.py
        │   ├── feedback_repo.py
        │   └── audit_trace_repo.py # Учет суточных расходов пользователей
        ├── services/          # Сервисный слой бизнес-логики
        │   ├── normalization_service.py # Парсинг цен, приведение к UTC+5 и шкале возрастов
        │   ├── deduplication_service.py # Генерация dedup_key, слияние дубликатов
        │   ├── embedding_service.py     # Обёртка над эмбеддингами с Circuit Breaker
        │   ├── import_service.py        # Идемпотентный импорт CSV/JSON и replay
        │   ├── catalog_service.py       # Каталог, пресеты дат, cancelled_badge
        │   └── fallback_search_service.py # Детерминированный поиск без LLM
        ├── agent/             # Модуль ИИ-агента на LangGraph
        │   ├── state.py       # TypedDict состояние AgentGraphState
        │   ├── prompts.py     # Системный промпт с Zero Hallucination контрактом
        │   ├── guardrails.py  # Инъекции, untrusted_event_description, факт-чекинг
        │   ├── tools.py       # 6 инструментов с двухфазным подтверждением
        │   ├── checkpointer.py# AsyncPostgresSaver + trim_conversation_history
        │   └── orchestrator.py# ReAct цикл, лимит 5 шагов, SSE стример
        └── api/               # Контроллеры FastAPI
            ├── deps.py        # DI зависимости
            └── v1/            # API v1
                ├── router.py  # Единый роутер v1
                ├── events.py  # Каталог, поиск, ETag/304, карточки (вкл. отмененные)
                ├── dictionaries.py # Города и площадки
                ├── chat.py    # Чат с агентом (синхронный + SSE стриминг)
                ├── subscriptions.py # Управление подписками
                ├── feedback.py# Обратная связь организаторов
                ├── admin.py   # Импорт CSV/JSON, модерация, смена статусов
                └── health.py  # Проверка готовности сервиса и БД
```

---

## 🚀 Быстрый старт

### 1. Запуск через Docker Compose (Рекомендуемый способ)

Для запуска всего стека (PostgreSQL 16 с pgvector, FastAPI бэкенд и Nginx с выключенной буферизацией) выполните:

```bash
# Клонирование репозитория (если еще не склонирован)
git clone https://github.com/legionhaos/afisha.git
cd afisha

# Запуск контейнеров
make up
# или: docker compose up -d --build
```

Сервисы будут доступны по адресам:
- **API через Nginx:** [http://localhost/api/v1/](http://localhost/api/v1/)
- **Интерактивная документация Swagger UI:** [http://localhost/docs](http://localhost/docs)
- **Альтернативная документация ReDoc:** [http://localhost/redoc](http://localhost/redoc)
- **Схема OpenAPI 3.1:** [http://localhost/openapi.json](http://localhost/openapi.json)
- **Healthcheck эндпоинт:** [http://localhost/health](http://localhost/health)

Применение миграций Alembic в базе данных:
```bash
make migrate
# или: docker compose exec backend alembic upgrade head
```

---

### 2. Локальный запуск для разработки

#### Требования:
- Python 3.12 или 3.13
- PostgreSQL 16 с установленными расширениями `vector`, `pg_trgm`, `btree_gist`

#### Шаги запуска:
```bash
cd backend

# Создание и активация виртуального окружения
python3 -m venv .venv
source .venv/bin/activate

# Установка зависимостей в режиме разработки
pip install -e .

# Применение миграций базы данных
alembic upgrade head

# Запуск dev-сервера uvicorn
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

---

## 🧪 Запуск автотестов

В проекте реализован полный набор из **30 асинхронных тестов**, покрывающих:
- Конфигурацию, PIIScrubberProcessor (152-ФЗ), circuit breaker и RFC 7807 исключения (`test_core.py`).
- Pydantic v2 DTO схемы, валидацию дат и RFC 7807 ProblemDetails (`test_schemas.py`).
- SQLAlchemy 2.0 модели, индексы, структуру TSVECTOR и dedup_key (`test_models.py`).
- Репозитории, нечеткий поиск триграммами и логику RRF поиска (`test_repositories.py`).
- Сервисы нормализации цен, дат UTC+5, дедупликации и регулярного парсера (`test_services.py`).
- Guardrails, фильтрацию инъекций, спотлайтинг и инструменты агента (`test_agent.py`).
- Эндпоинты FastAPI, ETag/304 кэширование, валидацию заголовков CSP и сценарии отмененных событий (`test_api_and_scenarios.py`).

Запуск всех тестов:
```bash
make test
# или:
cd backend && pytest -v
```

Результат выполнения:
```
============================== 30 passed in 2.92s ==============================
```

---

## 🛡️ Безопасность и архитектурные контракты

1. **RFC 7807 Problem Details:**
   Любая ошибка API (400, 401, 404, 422, 429, 500, 503) сериализуется с заголовком `Content-Type: application/problem+json` и содержит поля `type`, `title`, `status`, `detail`, `instance`, `code`, `request_id`, `errors`.
2. **152-ФЗ и защита персональных данных:**
   Все пользовательские логи проходят через `PIIScrubberProcessor`. Номера телефонов (`+7...`, `89...`), адреса электронной почты, IP-адреса и токены авторизации автоматически маскируются значением `[SCRUBBED]`.
3. **Telegram Chat ID:**
   Идентификаторы пользователей Telegram хранятся строго в формате `BIGINT` (64-бит), предотвращая переполнение 32-битного целочисленного диапазона.
4. **Контроль бюджета LLM и Circuit Breaker:**
   - Таймаут сетевого вызова модели: 6.0 секунд.
   - Максимум шагов ReAct-цикла на один запрос: 5.
   - Лимит расхода на диалог: 5.0 рублей.
   - Суточный лимит расхода на пользователя: 25.0 рублей.
   - При превышении или 3 последовательных сбоях внешней LLM состояние переходит в `OPEN`, и запрос безопасно обслуживается детерминированным `FallbackSearchService`.
5. **Двухфазное подтверждение мутаций (Two-Phase Mutation):**
   При попытке оформить подписку или отправить фидбек через чат агент сначала запрашивает явное подтверждение пользователя (`CONFIRMATION_REQUIRED`), возвращая `action_id`. Запись в базу выполняется только при передаче `confirmed_action_id`.

---

## 📄 Спецификация API

Полная спецификация OpenAPI 3.1 доступна в файле [`openapi.json`](file:///home/scoof/Downloads/afisha/openapi.json) и по адресу `http://localhost/docs`.
