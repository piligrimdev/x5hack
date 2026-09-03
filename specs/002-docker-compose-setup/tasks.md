---

description: "Task list for Docker Compose Setup implementation"
---

# Tasks: Docker Compose Setup

**Input**: Design documents from `specs/002-docker-compose-setup/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/docs.md

**Tests**: Не запрошены явно; валидация через quickstart.md сценарии.

**Organization**: Задачи сгруппированы по user story для независимой реализации.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Можно выполнять параллельно (разные файлы, нет зависимостей)
- **[Story]**: К какой user story относится задача (US1, US2, US3)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Подготовка зависимостей и конфигурационных файлов

- [x] T001 Добавить `scalar-fastapi>=1.0.0,<2.0.0` в `web/pyproject.toml` и обновить `web/poetry.lock` командой `poetry lock` из `web/`
- [x] T002 [P] Обновить `.env.example` в корне репозитория: добавить `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `PORT` переменные

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Базовые файлы контейнеризации, блокирующие все user story

**⚠️ CRITICAL**: US1, US2, US3 не начинаются до завершения этой фазы.

- [x] T003 Создать `web/Dockerfile`: базовый образ `python:3.12-slim`, установить Poetry с `POETRY_VENVS_CREATE=false`, скопировать `pyproject.toml`+`poetry.lock` → `RUN poetry install --no-root --only main`, затем `COPY src/ alembic/ alembic.ini ./`, установить `ENV PYTHONPATH=/app/src`, `EXPOSE 8000`, `ENTRYPOINT ["./entrypoint.sh"]`
- [x] T004 Создать `web/entrypoint.sh`: выполнить `alembic upgrade head || echo "Migration failed, continuing"`, затем `exec python -m webx5`; сделать исполняемым (`chmod +x`)
- [x] T005 [P] Создать `docker-compose.yml` в корне репозитория: сервис `db` (postgres:16-alpine) с `pg_isready` healthcheck (interval: 5s, retries: 10), сервис `web` (build: `./web`) с `depends_on: db: condition: service_healthy`, named volume `pgdata`, порты `${PORT:-8000}:8000`, env-переменные из `.env`

**Checkpoint**: `docker compose build` завершается без ошибок

---

## Phase 3: User Story 1 — Запуск сервиса одной командой (Priority: P1) 🎯 MVP

**Goal**: `docker compose up --build` поднимает стек; `GET /health` с хост-машины → HTTP 200

**Independent Test**: `curl -s http://localhost:8000/health` возвращает `{"status":"ok"}`

- [x] T006 [US1] Проверить и при необходимости исправить `web/Dockerfile`: убедиться что `COPY entrypoint.sh ./` и `RUN chmod +x entrypoint.sh` присутствуют; образ собирается командой `docker compose build`
- [x] T007 [US1] Убедиться, что `docker-compose.yml` публикует порт `${PORT:-8000}:8000` и сервис `web` достигается с хост-машины; выполнить `docker compose up -d` и проверить `docker compose ps`
- [x] T008 [US1] Добавить `restart: unless-stopped` к сервису `web` в `docker-compose.yml` для устойчивости при временных ошибках старта

**Checkpoint**: `docker compose up --build` → `curl http://localhost:8000/health` → `{"status":"ok"}`

---

## Phase 4: User Story 2 — Автоматическая подготовка базы данных (Priority: P2)

**Goal**: Alembic-миграции применяются до старта сервера; ошибка миграции не блокирует сервер

**Independent Test**: `docker compose down -v && docker compose up --build` → в логах присутствует попытка применения миграций; сервер стартует в обоих случаях (успех и ошибка)

- [x] T009 [US2] Убедиться что `web/entrypoint.sh` содержит non-blocking вызов `alembic upgrade head`: при ошибке выводит сообщение и продолжает (`|| echo "Migration failed, continuing..."`); при успехе — логирует стандартный alembic-вывод
- [x] T010 [US2] Убедиться что в `docker-compose.yml` сервис `db` имеет healthcheck: `test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-postgres} -d ${POSTGRES_DB:-x5hack}"]`, `start_period: 10s`; сервис `web` имеет `depends_on: db: condition: service_healthy`
- [x] T011 [US2] Проверить идемпотентность: запустить `docker compose restart web` на уже подготовленной БД → в логах повторное применение миграций не вызывает ошибку

**Checkpoint**: `docker compose down -v && docker compose up --build` → в логах миграции применены → `docker compose exec db psql -U postgres -d x5hack -c "\dt"` показывает `alembic_version`

