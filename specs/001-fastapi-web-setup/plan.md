# Implementation Plan: FastAPI Web Application Setup

**Branch**: `001-fastapi-web-setup` | **Date**: 2026-09-03 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/001-fastapi-web-setup/spec.md`

## Summary

Инициализировать FastAPI-сервис в `web/` с подключением к PostgreSQL через SQLAlchemy, управлением миграциями через Alembic и health-эндпоинтом `GET /health`. Результат — запускаемый сервис с воспроизводимой зависимостью через Poetry и готовой инфраструктурой БД для последующих фич.

## Technical Context

**Language/Version**: Python >=3.14 (задан в `web/pyproject.toml`)

**Primary Dependencies**: FastAPI, uvicorn[standard], SQLAlchemy, Alembic, pydantic, structlog, python-dotenv, psycopg2-binary

**Storage**: PostgreSQL; подключение через `DATABASE_URL` env var; DSN `postgresql+psycopg2://...`

**Testing**: pytest, httpx (TestClient для FastAPI)

**Target Platform**: Linux server (Docker), локально macOS

**Project Type**: web-service

**Performance Goals**: `/health` p99 < 500 мс

**Constraints**: Poetry (не pip), structlog (не print/logging), sync SQLAlchemy Session, src-layout (`web/src/webx5/`)

**Scale/Scope**: PoC/хакатон; не production-grade; без кластеризации

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Принцип | Применим? | Статус |
|---|---|---|
| I. Экономия как метрика | Нет (инфраструктура) | ✓ N/A |
| II. Минимальный когнитивный барьер | Нет (инфраструктура) | ✓ N/A |
| III. ИИ-персонализация | Нет (инфраструктура) | ✓ N/A |
| IV. Экономическая обоснованность | Нет (инфраструктура, не механика) | ✓ N/A |
| V. Privacy by Design | Частично — entities не содержат ПД на этом этапе | ✓ Pass |
| Backend RSI Architecture | Да | ✓ routes/ + services/ + crud/ |
| Dependency Injection | Да | ✓ FastAPI Depends, SessionDep |
| Controlled initialization | Да | ✓ side-effects только в main.py + core/ |
| Poetry | Да | ✓ |
| structlog | Да | ✓ |
| Tests mirror src/ | Да | ✓ tests/webx5/ |

**Результат проверки**: все применимые принципы соблюдены. Нарушений нет.

## Project Structure

### Documentation (this feature)

```text
specs/001-fastapi-web-setup/
├── plan.md              # Этот файл
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   └── health.md        # Phase 1 output
└── tasks.md             # Phase 2 output (/speckit-tasks)
```

### Source Code (repository root)

```text
web/
├── pyproject.toml           # Добавить fastapi, sqlalchemy, alembic, uvicorn, structlog, etc.
├── poetry.lock
├── alembic.ini              # Новый: конфиг Alembic
├── alembic/
│   ├── env.py               # Новый: импортирует Base из webx5.entities
│   ├── script.py.mako       # Шаблон Alembic (генерируется)
│   └── versions/
│       └── <hash>_init.py   # Первая ревизия (пустая, baseline)
└── src/
    └── webx5/
        ├── __init__.py
        ├── main.py              # composition root: load_dotenv, logging, serve
        ├── core/
        │   ├── __init__.py
        │   ├── logging_config.py    # configure_logging(), default_log_dir()
        │   ├── db.py                # Database instance, wiring
        │   └── server.py            # FastAPI app + router mounting
        ├── database/
        │   ├── __init__.py
        │   └── database.py          # class Database(db_uri) → engine, session, get_db, get_sync_session
        ├── entities/
        │   └── __init__.py          # Base = DeclarativeBase(); будущие таблицы импортируются здесь
        ├── crud/                    # Пусто на этом этапе
        │   └── __init__.py
        ├── services/                # Пусто на этом этапе
        │   └── __init__.py
        ├── routes/
        │   ├── __init__.py
        │   └── health.py            # GET /health → {"status": "ok"}
        ├── schemas/
        │   ├── __init__.py
        │   └── health.py            # HealthResponse(BaseModel)
        ├── dependencies/
        │   ├── __init__.py
        │   └── db.py                # SessionDep = Annotated[Session, Depends(db.get_db)]
        └── utils/
            └── __init__.py

tests/
└── webx5/
    ├── __init__.py
    └── routes/
        ├── __init__.py
        └── test_health.py           # TestClient → GET /health → assert 200 + {"status":"ok"}
```

**Structure Decision**: src-layout под `web/src/webx5/` — пакет уже инициализирован в `web/pyproject.toml`. Alembic живёт в `web/alembic/` рядом с `alembic.ini` для стандартного CLI. Тесты в `web/tests/` зеркалируют `web/src/`.

## Complexity Tracking

Нарушений конституции нет — таблица не заполняется.
