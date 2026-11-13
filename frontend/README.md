# Веб-интерфейс «Афиша культуры Башкортостана»

## Запуск

Из корня `/Users/makarrr/Documents/кибер102/afisha` весь стек без Nginx запускается командой `docker compose up -d --build`. Сайт: http://localhost:3000, backend (только локально): http://localhost:8000/docs. Миграции запускаются при старте backend; БД хранится в Docker volume. Для тестовых данных выполните `docker compose exec -T backend python scripts/seed_hackathon_demo.py` (события вымышлены и помечены [ДЕМО]). Остановка: `docker compose down`. Это локальная демонстрация, не безопасный публичный деплой: API подписок backend не защищён, реальные данные/токены не использовать. Туннель и Telegram Mini App этой командой не настраиваются.

Для отдельного запуска интерфейса нужен Node.js 22 или новее и npm. Из папки `frontend`:

```sh
npm ci
npm run dev
```

Откройте http://localhost:3000. По умолчанию включён **демонстрационный режим**: все четыре события вымышлены, чат не имитируется и требует работающего backend.

Проверки: `npm run typecheck`, `npm run build`, `npm audit --omit=dev`. Production: `npm run build && npm start`. Виджет: http://localhost:3000/widget; информационные страницы админки: http://localhost:3000/admin.

## Интеграция с backend

Frontend и backend ещё не согласовали реальные контракты. Для реальных данных при сборке/запуске frontend задайте `NEXT_PUBLIC_DATA_MODE=api`; `BACKEND_URL` — адрес backend, доступный серверу Next.js (по умолчанию `http://localhost:8000`). В Docker используйте сетевое имя сервиса backend, например `http://backend:8000`. Next.js проксирует `/api/*` на backend. Публичные `NEXT_PUBLIC_*` переменные включаются в сборку: при изменении режима production-сборку необходимо пересобрать.

Временный контракт описан в `src/types/api.ts`: `GET /api/v1/events` принимает фильтры `city`, `category`, `date_from`, `date_to`, `query`, `free`, `page` и возвращает `{items, total}`; `GET /api/v1/events/{id}` возвращает событие. Предполагается цена в рублях, время ISO 8601 с часовым поясом; интерфейс отображает время в Asia/Yekaterinburg. Поля и пагинацию обязательно согласовать с backend.

Чат предполагает `POST /api/v1/chat/stream` с JSON `{message, thread_id}` и ответом SSE или JSON; детали разбора находятся в `src/lib/sse-client.ts`. Настоящая работа агента зависит от backend и LLM. Протокол, сценарии fallback, структурированные карточки и подтверждения изменений необходимо согласовать и проверить совместно с командой агента.

`/admin`, `/admin/import`, `/admin/moderation`, `/admin/traces/[traceId]` — информационные заглушки: авторизация, импорт, модерация и traces не реализованы. Их необходимо подключить к защищённому backend API; сам frontend не обеспечивает авторизацию. Виджет можно встраивать через iframe; ограничения `frame-ancestors` и разрешённые сайты нужно настроить перед публикацией.
