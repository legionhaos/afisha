.PHONY: help up down build logs migrate seed test test-local bench openapi clean

help:
	@echo "Афиша культуры Башкортостана — Команды разработки"
	@echo "----------------------------------------------------"
	@echo "make up          - Запуск всех сервисов в Docker (Postgres, Backend, Nginx)"
	@echo "make down        - Остановка сервисов Docker"
	@echo "make build       - Пересборка Docker контейнеров"
	@echo "make logs        - Просмотр логов бэкенда в реальном времени"
	@echo "make migrate     - Применение миграций Alembic"
	@echo "make seed        - Начальное наполнение БД реальными мероприятиями Башкортостана"
	@echo "make test        - Запуск тестов pytest в локальном окружении"
	@echo "make bench       - Запуск бенчмарка качества ИИ-агента (22 контрольных запроса)"
	@echo "make openapi     - Экспорт актуальной схемы OpenAPI 3.1 в openapi.json"
	@echo "make clean       - Очистка кэша python (__pycache__, .pytest_cache)"

up:
	docker compose up -d --build

down:
	docker compose down

build:
	docker compose build

logs:
	docker compose logs -f backend

migrate:
	cd backend && .venv/bin/alembic upgrade head

seed:
	cd backend && .venv/bin/python scripts/seed_demo_data.py

test:
	cd backend && .venv/bin/pytest -v

bench:
	backend/.venv/bin/python eval/run_benchmark.py

openapi:
	cd backend && python -c "import json; from app.main import app; open('openapi.json', 'w', encoding='utf-8').write(json.dumps(app.openapi(), ensure_ascii=False, indent=2))" && cp backend/openapi.json ./openapi.json
	@echo "OpenAPI 3.1 schema exported successfully."

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
