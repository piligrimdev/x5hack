# Research: FastAPI Web Application Setup

**Feature**: 001-fastapi-web-setup
**Date**: 2026-09-03

## Decision Log

### 1. Расположение сервисного пакета

**Decision**: `web/src/webx5/`
**Rationale**: Пакет `webx5` уже инициализирован в `web/pyproject.toml`. Конституция требует FastAPI-сервис как отдельный пакет под `web/`. Src-layout (`web/src/webx5/`) изолирует пакет от тестов и корня.
**Alternatives considered**: `web/webx5/` (flat layout) — отклонён, src-layout лучше предотвращает случайные импорты из корня.

### 2. Health endpoint — проверка БД

**Decision**: `/health` возвращает `{"status": "ok"}` без пинга БД.
**Rationale**: Health endpoint должен отвечать как можно быстрее и не зависеть от состояния внешних зависимостей. Отдельный `GET /health/db` может быть добавлен позже для deep health checks. Spec SC-001 требует <500 мс.
**Alternatives considered**: Включить ping БД в `/health` — отклонён, это смешивает liveness и readiness проверки.

### 3. Alembic — расположение миграций

**Decision**: `web/alembic/` рядом с `web/pyproject.toml`, `alembic.ini` в корне `web/`.
**Rationale**: Стандартное расположение Alembic; `env.py` импортирует `Base` из `webx5.entities`, что требует установленного пакета через Poetry. Команды запускаются из `web/`.
**Alternatives considered**: `web/src/webx5/migrations/` — отклонён, Alembic ожидает `alembic.ini` рядом с командой, нестандартное расположение усложняет CLI.

### 4. Database URL — переменные окружения

**Decision**: `DATABASE_URL` как единственная переменная (DSN-строка PostgreSQL).
**Rationale**: Один DSN проще, чем разделённые HOST/PORT/USER/PASS/DB; поддерживается SQLAlchemy напрямую; совместимо с Docker, Railway, Heroku.
**Alternatives considered**: Отдельные переменные (PG_HOST, PG_PORT, ...) — отклонён, требует дополнительной сборки DSN в коде.

### 5. Python версия

**Decision**: Python >=3.12 (хотя `pyproject.toml` указывает >=3.14 — уточнить при запуске).
**Rationale**: `pyproject.toml` в `web/` уже задаёт `requires-python = ">=3.14"`, оставляем без изменений. Если Python 3.14 недоступен в среде — понизить до >=3.12.
**Alternatives considered**: N/A — задано существующим проектом.

### 6. ASGI-сервер

**Decision**: `uvicorn` (standard extras).
**Rationale**: Стандарт для FastAPI; поддерживает graceful shutdown; легковесен для PoC.
**Alternatives considered**: Hypercorn, Gunicorn+uvicorn worker — излишне для хакатона.
