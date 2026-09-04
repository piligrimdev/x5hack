# Implementation Plan: Кешбек в баллах вместо скидочной награды за задания

**Branch**: `007-cashback-points` | **Date**: 2026-09-04 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/007-cashback-points/spec.md`

## Summary

Заменяем существующую форму награды за задание (создание записи в `discounts`) на начисление баллов пользователю. Баллы можно тратить при оплате чека — их конвертация в рубли идёт по настраиваемому курсу (по умолчанию 10 баллов = 1 руб). **Начисление** идёт as-is: `points = int(task.reward_rub)`; курс участвует ТОЛЬКО в списании и в предварительном расчёте (`POST /receipts/calculate`). Кешбек применяется ко всему чеку (не к конкретным позициям), считается за экономию и суммируется с discount-экономией в общем счётчике «сколько сэкономлено» (принцип I конституции). Баланс не может уходить в минус (`CHECK (balance >= 0)` + pessimistic per-user row-lock). Атомарность и идемпотентность — на уровне БД (транзакции + уникальный индекс `(type='earn', related_task_id)`).

## Technical Context

**Language/Version**: Python 3.11 (существующий пакет `web/src/webx5/`); TypeScript strict (`x5mobile/`).

**Primary Dependencies**: FastAPI, SQLAlchemy 2.x, Alembic, Celery (для background-таска списания/начисления, если применимо), structlog, pytest. Мобильный клиент — Expo v57, Expo Router, React Native.

**Storage**: PostgreSQL (существующая БД сервиса). Новые таблицы `points_account`, `points_transaction`, `points_settings`. Расширение существующей `receipts` тремя полями.

**Testing**: pytest (unit + integration с in-memory или контейнер-PG); отдельные тесты на конкурентное списание (`points_service.spend` под нагрузкой в потоках).

**Target Platform**: Linux server (Docker Compose, существующий контур); мобильные экраны — iOS/Android через Expo.

**Project Type**: Web-service (Python backend) + mobile app (Expo). Frontend-делта в этой фиче минимальна: один экран баланса/истории + переиспользование существующих экранов заданий и чеков.

**Performance Goals**:
- `POST /receipts/calculate` с баллами — ≤ 500 мс p95 (SC-004).
- `POST /receipts` с списанием — ≤ 2 с p95 (SC-005).
- `GET /points/balance` — ≤ 300 мс p95 (SC-006).

**Constraints**:
- Целочисленная арифметика для денег/баллов (никакого float): `balance INT`, `amount INT`, `rate INT`, `cashback_rub INT` (в этой фиче — Numeric не нужен, потому что списание кратно рублю и балл — целое). `receipt_item.paid_price` остаётся Numeric, но `cashback_applied_rub` — целое.
- Атомарность списания баллов и создания чека — одна SQL-транзакция.
- Инвариант `balance >= 0` — на уровне DB constraint + логика сервиса.
- Обратная совместимость: не переименовываем существующие поля `receipt.*`, `task.reward_rub`.

**Scale/Scope**: PoC для хакатона: до ~1000 пользователей, до ~50000 задач в БД. Нагрузка на списание — единичные конкурентные транзакции; нагрузочные показатели SC-003 (100 параллельных списаний) верифицируются в тесте.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Принцип | Соответствие | Обоснование |
|---|---|---|
| I. Экономия как единая метрика | ✅ | Cashback добавляется в `receipt.total_saved` и в дашборд экономии (FR-013). Пользователь видит суммарную «экономию» = скидки + кешбек. |
| II. Минимальный когнитивный барьер | ✅ | Экран «Мои баллы» — один тап от главного (в мобильном приложении). Кассир видит применённый кешбек прямо в /calculate — без дополнительных экранов. `points_to_spend` в API — опциональное; отсутствие = 0. |
| III. ИИ-персонализация с hit rate | N/A | Фича не затрагивает генерацию заданий. Только форма награды. |
| IV. Экономическая обоснованность | ✅ | Курс `rate_points_per_rub` — калибровочный параметр для маржи. Хранится в singleton `points_settings`. Для юнит-экономики: при курсе 10:1 задание с `reward_rub=50` даёт 50 баллов = максимум 5 руб экономии — «дороговизна» баллов настраивается. |
| V. Privacy by Design | ✅ | Не добавляет ПД. Баллы привязаны к `loyalty_card_id` (существующая анонимная идентификация). |
| Backend RSI | ✅ | Новые слои: `crud/points.py`, `services/points.py`, `routes/points.py`, `schemas/points.py`. Модели — `entities/points.py`. Composition — `core/points.py`. |
| Backend DI | ✅ | `PointsService` получает `PointsRepository` через конструктор; wiring — в `core/points.py`. Никаких side-effects на импорте. |
| Backend Poetry | ✅ | Новых зависимостей не требуется. Все возможности — на существующем стеке. |
| Backend structlog | ✅ | Логирование в `points_service` — через `structlog.get_logger("points")`. |
| Mobile: Expo v57, TypeScript | ✅ | Экран `x5mobile/src/app/(app)/points.tsx`; хук `x5mobile/src/hooks/usePoints.ts`. Без нативных зависимостей. Функциональные компоненты, `StyleSheet.create`. |

**Итог**: гейт пройден. Complexity Tracking — пустой.

### Post-design re-check

После Phase 1 (data-model, contracts, quickstart) конституционный гейт **пройден повторно без изменений**:

- Дизайн подтвердил integer-only арифметику (принцип IV — экономическая обоснованность: калибровка курса без float-багов).
- Новые эндпоинты `/points/*` — 2 действия от главного (принцип II).
- Расчёт cashback вынесен в чистую функцию `points_applier.apply_cashback` (соответствует Backend RSI + testability).
- Ни один принцип не нарушен, complexity tracking остаётся пустым.

## Project Structure

### Documentation (this feature)

```text
specs/007-cashback-points/
├── plan.md              # This file (/speckit-plan output)
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output — OpenAPI-фрагменты
│   ├── points_api.yaml
│   └── receipts_delta.yaml
├── checklists/
│   └── requirements.md  # Уже создан на этапе /speckit-specify
└── tasks.md             # Будет создан /speckit-tasks
```

### Source Code (repository root)

Проект уже существует. Изменения — точечные, в существующей структуре `web/src/webx5/` (backend) и `x5mobile/src/` (mobile). Только новые/затрагиваемые файлы:

```text
web/
├── alembic/versions/
│   └── g5b6c7d8e9f0_add_points_tables.py       # NEW — миграция: 3 таблицы + 3 колонки receipts
├── src/webx5/
│   ├── entities/
│   │   ├── points.py                            # NEW — PointsAccount, PointsTransaction, PointsSettings
│   │   └── receipt.py                           # MOD — 3 новых поля
│   ├── crud/
│   │   ├── points.py                            # NEW — PointsRepository (CRUD + row-lock)
│   │   └── task.py                              # MOD — вместо create_reward_discount → award_points
│   ├── services/
│   │   ├── points.py                            # NEW — PointsService (award, spend, get_balance, get_rate, set_rate)
│   │   ├── receipt.py                           # MOD — списание баллов при create_receipt
│   │   ├── task_completion.py                   # MOD — вызов award_points вместо create_reward_discount
│   │   └── points_applier.py                    # NEW — чистая функция расчёта cashback для /calculate
│   ├── schemas/
│   │   ├── points.py                            # NEW — Pydantic (BalanceResponse, TransactionOut, RateOut, RateUpdate)
│   │   └── receipt.py                           # MOD — CalculateRequest/Response, ReceiptCreate/Response
│   ├── routes/
│   │   ├── points.py                            # NEW — /points/balance, /points/transactions, /points/settings/rate
│   │   └── receipts.py                          # MOD — принимает points_to_spend
│   ├── core/
│   │   ├── points.py                            # NEW — wiring PointsRepository + PointsService
│   │   └── server.py                            # MOD — include points_router
│   └── utils/                                   # без изменений
└── tests/webx5/
    ├── services/
    │   ├── test_points.py                       # NEW — unit-тесты award/spend/rate/idempotency
    │   ├── test_points_applier.py               # NEW — unit-тесты calculate-логики
    │   ├── test_receipt_with_points.py          # NEW — integration: чек с кешбеком
    │   └── test_task_completion_awards_points.py # NEW — замена discount-теста
    └── routes/
        ├── test_points_routes.py                # NEW
        └── test_receipts_with_points.py         # NEW

x5mobile/
└── src/
    ├── app/(app)/
    │   └── points.tsx                            # NEW — экран баланса + история
    └── hooks/
        └── usePoints.ts                          # NEW — фетчинг balance + transactions
```

**Structure Decision**: Проект — существующий web-service + mobile-app. Все изменения ложатся в текущие пакеты `web/src/webx5/` (следуя RSI-раскладке: entities → crud → services → routes → core) и `x5mobile/src/` (экран + хук). Никаких новых пакетов/сервисов не создаётся.

## Complexity Tracking

*Constitution Check прошёл без нарушений. Раздел пуст.*
