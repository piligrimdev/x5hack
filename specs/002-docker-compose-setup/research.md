# Research: Docker Compose Setup

**Feature**: 002-docker-compose-setup
**Date**: 2026-09-03

## Decision Log

### 1. Python base image

**Decision**: `python:3.12-slim`
**Rationale**: Минимальный официальный образ с Python 3.12. `slim` убирает dev-утилиты (~150MB vs ~900MB full). Совместим с Poetry и psycopg2-binary (бинарная сборка не требует libpq-dev).
**Alternatives considered**: `python:3.14-slim` — Python 3.14 ещё нестабилен в некоторых образах; `alpine` — требует компиляции psycopg2 из исходников (нет бинарного wheel).

### 2. Poetry в Docker — virtualenv

**Decision**: `POETRY_VENVS_CREATE=false` — устанавливать зависимости напрямую в системный Python образа.
**Rationale**: В контейнере нет смысла создавать виртуальное окружение внутри виртуального окружения (образ уже изолирован). Это упрощает пути и ускоряет старт.
**Alternatives considered**: Устанавливать в virtualenv (`/venv`) — усложняет `PATH` и `PYTHONPATH`.

### 3. Docker слои — порядок COPY

**Decision**: Сначала `COPY pyproject.toml poetry.lock ./` + `RUN poetry install`, затем `COPY src/ alembic/ alembic.ini ./`.
**Rationale**: Кэшируем тяжёлый слой установки зависимостей — он инвалидируется только при изменении lock-файла, не при каждом изменении кода.
**Alternatives considered**: `COPY . .` одним слоем — отменяет кэш при любом изменении файла.

### 4. Механизм ожидания БД

**Decision**: `depends_on: db: condition: service_healthy` + `pg_isready` healthcheck на postgres-сервисе.
**Rationale**: Нативный механизм Compose V2; декларативен; не требует скриптов wait-for-it. `pg_isready` — официальный инструмент PostgreSQL для проверки готовности.
**Alternatives considered**: `wait-for-it.sh` или `dockerize` — внешние зависимости; retry-цикл в Python — смешивает инфраструктурную логику с приложением.

### 5. Entrypoint — миграции non-blocking

**Decision**: `entrypoint.sh` запускает `alembic upgrade head`; при ошибке — логирует и продолжает запуск сервера (`|| true`).
**Rationale**: Явное решение пользователя: сервер ДОЛЖЕН запуститься даже при ошибке миграции. Это позволяет диагностировать проблему через работающий сервис, не перезапуская контейнер.
**Alternatives considered**: `set -e` с остановкой на ошибке — противоречит FR-008 (updated).

### 6. scalar-fastapi интеграция

**Decision**: Переопределить `/docs` через `get_scalar_api_reference(openapi_url=app.openapi_url, title=app.title)`. Стандартные `/docs` и `/redoc` FastAPI отключить (`docs_url=None, redoc_url=None`).
**Rationale**: Scalar предоставляет современный UI; отключение дефолтных эндпоинтов исключает дублирование.
**Alternatives considered**: Оставить Swagger UI параллельно с Scalar — избыточно для PoC.

### 7. PostgreSQL версия в compose

**Decision**: `postgres:16-alpine`
**Rationale**: LTS-версия, alpine-образ (~80MB). Соответствует типичным production-версиям.
**Alternatives considered**: `postgres:latest` — нестабильно для зафиксированных окружений.

### 8. PYTHONPATH в Docker

**Decision**: `ENV PYTHONPATH=/app/src` в Dockerfile.
**Rationale**: src-layout требует явного пути для импорта пакета `webx5` при `poetry install --no-root`.
**Alternatives considered**: `poetry install` (с root) — устанавливает пакет в site-packages, но требует установки пакета в prod-образе.
