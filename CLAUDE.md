# CLAUDE.md — Руководство по разработке для Claude Code / Antigravity

Проект: **Афиша культуры Башкортостана (Уровень 3: ИИ-агент)**
Модуль: **Backend (FastAPI, SQLAlchemy 2.0, PostgreSQL 16 + pgvector, LangGraph)**

---

## 1. Команды для разработки и проверки

```bash
# Переход в директорию бэкенда
cd backend

# Проверка синтаксиса и импортов
python -m py_compile app/**/*.py
python -c "import app.main; print('Imports OK')"

# Запуск тестов
pytest -v

# Применение миграций Alembic
alembic upgrade head

# Локальный запуск dev-сервера
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

---

## 2. Архитектурный контракт и правила разработки

### 2.1. Структура каталогов
- Модели SQLAlchemy 2.0: строго в `backend/app/models/`
- Миграции базы данных: строго в `backend/migrations/`
- Модуль ИИ-агента на LangGraph: строго в `backend/app/agent/`
- Контроллеры FastAPI: строго в `backend/app/api/v1/`
- Сервисный слой: строго в `backend/app/services/`
- Слой репозиториев: строго в `backend/app/repositories/`
- DTO-схемы Pydantic v2: строго в `backend/app/schemas/`
- Системное ядро: строго в `backend/app/core/`

### 2.2. Требования к коду
1. **Python 3.12+** с максимальной строгостью типов (`typing`, `Type Hints`).
2. **SQLAlchemy 2.0**:
   - Только `AsyncSession`.
   - Инициализация сессий: `expire_on_commit=False`.
   - Для подгрузки отношений — `selectinload`.
3. **Pydantic v2**:
   - `model_config = ConfigDict(from_attributes=True)`.
   - Все даты в DTO — `pydantic.AwareDatetime` в таймзоне `Asia/Yekaterinburg` (UTC+5).
4. **LangGraph Checkpointer**:
   - Отдельный пул `AsyncConnectionPool` из `psycopg_pool`.
   - Обязательные параметры: `autocommit=True`, `row_factory=dict_row`.
   - Флаг `LANGGRAPH_STRICT_MSGPACK=true`.
5. **Telegram ID**:
   - Хранить в БД как `BIGINT` (`BigInteger` в SQLAlchemy).
6. **Ошибки по RFC 7807**:
   - `Content-Type: application/problem+json`.
   - Единый базовый класс `AppError` и обработчик `rfc7807_exception_handler`.
7. **Логирование и ПДн**:
   - `structlog` с процессором `PIIScrubberProcessor` (маскирование телефонов, почты, IP, токенов).

---

## 3. Рабочий процесс генерации кода

1. Генерировать модули строго шаг за шагом в соответствии со спецификацией.
2. После каждого шага запускать терминальную проверку импортов и тестов.
3. Не переходить к следующему шагу при наличии любых ошибок или предупреждений линтера/интерпретатора.
