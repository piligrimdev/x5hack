# Implementation Plan: Составные задания, типы наград и вайб

**Branch**: `008-composite-challenges-rewards-vibe` | **Date**: 2026-09-06 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/008-composite-challenges-rewards-vibe/spec.md`

## Summary

Три независимых расширения бэкенда (`web/`): (1) составные задания через таблицу `task_item` с per-criterion прогрессом; (2) подарочный тип награды через таблицу `gift_reward`, применяемый при расчёте корзины и чека; (3) управляемый каталог вайбов через таблицу `vibe_type` с пользовательским выбором и POS CRUD через уже реализованный `TerminalTokenDep`.

## Technical Context

**Language/Version**: Python 3.11+

**Primary Dependencies**: FastAPI (sync), SQLAlchemy (sync), Alembic, structlog, pytest

**Storage**: PostgreSQL (существующий инстанс, Alembic-миграции)

**Testing**: pytest, зеркалирование в `web/tests/webx5/`

**Target Platform**: Linux server (Docker)

**Project Type**: web-service (REST API)

**Performance Goals**: PoC — стандартные показатели для хакатона

**Constraints**: Alembic-миграции должны быть обратимы (downgrade); новые таблицы не нарушают работу существующих фич

**Scale/Scope**: Синтетические данные, несколько десятков пользователей

## Constitution Check

| Принцип | Статус | Обоснование |
|---------|--------|-------------|
| I — Экономия как метрика | ✅ | Gift reward: экономия видна как конкретная сумма в корзине |
| II — ≤2 действия | ✅ | Выбор вайба — 1 API-вызов; применение подарка — автоматическое |
| III — ИИ-персонализация | ✅ | VibeType.llm_context передаётся в промпт генерации заданий |
| IV — Экономическая обоснованность | ⚠️ PoC | Gift reward стоимость = стоимость товара; unit-экономика упрощена для PoC |
| V — Privacy | ✅ | Новые таблицы не хранят персональные данные сверх существующего |
| RSI Architecture | ✅ | Все новые сущности: crud/ + services/ + routes/ |
| DI | ✅ | Новые сервисы получают репозитории через конструктор |
| Контролируемая инициализация | ✅ | Wiring через core/, без side effects на импорте |

## Project Structure

### Documentation (this feature)

```text
specs/008-composite-challenges-rewards-vibe/
├── plan.md              # Этот файл
├── research.md          # Phase 0: решения и обоснования
├── data-model.md        # Phase 1: схема БД
├── quickstart.md        # Phase 1: сценарии валидации
├── contracts/
│   └── api-contracts.md # Phase 1: API контракты
└── tasks.md             # Phase 2: /speckit-tasks
```

### Source Code

```text
web/
├── alembic/versions/
│   ├── <hash>_create_vibe_type.py           # M1: vibe_type + seed
│   ├── <hash>_add_user_vibe_type_fk.py      # M2: users.vibe_type_id + migrate
│   ├── <hash>_create_task_item.py           # M3: task_item + backfill
│   ├── <hash>_extend_task_reward_type.py    # M4: CHECK constraint
│   └── <hash>_create_gift_reward.py         # M5: gift_reward
└── src/webx5/
    ├── entities/
    │   ├── task.py         # + class TaskItem
    │   ├── user.py         # vibe_category/vibe_month → vibe_type_id FK
    │   └── vibe.py         # NEW: class VibeType
    │   └── reward.py       # NEW: class GiftReward
    ├── crud/
    │   ├── task.py         # + TaskItemRepository
    │   ├── vibe.py         # NEW: VibeRepository
    │   └── reward.py       # NEW: GiftRewardRepository
    ├── services/
    │   ├── challenge_adapter.py  # _resolve_vibe_category → vibe_type FK
    │   ├── task_completion.py    # + gift_reward creation on completion
    │   ├── discount_calculator.py # + gift_reward application
    │   └── vibe.py               # NEW: VibeService (CRUD + cascade reset)
    ├── schemas/
    │   ├── challenge.py    # + TaskItemOut в ChallengeOut
    │   ├── vibe.py         # NEW: VibeIn, VibeOut, VibeUpdate
    │   └── reward.py       # NEW: GiftRewardOut
    ├── routes/
    │   ├── vibes.py        # NEW: GET /vibes, POST /vibes, PUT, DELETE
    │   ├── rewards.py      # NEW: GET /rewards
    │   └── challenges.py   # обновить ответ: добавить items[]
    └── core/
        └── server.py       # подключить vibes_router, rewards_router

web/tests/webx5/
    ├── services/
    │   ├── test_vibe_service.py      # CRUD, cascade reset
    │   ├── test_task_completion_gift.py  # gift_reward creation
    │   └── test_gift_reward_apply.py # basket + checkout применение
    └── crud/
        └── test_task_item.py         # per-criterion progress tracking
```

## Complexity Tracking

Нет нарушений конституции, требующих обоснования.
