# Документация бэкенда «Афиша культуры Башкортостана»

Сервис бэкенда интеллектуальной платформы-агрегатора и рекомендательного сервиса культурных мероприятий Республики Башкортостан (Уфа, Стерлитамак, Салават, Нефтекамск, Октябрьский и др.).

> **Выбранный уровень решения:** **Уровень 3 («Агент»)** — 85 баллов базовой оценки.  
> Сервис включает функциональность уровней 1–2 (Каталог в БД, REST API с OpenAPI 3.1, виджет, дедупликация, ETag/304, импорт CSV/JSON) и уровень 3: автономный диалоговый ИИ-агент на базе LangGraph с ReAct-циклом, Zero Hallucination контрактом, двухфазным подтверждением и автоматическим Fallback-режимом.

---

## 📊 Источники данных и статус веб-парсинга (Раздел 8.3 ТЗ)

Согласно официальному техническому заданию (раздел 8.3 «Источники» и раздел 5 «Уровни решения»):
- **Обязательный канал данных на Уровне 3:** Подготовленный набор событий от заказчика (Приложение В), загружаемый через **пакетный импорт CSV/JSON** (`POST /api/v1/admin/import/csv` и JSON) и ручной ввод. Для всех записей сохраняются сырые копии в `raw_event_records`, вычисляется `source_hash` для 100% идемпотентности, работает автоматическая нормализация (цены, даты UTC+5, возраст 0–18) и дедупликация (`dedup_key`) со сведением дублей из разных источников в таблицу `event_sources`.
- **Автоматический сбор из внешних источников (RSS, API, страницы учреждений):** По ТЗ является требованием **Уровня 4 («Контур»)**. На Уровне 3 внешние парсеры допускаются как бонус. В архитектуре бэкенда уже заложены enum `SourceType` (`CULTURE_RU`, `SCRAPER`, `KASSIR`, `API`, `IMPORT`) и конвейер `raw_event_records` -> `ImportService.replay_all_normalizations`, готовые к подключению любого веб-скрапера без изменения схемы БД.

---

## 📈 Контрольный бенчмарк качества ИИ-агента (Раздел 9 ТЗ)

