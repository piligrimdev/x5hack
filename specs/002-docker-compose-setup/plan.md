# Implementation Plan: Docker Compose Setup

**Branch**: `002-docker-compose-setup` | **Date**: 2026-09-03 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/002-docker-compose-setup/spec.md`

## Summary

Добавить контейнеризацию FastAPI-бэкенда: `Dockerfile` в `web/`, `docker-compose.yml` в корне репозитория. Перед стартом сервера — `entrypoint.sh` запускает `alembic upgrade head` (non-blocking). Готовность PostgreSQL обеспечивается через `depends_on: condition: service_healthy`. Документация API переключается на Scalar через `scalar-fastapi`.

## Technical Context

**Language/Version**: Python 3.12 (образ `python:3.12-slim`)

**Primary Dependencies**: FastAPI, uvicorn, SQLAlchemy, Alembic, structlog, scalar-fastapi (новый), psycopg2-binary

**Storage**: PostgreSQL 16 (`postgres:16-alpine`); данные в named volume `pgdata`

**Testing**: pytest (health endpoint smoke test из фичи 001 остаётся валидным)

**Target Platform**: Docker Desktop (macOS/Linux); Linux-server

**Project Type**: web-service + containerization

**Performance Goals**: полный запуск стека ≤90 сек; `/health` p99 <500 мс; `/docs` <3 сек

**Constraints**: Poetry (не pip); structured logging (structlog); `docker-compose.yml` в корне; `Dockerfile` в `web/`; миграции non-blocking

**Scale/Scope**: PoC/хакатон; один экземпляр каждого сервиса

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Принцип | Применим? | Статус |
|---|---|---|
| I. Экономия как метрика | Нет (инфраструктура) | ✓ N/A |
| II. Минимальный когнитивный барьер | Нет (инфраструктура) | ✓ N/A |
| III. ИИ-персонализация | Нет (инфраструктура) | ✓ N/A |
| IV. Экономическая обоснованность | Нет (инфраструктура) | ✓ N/A |
| V. Privacy by Design | ✓ — учётные данные БД не в коде, только в `.env` | ✓ Pass |
| Backend: Poetry | ✓ — Dockerfile использует Poetry | ✓ Pass |
| Backend: structlog | ✓ — entrypoint логирует через stdout | ✓ Pass |
| Backend: контролируемая инициализация | ✓ — side effects только в entrypoint и main.py | ✓ Pass |
| Backend: RSI | Не затрагивает слои; новые файлы — только инфраструктурные | ✓ Pass |

**Результат**: нарушений нет.

## Project Structure

### Documentation (this feature)

```text
specs/002-docker-compose-setup/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── docs.md
└── tasks.md        # /speckit-tasks output
```

### Source Code (repository root)

```text
/                              # Корень репозитория
├── docker-compose.yml         # Новый: оркестрация db + web
└── .env.example               # Обновить: добавить POSTGRES_* переменные

web/
├── Dockerfile                 # Новый: python:3.12-slim, Poetry, src-layout
├── entrypoint.sh              # Новый: alembic upgrade head (non-blocking) → python -m webx5
├── pyproject.toml             # Обновить: добавить scalar-fastapi зависимость
└── src/webx5/
    └── core/
        └── server.py          # Обновить: отключить /docs Swagger, добавить Scalar /docs
```

**Structure Decision**: минимальные изменения существующей структуры. Все новые файлы — в корне или `web/`. Исходный код `src/webx5/` меняется только в `server.py`.

## Complexity Tracking

Нарушений конституции нет — таблица не заполняется.