---

## Phase 5: User Story 3 — Интерактивная документация API (Priority: P3)

**Goal**: `GET /docs` возвращает HTML со Scalar UI; стандартный Swagger UI отключён

**Independent Test**: `curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/docs` → `200`; страница содержит Scalar UI

- [x] T012 [P] [US3] Обновить `web/src/webx5/core/server.py`: создать `FastAPI(title="webx5", version="0.1.0", docs_url=None, redoc_url=None)` (отключить дефолтный Swagger/ReDoc)
- [x] T013 [US3] Добавить в `web/src/webx5/core/server.py` роут `GET /docs` с `include_in_schema=False`, возвращающий `get_scalar_api_reference(openapi_url=app.openapi_url, title=app.title)` из `scalar_fastapi`
- [x] T014 [US3] Обновить импорты в `web/src/webx5/core/server.py`: добавить `from scalar_fastapi import get_scalar_api_reference`; убедиться что `app.openapi_url` равен `/openapi.json`

**Checkpoint**: `docker compose up` → `open http://localhost:8000/docs` → Scalar UI загружается, `GET /health` через «Try it» возвращает `{"status":"ok"}`

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Финальная валидация и документация

- [x] T015 [P] Обновить `README.md`: добавить секцию «Docker запуск» с командами `docker compose up --build`, `docker compose down`, ссылкой на `/docs`
- [x] T016 Запустить все 9 сценариев из `specs/002-docker-compose-setup/quickstart.md` и зафиксировать результат; убедиться что SC-001 (≤90 сек), SC-002 (health <500 мс), SC-005 (/docs <3 сек) выполнены

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: Нет зависимостей — начинать немедленно
- **Foundational (Phase 2)**: Зависит от Phase 1 — БЛОКИРУЕТ все user story
- **US1 (Phase 3)**: Зависит от Phase 2; независима от US2 и US3
- **US2 (Phase 4)**: Зависит от Phase 2; независима от US1 и US3
- **US3 (Phase 5)**: Зависит от Phase 2; независима от US1 и US2 (но тестируется вместе со стеком)
- **Polish (Phase 6)**: После завершения US1, US2, US3

### User Story Dependencies

- **US1 (P1)**: Только Phase 2
- **US2 (P2)**: Только Phase 2 (entrypoint.sh уже создан в Phase 2)
- **US3 (P3)**: Только Phase 1 (scalar-fastapi установлен) + Phase 2 (контейнер запущен)

### Parallel Opportunities

- T001 и T002 в Phase 1 — параллельно
- T003, T004 и T005 в Phase 2 — параллельно (разные файлы)
- T012 в Phase 5 — независим от T013/T014 по файлу, но логически первый

---

## Parallel Example: Foundational Phase

```bash
# Запустить параллельно:
Task T003: "Создать web/Dockerfile"
Task T004: "Создать web/entrypoint.sh"
Task T005: "Создать docker-compose.yml в корне"
```

## Parallel Example: US3

```bash
# T012 (отключить дефолтный docs_url) и T013 (добавить /docs роут) — в одном файле,
# выполнять последовательно внутри server.py
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Phase 1: Setup (T001, T002)
2. Phase 2: Foundational (T003, T004, T005)
3. Phase 3: US1 (T006, T007, T008)
4. **СТОП**: `curl http://localhost:8000/health` → `{"status":"ok"}`
5. Демо готово — контейнер запущен и отвечает

### Incremental Delivery

1. Phase 1 + Phase 2 → сборка образа работает
2. Phase 3 (US1) → стек поднимается, health endpoint доступен → **MVP!**
3. Phase 4 (US2) → миграции автоматические → БД готова к следующим фичам
4. Phase 5 (US3) → документация через Scalar → разработчики мобильного/фронтенда могут работать
5. Phase 6 → README обновлён, quickstart пройден

---

## Notes

- [P] = разные файлы, нет зависимостей
- T004 (`entrypoint.sh`) перекрывается с US2 (T009) — T009 только проверяет/уточняет поведение, не переписывает файл
- `docker-compose.yml` использует `${VAR:-default}` синтаксис для всех параметров — `.env` не обязателен для первого запуска
- После T003 (`Dockerfile`) можно сразу проверить сборку: `docker build -t webx5-test web/`
- scalar-fastapi уже добавлен в pyproject.toml (автоматически), T001 — только `poetry lock` + проверка