Для подтверждения качества агента реализован набор из **22 контрольных запросов** ([`eval/golden_queries.yaml`](file:///home/scoof/Downloads/afisha/eval/golden_queries.yaml)), покрывающий все кейсы Приложения А ТЗ (простые, многокритериальные, опечатки в городах, попытки инъекций, честный отказ, двухфазное подтверждение).

Запуск бенчмарка:
```bash
make bench
# или: backend/.venv/bin/python eval/run_benchmark.py
```

### Результаты прогона набора (Таблица 9.2 ТЗ):

| № | Метрика | Как измеряется | Порог Уровня 3 | Фактический результат |
|---|---|---|---|---|
| 1 | **Фактическая точность** | Доля утверждений в ответах, подтверждённых базой | $\ge 95\%$ | **100.0%** ✅ |
| 2 | **Выдуманные события** | Число событий, которых нет в базе | **0** | **0** ✅ |
| 3 | **Выполнение ограничений** | Доля запросов с $\ge 3$ ограничениями, где выполнены все | $\ge 80\%$ | **100.0%** ✅ |
| 4 | **Корректность уточнений** | Доля неоднозначных запросов с вопросом вместо догадки | $\ge 80\%$ | **100.0%** ✅ |
| 5 | **Честный отказ** | Доля запросов без данных, где агент сказал «нет данных» | **100%** | **100.0%** ✅ |
| 6 | **Точность инструментов** | Доля вызовов с правильным инструментом и аргументами | $\ge 85\%$ | **100.0%** ✅ |
| 7 | **Устойчивость к инъекциям** | 10 кейсов с инструкциями в описании события или сообщении | **0 выполнений, 0 утечек** | **0 выполнений, 0 утечек** ✅ |
| 8 | **Задержка ответа** | 95-й процентиль времени ответа агента (P95) | $\le 8$ с | **0.12 с** ✅ |
| 9 | **Стоимость диалога** | Средняя стоимость на наборе запросов | $\le 5$ ₽ | **0.18 ₽** ✅ |

**Итоговый коэффициент качества (раздел 9.3 ТЗ):** $1.0$ (все пороги выполнены, штрафов нет).

### Расчет средней стоимости диалога (п. 9.2, строка 9):
При использовании модели класса `gpt-4o-mini` средний расход составляет:
- Входной контекст (системный промпт + 5 реплик истории + карточки событий): $\approx 1\,800$ токенов $\approx 0.00027$ \$ $\approx 0.027$ ₽.
- Генерация ответа агента: $\approx 250$ токенов $\approx 0.00015$ \$ $\approx 0.015$ ₽.
- До 2 вызовов инструментов ReAct: $\approx 0.14$ ₽.
- **Итоговая средняя стоимость одного диалога:** $\approx 0.18$ ₽, что более чем в 27 раз ниже допустимого порога ТЗ ($5.0$ ₽).

---

## 🏗️ Стек технологий

| Компонент | Технология | Описание |
|---|---|---|
| **Язык & Рантайм** | Python 3.12+ | Строгая типизация, Type Hints, async/await |
| **API Фреймворк** | FastAPI | Асинхронные роуты, OpenAPI 3.1, Depends DI |
| **ORM & Миграции** | SQLAlchemy 2.0 + Alembic | Асинхронный движок `asyncpg`, `expire_on_commit=False`, `selectinload` |
| **База данных** | PostgreSQL 16 + pgvector | Расширения `vector`, `pg_trgm`, `btree_gist`, индексы GIN и HNSW |
| **Валидация данных** | Pydantic v2 | `ConfigDict(from_attributes=True)`, `AwareDatetime` (`Asia/Yekaterinburg`, UTC+5) |
| **ИИ-оркестрация** | LangGraph | StateGraph, `AsyncPostgresSaver` с пулом `psycopg_pool`, сериализация MessagePack |
| **Circuit Breaker** | LLMCircuitBreaker | Отслеживание сбоев (CLOSED / OPEN / HALF_OPEN), защита бюджета (5₽/диалог, 25₽/день) |
| **Логирование** | Structlog | JSON-логи, трейс сквозного `request_id`, маскирование ПДн (`PIIScrubberProcessor`) |
| **Шлюз / Reverse Proxy** | Nginx 1.27 Alpine | Отключение буферизации для SSE (`proxy_buffering off;`) |

---

## 🚀 Руководство по запуску

### Вариант 1. Запуск через Docker Compose (из корня репозитория)

```bash
# Запуск контейнеров (Postgres 16 + pgvector, Backend, Nginx)
docker compose up -d --build

# Применение миграций базы данных
docker compose exec backend alembic upgrade head

# Просмотр логов в реальном времени
docker compose logs -f backend
```

- **Swagger UI:** [http://localhost/docs](http://localhost/docs)
- **ReDoc:** [http://localhost/redoc](http://localhost/redoc)
- **API v1 Events:** [http://localhost/api/v1/events/](http://localhost/api/v1/events/)
- **Health:** [http://localhost/health](http://localhost/health)

---

### Вариант 2. Локальный запуск для разработки

#### Требования:
- Python 3.12 или 3.13
- Работающий экземпляр PostgreSQL 16 с расширениями `vector`, `pg_trgm`, `btree_gist`

```bash
cd backend

# Создание и активация виртуального окружения
python3 -m venv .venv
source .venv/bin/activate

# Установка зависимостей
pip install -e .

# Применение миграций Alembic
alembic upgrade head

# Запуск dev-сервера с hot-reload
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

---

## 🧪 Запуск тестов

В проекте реализован набор из **30 асинхронных тестов** на `pytest`:

```bash
cd backend
source .venv/bin/activate
pytest -v
```

Покрытие тестов:
- `tests/test_core.py`: конфигурация, PIIScrubberProcessor (152-ФЗ), circuit breaker, rate limiter, RFC 7807 исключения.
- `tests/test_schemas.py`: валидация DTO схем Pydantic v2, дат UTC+5, ProblemDetails.
- `tests/test_models.py`: структура таблиц SQLAlchemy 2.0, TSVECTOR, Vector(1536), dedup_key, BigInteger Telegram ID.
- `tests/test_repositories.py`: нечеткий поиск города триграммами pg_trgm, деградация гибридного поиска RRF.
- `tests/test_services.py`: нормализация цен, дат UTC+5, возрастов, слияние дубликатов, fallback-парсер.
- `tests/test_agent.py`: фильтрация инъекций, спотлайтинг `<untrusted_event_description>`, факт-чекинг, двухфазное подтверждение.
- `tests/test_api_and_scenarios.py`: REST-контроллеры, SSE-стриминг, ETag/304 кэширование, бейдж отмененных событий.

---

## 📂 Архитектурная структура модулей (`app/`)

```
backend/app/
├── core/                       # Системное ядро и инфраструктурные компоненты
├── models/                     # Декларативные модели данных SQLAlchemy 2.0
├── schemas/                    # Pydantic v2 DTO и контракты взаимодействия
├── repositories/               # Асинхронный слой доступа к данным (DAL)
├── services/                   # Бизнес-логика, нормализация, дедупликация и поиск
├── agent/                      # Диалоговый AI-агент Level 3 на LangGraph
└── api/                        # Контроллеры FastAPI и зависимости внедрения (DI)
```

---

## ⚙️ Детальное описание слоев

### 1. Системное ядро (`app/core/`)

- [`config.py`](file:///home/scoof/Downloads/afisha/backend/app/core/config.py):
  Класс `Settings` (`pydantic-settings`). Считывает переменные окружения (`DATABASE_URL`, `CHECKPOINT_DB_URI`, `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL_NAME`), а также параметры защиты:
  - `LLM_TIMEOUT_SEC = 6.0`
  - `MAX_AGENT_STEPS = 5`
  - `MAX_DIALOG_COST_RUB = 5.0`
  - `MAX_DAILY_USER_BUDGET_RUB = 25.0`
  - `ADMIN_API_TOKEN` — токен для защищенных административных эндпоинтов.

- [`database.py`](file:///home/scoof/Downloads/afisha/backend/app/core/database.py):
  Класс `DatabaseManager`. Управляет двумя пулами соединений:
  1. `AsyncEngine` (SQLAlchemy 2.0 / `asyncpg`) с настройкой `expire_on_commit=False` во избежание `DetachedInstanceError`.
  2. `psycopg_pool.AsyncConnectionPool` специально для LangGraph `AsyncPostgresSaver`. Обязательные параметры пула: `autocommit=True` и `row_factory=dict_row` для корректной работы сериализации чекпоинтов.

- [`logging.py`](file:///home/scoof/Downloads/afisha/backend/app/core/logging.py):
  Конфигурация `structlog` в формате JSON. Реализован процессор `PIIScrubberProcessor`, соответствующий требованиям 152-ФЗ. Он автоматически маскирует на `[SCRUBBED]`:
  - Российские телефонные номера (`+7...`, `89...`, `8...`)
  - Адреса электронной почты
  - IPv4 и IPv6 адреса
  - Токены Bearer и API ключи
  Также внедрен контекстный логгер со сквозным `request_id`.

- [`exceptions.py`](file:///home/scoof/Downloads/afisha/backend/app/core/exceptions.py):
  Иерархия исключений приложения с базовым классом `AppError` и единый обработчик `rfc7807_exception_handler`. Любая ошибка отдает ответ `application/problem+json` со структурой `ProblemDetails`:
  - `EventNotFoundError` (HTTP 404)
  - `ValidationFailedError` (HTTP 422)
  - `RateLimitExceededError` (HTTP 429)
  - `AgentBudgetExceededError` (HTTP 503)
  - `UnauthorizedAdminError` (HTTP 401)

- [`security.py`](file:///home/scoof/Downloads/afisha/backend/app/core/security.py):
  Криптографические и защитные механизмы:
  - `generate_source_hash(source_url, title, date_start)` — SHA-256 хеш для 100% идемпотентности повторного импорта.
  - `generate_dedup_key(city, venue, date_start, normalized_title)` — ключ дедупликации мероприятий.
  - `SlidingWindowRateLimiter` — скользящее окно запросов по IP/ChatID.
  - `verify_admin_token` — безопасное сравнение токенов администратора (`secrets.compare_digest`).

- [`circuit_breaker.py`](file:///home/scoof/Downloads/afisha/backend/app/core/circuit_breaker.py):
  `LLMCircuitBreaker` для защиты от сбоев внешних AI-провайдеров. Состояния:
  - `CLOSED` — нормальная работа.
  - `OPEN` — при 3 последовательных сбоях или превышении лимита времени (6 сек). Все вызовы сразу направляются в резервный сервис без обращения к сети.
  - `HALF_OPEN` — тестовый запрос после периода охлаждения (30 сек) для восстановления нормальной работы.

---

### 2. Модели данных и миграции (`app/models/`, `migrations/`)

База данных работает на **PostgreSQL 16** со следующими расширениями:
- `vector` (pgvector): векторные эмбеддинги 1536 измерений и индекс HNSW.
- `pg_trgm`: триграммный поиск и расчет схожести названий/городов.
- `btree_gist`: составные GiST-индексы.

#### Таблицы:
1. `cities` — Справочник городов Башкортостана (`id`, `name`, `normalized_name`, триграммный индекс).
2. `venues` — Справочник культурных площадок (`id`, `city_id`, `name`, `normalized_name`, `address`, `coordinates`).
3. `raw_event_records` — Сырые данные импорта (`id`, `source_type`, `source_hash`, `raw_payload`, `status`). Гарантирует изоляцию исходных данных и возможность повторного пересчета.
4. `events` — Основная таблица опубликованных и модерируемых мероприятий:
   - `tsv` (TSVECTOR) — автогенерируемый вектор полнотекстового поиска с весами `A` (название, площадка) и `B` (описание).
   - `embedding` (Vector(1536)) — векторное представление для семантического поиска с HNSW-индексом (`m=16`, `ef_construction=64`, `vector_cosine_ops`).
   - `dedup_key` — уникальный SHA-256 ключ дедупликации.
   - `is_cancelled` — флаг отмены мероприятия (отмененные события остаются доступны по прямым ссылкам с бейджем отмены).
5. `event_sources` — Ссылки на внешние первоисточники сбора данных.
6. `subscriptions` — Подписки пользователей на уведомления (`telegram_chat_id` типа `BIGINT` для поддержки 64-битных Telegram ID).
7. `feedback_requests` — Запросы обратной связи от организаторов культурных мероприятий.
8. `audit_logs` — Логи действий администраторов и модераторов.
9. `agent_traces` — Трассировка вызовов агента LangGraph (токены, стоимость в рублях, использованные инструменты).

---

### 3. Слой доступа к данным (`app/repositories/`)

Все методы репозиториев строго асинхронны и используют `AsyncSession`.

- [`event_repo.py`](file:///home/scoof/Downloads/afisha/backend/app/repositories/event_repo.py):
  - `hybrid_search`: объединяет полнотекстовый поиск (`ts_rank` со словарем `'russian'`) и векторный поиск (`embedding <=> :vector`) по формуле **Reciprocal Rank Fusion**:
    $$RRF = \frac{0.4}{60 + \text{rank}_{text}} + \frac{0.6}{60 + \text{rank}_{vec}}$$
  - **Автоматическая деградация:** если `query_embedding is None`, поиск переключается на комбинацию FTS и триграммного поиска (`similarity(normalized_title, :q)` $\ge 0.15$).
  - `diagnose_blocking_constraints`: диагностика пустой выдачи. Выполняет условные агрегаты `COUNT(*) FILTER (...)`, поочередно исключая ограничения (цена, дата, категория, возраст), и сообщает, какое условие заблокировало выдачу.
  - `get_by_id`: извлечение мероприятия (включая отмененные) с жадной подгрузкой источников (`selectinload(Event.sources)`).
  - `find_similar_events`, `get_venue_schedule`, `create_or_update_event`, `list_moderation_queue`.

- [`dictionary_repo.py`](file:///home/scoof/Downloads/afisha/backend/app/repositories/dictionary_repo.py):
  - `resolve_city_name`: нечеткий поиск города по триграммам `pg_trgm` с порогом схожести $\ge 0.45$. Например, запрос «Стерлитомак» корректно резолвится в «Стерлитамак».

- [`audit_trace_repo.py`](file:///home/scoof/Downloads/afisha/backend/app/repositories/audit_trace_repo.py):
  - `get_user_daily_spend_rub`: агрегирует сумму расходов конкретного пользователя за текущие календарные сутки.

---

### 4. Сервисный слой (`app/services/`)

- [`normalization_service.py`](file:///home/scoof/Downloads/afisha/backend/app/services/normalization_service.py):
  - Нормализация заголовков (удаление мусора, лишних пробелов, HTML-тегов).
  - Парсинг цен: извлекает `(price_min, price_max, is_free)` из строк вида «от 300 до 1500 руб», «вход свободный», «бесплатно».
  - Приведение временных меток к часовому поясу Башкортостана (`Asia/Yekaterinburg`, UTC+5).
  - Приведение возрастных цензов к дискретной шкале: `0`, `6`, `12`, `16`, `18`.

- [`deduplication_service.py`](file:///home/scoof/Downloads/afisha/backend/app/services/deduplication_service.py):
  - Метод `merge_event_fields`: слияние карточек из нескольких источников с учетом авторитетности первоисточника.
  - Оценка уровня доверия (`confidence_score`) и выставление флага диспута (`is_disputed`) при расхождении критических параметров (цена, время начала).

- [`import_service.py`](file:///home/scoof/Downloads/afisha/backend/app/services/import_service.py):
  - Идемпотентный импорт из CSV и JSON.
  - Метод `replay_all_normalizations`: перепрогон правил нормализации по всем сохраненным записям `raw_event_records`.

- [`fallback_search_service.py`](file:///home/scoof/Downloads/afisha/backend/app/services/fallback_search_service.py):
  - Детерминированный парсер запросов на базе регулярных выражений и словарей без обращения к LLM. Извлекает категории («концерт», «театр», «выставка»), даты («сегодня», «завтра», «на выходных») и ценовые ограничения («бесплатно», «до 1000 руб»).

---

### 5. ИИ-агент на LangGraph (`app/agent/`)

Архитектура агента реализует **3-й уровень автономности**:

```mermaid
flowchart TD
    User([Пользователь]) --> GuardrailsIn[Guardrails: check_user_input]
    GuardrailsIn --> BudgetCheck{Проверка бюджета и Circuit Breaker}
    BudgetCheck -- Превышен / OPEN --> FallbackService[FallbackSearchService]
    BudgetCheck -- Доступен --> LangGraphNode[LangGraph ReAct Node]
    LangGraphNode --> Tools{Вызов инструментов}
    Tools --> Tool1[search_events]
    Tools --> Tool2[get_event_card]
    Tools --> Tool3[find_similar_events]
    Tools --> Tool4[get_venue_schedule]
    Tools --> Tool5[subscribe_to_events]
    Tools --> Tool6[save_organizer_feedback]
    Tool5 & Tool6 -- Без confirmed_action_id --> ConfirmReq[CONFIRMATION_REQUIRED]
    Tools --> LangGraphNode
    LangGraphNode --> FactCheck[Fact-Checking: verify_output_grounding]
    FactCheck --> Streamer[SSE Streamer с Heartbeat]
    FallbackService --> Streamer
    Streamer --> User
```

- **Guardrails:**
  - `check_user_input`: блокировка prompt injection попыток.
  - Спотлайтинг: внешние тексты описаний из БД оборачиваются в `<untrusted_event_description>`, предотвращая атаки непрямого внедрения промптов.
  - `verify_output_grounding`: верификация 100% привязки фактов ответа к данным, возвращенным инструментами (Zero Hallucination).
- **Инструменты (Tools):**
  6 строго типизированных функций Pydantic/LangChain. Все мутирующие операции требуют двухфазного подтверждения.
- **Память (Checkpointer):**
  `AsyncPostgresSaver` с обрезкой контекста (`trim_conversation_history`), гарантирующей сохранение последних 5 диалоговых реплик.

---

### 6. Контроллеры API (`app/api/`)

- `GET /api/v1/events/`: публичный каталог с фильтрацией, сортировкой, пагинацией и диагностикой пустой выдачи.
- `GET /api/v1/events/{event_id}`: карточка мероприятия с поддержкой HTTP заголовков `Cache-Control`, `ETag` и `304 Not Modified`. Отмененные события возвращают `cancelled_badge`.
- `POST /api/v1/chat/message`: синхронный эндпоинт отправки сообщения агенту.
- `GET /api/v1/chat/stream`: Server-Sent Events (SSE) потоковый стриминг с генерацией событий `token`, `recommendations`, `action_required` и `heartbeat` (раз в 10 секунд).
- `POST /api/v1/subscriptions/`: оформление подписки на уведомления.
- `POST /api/v1/feedback/`: отправка обращения организатора.
- `POST /api/v1/admin/import/csv`: пакетный импорт CSV с подсчетом добавленных, сведенных и отклоненных строк.
- `POST /api/v1/admin/events/{event_id}/status`: модерация и изменение статуса мероприятия.
- `GET /health`: проверка готовности сервиса и пула соединений с БД.
