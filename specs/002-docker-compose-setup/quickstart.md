# Quickstart & Validation Guide

**Feature**: 002-docker-compose-setup
**Date**: 2026-09-03

## Prerequisites

- Docker Desktop установлен и запущен
- Репозиторий склонирован
- `.env` файл настроен в корне репозитория (см. `.env.example`)

## Setup

### 1. Создать .env (если не существует)

```bash
cp .env.example .env
# Значения по умолчанию работают для локальной разработки без правок
```

### 2. Собрать и запустить стек

```bash
docker compose up --build
```

**Ожидаемый вывод в логах** (в порядке появления):
1. `db` — `database system is ready to accept connections`
2. `web` — `Running migrations...`
3. `web` — `alembic upgrade head` (или сообщение об ошибке, если БД пустая и нет миграций)
4. `web` — `app.starting service=webx5`
5. `web` — `Uvicorn running on http://0.0.0.0:8000`

## Validation Scenarios

### Scenario 1: Health Check (US1 — базовая проверка)

```bash
curl -s http://localhost:8000/health
```

**Ожидаемый ответ**: `{"status":"ok"}` (HTTP 200)

---

### Scenario 2: Сервис доступен извне контейнера (US1)

```bash
# Проверить, что порт опубликован
docker compose ps

# Ожидаемый вывод: web ... 0.0.0.0:8000->8000/tcp
```

---

### Scenario 3: Данные БД сохраняются между перезапусками (US1)

```bash
docker compose down
docker compose up -d
curl -s http://localhost:8000/health
# Сервис должен ответить без повторного применения миграций
```

---

### Scenario 4: Миграции применяются автоматически (US2)

```bash
# Запустить на чистой БД (удалить volume)
docker compose down -v
docker compose up --build

# Проверить наличие таблицы версий миграций
docker compose exec db psql -U postgres -d x5hack -c "\dt"
# Ожидаемый вывод: alembic_version таблица присутствует
```

---

### Scenario 5: Идемпотентность миграций (US2)

```bash
# Перезапустить стек при уже применённых миграциях
docker compose restart web
docker compose logs web | grep -i migrat
# Ожидаемый вывод: "alembic upgrade head" завершается без ошибок
```

---

### Scenario 6: Non-blocking при ошибке миграции (US2)

```bash
# Сервер должен стартовать даже если миграция упала
docker compose logs web | grep -E "Migration|Starting server"
# Ожидаемый вывод: оба сообщения присутствуют вне зависимости от результата миграции
```

---

### Scenario 7: Документация /docs (US3)

```bash
# Открыть в браузере
open http://localhost:8000/docs
# или проверить через curl
curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/docs
# Ожидаемый код: 200
```

---

### Scenario 8: Try it через Scalar UI (US3)

Открыть `http://localhost:8000/docs` → найти `GET /health` → нажать «Test Request» → ожидаемый ответ `{"status":"ok"}`.

---

### Scenario 9: Время запуска стека (SC-001)

```bash
time docker compose up --build 2>&1 | grep "Uvicorn running"
# Ожидаемый результат: < 90 секунд с нуля
```

## Contract Reference

- [/docs endpoint contract](contracts/docs.md)
- [/health endpoint contract](../001-fastapi-web-setup/contracts/health.md)
- [Environment variables](data-model.md#environment-variables-compose-level)
