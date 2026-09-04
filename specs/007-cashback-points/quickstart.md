# Quickstart: Кешбек в баллах

**Feature**: 007-cashback-points
**Phase**: 1 (Design & Contracts)

Валидационный сценарий end-to-end. Используется вручную (или через bash-скрипт) для приёмки. Все шаги — на существующем docker-compose стенде.

## Prerequisites

- Docker Compose стенд поднят: `docker compose up -d` (в корне репозитория).
- Миграции применены (включая новую `g5b6c7d8e9f0_add_points_tables`).
- Сиды выполнены в порядке: `seed_products` → `seed_stores` → `seed_discounts` → `seed_receipts`.
- Переменные окружения:
  - `TERMINAL_TOKEN=<секрет из .env>` — для кассовых запросов.
  - `API_BASE=http://localhost:8000` — базовый URL.

Все ссылки на форматы запросов/ответов — [contracts/points_api.yaml](./contracts/points_api.yaml) и [contracts/receipts_delta.yaml](./contracts/receipts_delta.yaml).

## Scenario 1 — Начисление баллов за задание (US1)

**Цель**: убедиться, что при закрытии задания баллы начисляются as-is (`int(reward_rub)`), курс не применяется.

1. Зарегистрировать нового пользователя (`POST /register`) → получить JWT + `loyalty_card_id`.
2. Отправить синтетический чек (`POST /receipts` с `X-Terminal-Token`), в котором есть 1 позиция → запускается фоновая генерация 3 заданий (спека 006).
3. Дождаться (≤30 сек), пока задания появятся: `GET /challenges/current` с JWT → 3 задания.
4. Взять задание с `reward_rub=50` (или любое); отправить чек, закрывающий его критерии.
5. Дождаться фоновой обработки (≤30 сек).
6. `GET /points/balance` с JWT.

**Expected**: `balance = 50` (независимо от текущего `rate_points_per_rub`), `rate_points_per_rub = 10` (default), `balance_rub_equivalent = 5`.

7. `GET /points/transactions` → 1 запись с `type='earn'`, `amount=50`, `related_task_id=<id закрытого>`, `rate_at_time=null`.

## Scenario 2 — Списание баллов при оплате (US2)

**Цель**: убедиться, что списание идёт по курсу, атомарно с чеком, баланс не уходит в минус.

Предусловие: пользователь из Scenario 1 с балансом 50 баллов.

1. Сформировать корзину с товарами на общую сумму ~50 руб (после скидок).
2. `POST /receipts/calculate` с `points_to_spend="all"` и `loyalty_card_id=<user>`.
   **Expected** (см. `CalculateResponseExtended`):
   - `cashback.points_available=50`,
   - `cashback.points_to_apply=50` (потолок = min(50, balance=50, 50×10=500)),
   - `cashback.cashback_rub=5`,
   - `cashback.total_paid_rub = subtotal_rub - 5`,
   - `cashback.points_balance_after=0`,
   - `cashback.points_capped_by='balance'` (был бы «receipt_total» если корзина < 5 руб).
3. `POST /receipts` с тем же `points_to_spend`, `X-Idempotency-Key: <новый UUID>`.
   **Expected**: 201 Created; в ответе `cashback_applied_points=50`, `cashback_applied_rub=5`, `points_rate_at_purchase=10`.
4. `GET /points/balance` → `balance=0`.
5. `GET /points/transactions` → добавилась запись `type='spend'`, `amount=-50`, `rate_at_time=10`, `related_receipt_id=<чек>`.

## Scenario 3 — Изменение курса (US6)

**Цель**: убедиться, что курс сохраняется и сразу применяется.

1. `GET /points/settings/rate` → `{rate_points_per_rub: 10}` (публичный).
2. `PUT /points/settings/rate` с `X-Terminal-Token`, тело `{"rate_points_per_rub": 20}` → 200, ответ содержит новый курс.
3. `PUT /points/settings/rate` **без** `X-Terminal-Token` → 401.
4. `PUT /points/settings/rate` с телом `{"rate_points_per_rub": 0}` → 422.

Проверка после изменения курса:
5. Пользователю с балансом 100 (закрыть ещё одно задание для тестового баланса): `GET /points/balance` → `balance=100`, `rate=20`, `balance_rub_equivalent=5` (100//20).
6. Списать баллы: 100 баллов = 5 руб при курсе 20:1.

## Scenario 4 — Идемпотентность начисления (SC-009)

**Цель**: убедиться, что 100 попыток закрыть одно задание создают 1 транзакцию.

1. Взять открытое задание; закрыть его (см. Scenario 1).
2. Запустить celery-таск обработки того же чека повторно 100 раз (`celery call apply_receipt <receipt_id>`).
3. `GET /points/transactions` → **ровно 1** запись `earn` для этого задания.
4. Баланс не изменился между 1-й и 100-й попыткой.

## Scenario 5 — Race condition при списании (SC-003)

**Цель**: убедиться, что баланс не уходит в минус при 100 параллельных списаниях.

Автоматизированный тест `tests/webx5/services/test_points.py::test_concurrent_spend_no_negative_balance`:

1. Создать аккаунт с `balance=1000`.
2. Запустить 100 потоков, каждый пытается списать 100 баллов через `PointsService.spend`.
3. Проверить: суммарно списано ровно 1000, balance = 0, ни одной ошибки, всего 10 успешных транзакций spend + 90 транзакций с `applied_points=0`.

## Scenario 6 — Экономия включает кешбек (US5)

**Цель**: убедиться, что `GET /receipts/economy` учитывает cashback.

1. У пользователя 2 чека:
   - Чек A: `sum(discounted_amount) = 100`, `cashback_applied_rub = 0`.
   - Чек B: `sum(discounted_amount) = 50`, `cashback_applied_rub = 30`.
2. `GET /receipts/economy` (существующий эндпоинт).

**Expected**: `total_saved = 100 + (50 + 30) = 180` руб.

## Scenario 7 — Мобильный экран баланса (US4, US6)

**Цель**: убедиться, что экран доступен ≤2 действия и показывает корректные данные.

1. Открыть мобильное приложение → главный экран.
2. Тап на таб «Мои баллы» (2-е действие: главный экран → таб).
3. Экран показывает: текущий баланс, курс, эквивалент в рублях, список последних 20 транзакций.
4. Pull-to-refresh → перезапрос `/points/balance` + `/points/transactions`.

## Post-conditions / Cleanup

- Для регресс-тестов: очистить тестовый аккаунт через `DELETE` в БД (в PoC — вручную; API для очистки не предусмотрен).
- Курс вернуть к дефолту (`PUT /points/settings/rate` с `{"rate_points_per_rub": 10}`).

## Traceability

| Scenario | User Stories | FRs | SCs |
|---|---|---|---|
| 1 | US1 | FR-001…FR-004 | SC-001, SC-009 |
| 2 | US2, US3 | FR-005…FR-011, FR-014…FR-017 | SC-002, SC-004, SC-005 |
| 3 | US6 | FR-021…FR-024 | SC-007 |
| 4 | US1 | FR-003 | SC-009 |
| 5 | US2 | FR-009, FR-010 | SC-003 |
| 6 | US5 | FR-013 | SC-008 |
| 7 | US4, US6 | FR-018…FR-020 | SC-006, SC-008 |
