# Implementation Plan: Dual-Consumer Authorization

**Branch**: `003-auth` | **Date**: 2026-09-03 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/003-auth/spec.md`

## Summary

Добавить авторизацию для двух типов потребителей API: мобильные пользователи (JWT, регистрация по телефону) и кассовые аппараты (статичный заголовочный токен). Реализация следует RSI-архитектуре существующего пакета `webx5`: новые слои `entities/`, `crud/`, `services/`, `routes/`, `schemas/`, `dependencies/`, `utils/` с минимальным вмешательством в существующий код.

## Technical Context

**Language/Version**: Python 3.12

**Primary Dependencies**: FastAPI 0.115, SQLAlchemy 2.0 (sync), Pydantic 2, Alembic, structlog, PyJWT (новая), phonenumbers (новая)

**Storage**: PostgreSQL (psycopg2-binary) — уже настроен; новая таблица `users`

**Testing**: pytest + httpx (уже настроены); unit-тесты сервисов, интеграционные тесты роутов

**Target Platform**: Linux-контейнер (Docker Compose)

**Project Type**: Web-service (REST API)

**Performance Goals**: Регистрация/вход ≤ 2 секунды (SC-001); отклонение дубликата ≤ 1 секунды (SC-002)

**Constraints**: JWT stateless, TTL 7 дней; без revocation; один статичный токен кассы через env var

**Scale/Scope**: PoC/хакатон; нет конкурентных нагрузочных требований

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Принцип | Применимость | Статус | Комментарий |
|---------|-------------|--------|-------------|
| I. Экономия как метрика | Не применимо (инфраструктура) | ✅ Pass | Auth — не пользовательская механика |
| II. Минимальный барьер | Применимо | ✅ Pass | Регистрация = 1 экран, 1 поле, 1 кнопка |
| III. AI-персонализация | Не применимо | ✅ Pass | Auth не затрагивает генерацию челленджей |
| IV. Юнит-экономика | Не применимо (инфраструктура) | ✅ Pass | Auth не является демонстрируемой механикой |
| V. Privacy by Design | **Применимо** | ✅ Pass | Номер телефона — только внутренний идентификатор; в публичные ответы и рейтинг не попадает |
| Backend RSI | Применимо | ✅ Pass | Repository → Service → Route, DI, structlog |
| Poetry-only deps | Применимо | ✅ Pass | PyJWT и phonenumbers добавляются через Poetry |
| Без ad-hoc pip | Применимо | ✅ Pass | Dockerfile уже использует `poetry install` |

**Constitution Check Post-Design**: переоценка после Phase 1 — все gate'ы сохраняются. Детали в research.md.

## Project Structure

### Documentation (this feature)

```text
specs/003-auth/
├── plan.md              # This file
├── research.md          # Phase 0 — выбор библиотек, паттерны
├── data-model.md        # Phase 1 — сущность User
├── quickstart.md        # Phase 1 — сценарии валидации
├── contracts/
│   └── auth.md          # Phase 1 — API-контракт
└── tasks.md             # Phase 2 — /speckit-tasks (не создаётся здесь)
```

### Source Code (repository root)

```text
web/
├── pyproject.toml                   # добавить PyJWT, phonenumbers
├── src/webx5/
│   ├── entities/
│   │   └── user.py                  # NEW: User SQLAlchemy entity
│   ├── crud/
│   │   └── user.py                  # NEW: UserRepository
│   ├── services/
│   │   └── auth.py                  # NEW: AuthService (register, login)
│   ├── routes/
│   │   └── auth.py                  # NEW: POST /register, POST /login
│   ├── schemas/
│   │   └── auth.py                  # NEW: RegisterRequest, LoginRequest, TokenResponse
│   ├── dependencies/
│   │   └── auth.py                  # NEW: CurrentUserUUID, TerminalTokenDep
│   ├── utils/
│   │   └── auth.py                  # NEW: encode_jwt, decode_jwt, normalize_phone
│   └── core/
│       └── server.py                # EDIT: include auth_router
└── alembic/
    └── versions/
        └── <hash>_add_users.py      # NEW: Alembic migration

tests/webx5/
├── services/
│   └── test_auth.py                 # NEW: unit-тесты AuthService
└── routes/
    └── test_auth.py                 # NEW: интеграционные тесты auth роутов
```

**Structure Decision**: Option 3 (Mobile + API) — проект уже имеет `web/` (бэкенд) и `x5mobile/` (мобильный). Вся реализация auth — в `web/`. Мобильная часть (хранение токена) — отдельная задача вне данного плана.

## Complexity Tracking

Нет нарушений Constitution Check — таблица не заполняется.
