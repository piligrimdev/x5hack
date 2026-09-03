---

description: "Task list template for feature implementation"
---

# Tasks: FastAPI Web Application Setup

**Input**: Design documents from `specs/001-fastapi-web-setup/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/health.md

**Tests**: Включён smoke-тест для health endpoint (критерий приёмки US1).

**Organization**: Задачи сгруппированы по user story для независимой реализации и тестирования.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Можно выполнять параллельно (разные файлы, нет зависимостей)
- **[Story]**: К какой user story относится задача (US1, US2)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Установка зависимостей и инициализация структуры пакета

- [x] T001 Добавить production-зависимости в `web/pyproject.toml`: fastapi, uvicorn[standard], sqlalchemy, alembic, pydantic, structlog, python-dotenv, psycopg2-binary
- [x] T002 Добавить dev-зависимости в `web/pyproject.toml`: pytest, httpx, pytest-env
- [x] T003 Создать src-layout структуру каталогов: `web/src/webx5/{core,database,entities,crud,services,routes,schemas,dependencies,utils}/__init__.py`
- [x] T004 [P] Создать директорию тестов: `web/tests/webx5/routes/__init__.py`
- [x] T005 [P] Создать `.env.example` в корне репозитория с переменной `DATABASE_URL=postgresql+psycopg2://postgres:password@localhost:5432/x5hack`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Базовая инфраструктура — БД, логирование, wiring. БЛОКИРУЕТ все user story.

**⚠️ CRITICAL**: Ни одна user story не начинается до завершения этой фазы.

- [x] T006 Реализовать класс `Database` в `web/src/webx5/database/database.py` с методами `get_db` (Generator для FastAPI Depends) и `get_sync_session` (contextmanager для воркеров), sync engine с `pool_pre_ping=True`
- [x] T007 [P] Реализовать `configure_logging()` и `default_log_dir()` в `web/src/webx5/core/logging_config.py` с использованием structlog (JSON-рендерер для prod, консоль для dev)
- [x] T008 [P] Создать `Base = DeclarativeBase()` в `web/src/webx5/entities/__init__.py`
- [x] T009 Создать `SessionDep = Annotated[Session, Depends(db.get_db)]` в `web/src/webx5/dependencies/db.py` (зависит от T006)
- [x] T010 Реализовать `web/src/webx5/core/db.py`: инстанциировать `Database(os.getenv("DATABASE_URL"))`, экспортировать `db`
- [x] T011 Реализовать `web/src/webx5/core/server.py`: создать `FastAPI()` app, подключить роутеры, экспортировать `api`
- [x] T012 Реализовать `web/src/webx5/main.py`: `load_dotenv`, `configure_logging`, structlog startup-лог, `asyncio` event loop + `api.server.serve()`

**Checkpoint**: Инфраструктура готова — можно запустить пустой сервис

---

## Phase 3: User Story 1 — Service Health Verification (Priority: P1) 🎯 MVP

**Goal**: Сервис отвечает на `GET /health` → HTTP 200 `{"status": "ok"}` менее чем за 500 мс

**Independent Test**: `curl -s http://localhost:8000/health` возвращает `{"status":"ok"}`

### Implementation

- [x] T013 [US1] Создать `HealthResponse(BaseModel)` с полем `status: str` в `web/src/webx5/schemas/health.py`
- [x] T014 [US1] Реализовать `health_router = APIRouter(prefix="/health")` с `GET /` эндпоинтом в `web/src/webx5/routes/health.py` — возвращает `HealthResponse(status="ok")` без аутентификации
- [x] T015 [US1] Подключить `health_router` в `web/src/webx5/core/server.py` (обновить файл)
- [x] T016 [US1] Написать smoke-тест в `web/tests/webx5/routes/test_health.py`: `TestClient(app).get("/health")` → assert status 200, assert body `{"status":"ok"}`

**Checkpoint**: `curl http://localhost:8000/health` → `{"status":"ok"}` и pytest проходит

---

## Phase 4: User Story 2 — Database Connectivity (Priority: P2)

**Goal**: Alembic миграции применяются без ошибок; сервис стартует с подключённой БД

**Independent Test**: `poetry run alembic upgrade head` завершается без ошибок; `alembic current` показывает `(head)`

### Implementation

- [x] T017 [US2] Инициализировать Alembic: `poetry run alembic init alembic` из `web/`; создать `web/alembic.ini`
- [x] T018 [US2] Настроить `web/alembic/env.py`: импортировать `Base` из `webx5.entities`, читать `DATABASE_URL` из env, использовать `Base.metadata` для `target_metadata`
- [x] T019 [US2] Создать первую ревизию миграции: `poetry run alembic revision --autogenerate -m "init"` из `web/`; проверить сгенерированный файл в `web/alembic/versions/`

**Checkpoint**: `poetry run alembic upgrade head` — таблица `alembic_version` создана в БД

---

## Phase 5: Polish & Cross-Cutting Concerns

**Purpose**: Финальная валидация и порядок

- [x] T020 [P] Добавить `[tool.pytest.ini_options]` в `web/pyproject.toml`: `testpaths = ["tests"]`, `pythonpath = ["src"]`
- [x] T021 [P] Добавить `.env` в `web/.gitignore` и проверить `.gitignore` в корне репозитория
- [x] T022 Запустить все сценарии из `specs/001-fastapi-web-setup/quickstart.md` и зафиксировать результат

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: Нет зависимостей — начинать немедленно
- **Foundational (Phase 2)**: Зависит от завершения Phase 1 — БЛОКИРУЕТ все user story
- **US1 (Phase 3)**: Зависит от Phase 2; независима от US2
- **US2 (Phase 4)**: Зависит от Phase 2; независима от US1
- **Polish (Phase 5)**: После завершения US1 и US2

### User Story Dependencies

- **US1 (P1)**: Начать после Phase 2 — зависимостей от US2 нет
- **US2 (P2)**: Начать после Phase 2 — зависимостей от US1 нет

### Within Each Phase

- T006, T007, T008 в Phase 2 можно запускать параллельно
- T009 зависит от T006; T010 зависит от T006; T011 зависит от T014 (US1)
- T013, T014 в US1 можно параллельно после T012 (но T012 — схема — нет зависимостей)

---

## Parallel Example: Foundational Phase

```bash
# Запустить параллельно:
Task: "Реализовать Database class в web/src/webx5/database/database.py" (T006)
Task: "Реализовать configure_logging() в web/src/webx5/core/logging_config.py" (T007)
Task: "Создать DeclarativeBase в web/src/webx5/entities/__init__.py" (T008)
```

## Parallel Example: User Story 1

```bash
# После T006 завершён:
Task: "Создать HealthResponse schema в web/src/webx5/schemas/health.py" (T013)
Task: "Реализовать health router в web/src/webx5/routes/health.py" (T014)
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Завершить Phase 1: Setup
2. Завершить Phase 2: Foundational (КРИТИЧНО — блокирует все)
3. Завершить Phase 3: User Story 1
4. **СТОП и ВАЛИДАЦИЯ**: `curl http://localhost:8000/health` + `poetry run pytest`
5. Демо готово

### Incremental Delivery

1. Phase 1 + Phase 2 → сервис стартует (без роутов)
2. Phase 3 → `/health` работает → **MVP!**
3. Phase 4 → Alembic миграции применяются → БД готова к следующим фичам
4. Phase 5 → Чистота и финальная валидация

---

## Notes

- [P] = разные файлы, нет взаимных зависимостей
- [Story] = трейсабилити задачи к user story
- После T012 в Phase 2 (`main.py`) сервис уже запускается, но без роутов — нормально
- `alembic init alembic` (T017) перезапишет `env.py` — сразу применять правки из T018
- Коммитить после каждого checkpoint
