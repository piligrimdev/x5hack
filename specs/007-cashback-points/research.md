# Research: Кешбек в баллах

**Feature**: 007-cashback-points
**Phase**: 0 (Outline & Research)
**Date**: 2026-09-04

Все критичные развилки — с решениями. Каждая запись: **Decision → Rationale → Alternatives considered**.

---

## R1. Начисление: as-is vs через курс

**Decision**: При закрытии задания начисляется `points = int(task.reward_rub)`. Курс `rate_points_per_rub` при начислении НЕ применяется.

**Rationale**:
- Уточнение пользователя (2026-09-04): «reward начисляет баллы as is».
- Семантика прозрачна для пользователя: «за задание с наградой 50 руб получаю 50 баллов». Позже курс превращает эти 50 баллов в 5 руб экономии — это отдельная механика калибровки.
- Начисление не зависит от курса → история начислений стабильна при перекалибровке курса; не нужно хранить `rate_at_time` для earn-транзакций.

**Alternatives considered**:
- Начисление по курсу (`points = int(reward_rub × rate)`) — было в v1 спеки; отклонено, т.к. это делает "цену" балла сразу заложенной в начисление, что усложняет ре-калибровку экономики: изменение курса моментально обесценивает все прошлые награды.
- Хранить награду сразу в баллах в `task.reward_points` — потребует правки `synth/challenges.py` (запрещено FR-026); отклонено.

**Открытый пункт**: `task.reward_rub` — Decimal(10,2). Дробная часть теряется при `int()`. В PoC LLM возвращает суммы кратные рублю; assumption валидируется отдельным тестом на пуле.

---

## R2. Курс списания: rate на момент /calculate или на момент /receipts

**Decision**: Курс применяется в момент финального POST /receipts. `POST /receipts/calculate` — только показывает предполагаемый результат при текущем курсе; при разрыве курса между шагами кассир увидит обновлённые цифры на этапе receipt (или получит 200 с фактически применённым — не 422).

**Rationale**:
- `POST /receipts/calculate` в текущей схеме (спека 005) — уже read-only preview; списание идёт в `POST /receipts`.
- Курс меняется редко (админ-действие через `PUT /points/settings/rate`); коллизия calc/receipt возможна только при live-перекалибровке — крайний edge case для PoC.
- Хранение `points_rate_at_purchase` в чеке даёт аудит: по чеку всегда можно восстановить, какой курс применялся.

**Alternatives considered**:
- Замораживать курс на момент /calculate (передавать в /receipts и валидировать) — усложняет протокол, требует новых полей в запросе. Отклонено ради простоты.
- Явный 422 при расхождении расчётного и фактического кешбека — плохой UX (кассир должен переспросить пользователя); отклонено.

---

## R3. Хранение баланса: denorm vs полностью derived from transactions

**Decision**: Баланс хранится denorm в `points_account.balance INT NOT NULL CHECK (balance >= 0)`. История — отдельная таблица `points_transaction`. Инвариант «balance = sum(amount) для аккаунта» поддерживается сервисом; sanity-check — отдельный скрипт (BACKLOG).

**Rationale**:
- Прямой доступ к балансу за O(1) → SC-006 (300 мс p95 для GET /points/balance) достижим тривиально.
- DB-constraint `CHECK (balance >= 0)` предотвращает уход в минус независимо от логики приложения.
- Для списания нужен per-user row-lock, который проще брать на `points_account`-строку (одна строка на пользователя), чем на таблицу транзакций.

**Alternatives considered**:
- Только транзакции (без denorm baseline): `balance = sum(amount)`; на N=100k транзакций уже медленно, требует индекса + суммирования. Отклонено.
- Materialized view: избыточно для PoC.

---

## R4. Атомарность и конкурентное списание (per-user row-lock)

**Decision**: В `PointsService.spend(session, loyalty_card_id, points_requested, receipt_subtotal_rub, rate)` перед списанием берётся `SELECT ... FROM points_account WHERE loyalty_card_id = :uid FOR UPDATE`. Всё списание + запись `receipt` + запись `points_transaction(type='spend')` — в одной SQL-транзакции сервиса.

**Rationale**:
- Симметрично FR-014 спеки 006 (row-lock на `users` для сериализации обработки чеков одного пользователя).
- PostgreSQL `FOR UPDATE` — proven, простой примитив; без deadlock-риска, т.к. lock всегда берётся первым и всегда одинокий (один аккаунт на транзакцию).
- Уникальный индекс `(type='earn', related_task_id)` в `points_transaction` — вторая линия защиты от двойного начисления (Task retry).

**Alternatives considered**:
- Optimistic concurrency (version column): проще для PoC, но требует retry-loop в сервисе; отклонено — pessimistic проще и достаточен для нагрузки хакатона.
- Advisory locks: избыточно.

---

## R5. Что делать со старой веткой создания Discount как награды

**Decision**: `TaskRepository.create_reward_discount` **удаляется** (не оставляется как fallback). `services/task_completion.py::apply_receipt` вызывает вместо него `points_service.award_for_task(session, task)`. `Task.reward_id` / `Task.reward_type` **остаются в схеме** для обратной совместимости (существуют миграции + записи), но новые задачи их не заполняют (`reward_id=NULL`, `reward_type='discount'` по default'у остаётся, но потеряет смысл; переосмысление — BACKLOG).

**Rationale**:
- Clean cutover (FR-027) — двойная семантика («иногда Discount, иногда баллы») запутывает и тестируется хуже, чем одна ветка.
- Удаление колонок в отдельной BACKLOG-миграции — не блокирует эту фичу.
- Существующие Discount-записи, созданные до релиза, продолжают работать (спека 005 их читает без изменений).

**Alternatives considered**:
- Feature-flag «награда = discount | points»: избыточно для PoC.
- Одновременное создание и Discount, и баллов: двойная награда — противоречит юнит-экономике (принцип IV).

---

## R6. Курс: singleton row vs env variable

**Decision**: `points_settings` — таблица с ровно одной строкой (singleton, PK fixed `id=1`). Изменяется через `PUT /points/settings/rate` с `X-Terminal-Token`. Значение при инициализации: 10.

**Rationale**:
- Требование FR-023: «в настройках я могу указать курс» — предполагает live-редактируемость без перезапуска сервиса.
- Env-var требовал бы перезапуска контейнера — плохой UX для админа.
- Singleton проще, чем полноценная система настроек — достаточно для PoC.

**Alternatives considered**:
- Полноценный settings-service с key-value: избыточно.
- Хранение в Redis: добавляет зависимость без выгоды.

---

## R7. Округление при списании

**Decision**: `applied_points = min(points_requested, balance, subtotal_rub × rate)`; далее `applied_points = (applied_points // rate) × rate` (округление вниз до кратного `rate`); `cashback_rub = applied_points // rate` (integer division). Все — целые.

**Rationale**:
- Целочисленная арифметика для денег → без float-ошибок.
- «Списать 105 баллов при курсе 10:1» → реально списывается 100 = 10 руб экономии. Лишние 5 баллов остаются на счёте — пользователь понимает: «баллы кратно курсу».
- Явное поле `points_to_apply` в ответе — кассир видит фактическое списание перед подтверждением.

**Alternatives considered**:
- Округление вверх («получить лишнюю копейку»): в пользу пользователя, но нарушает инвариант `cashback_rub = points / rate`; отклонено.
- Дробные баллы: усложняет UX и БД (Decimal); отклонено.

---

## R8. Как считать `balance_rub_equivalent` в GET /points/balance

**Decision**: `balance_rub_equivalent = balance // rate_points_per_rub` (по текущему курсу, integer floor).

**Rationale**:
- Отображение баланса «сколько это в рублях» — справочное; берётся текущий курс, а не курс на момент начислений (по R1 у earn нет `rate_at_time`).
- Пользователь видит «490 баллов ≈ 49 руб» при курсе 10:1 → интуитивно.

**Alternatives considered**:
- Отображать курс отдельно, конверсию не делать: пользователю пришлось бы считать вручную; отклонено.

---

## R9. Интеграция с существующим `services/discount_calculator.py`

**Decision**: Кешбек не влияет на выбор скидок для позиций. `discount_calculator` работает как раньше. Расчёт `cashback` — отдельная чистая функция `services/points_applier.py::apply_cashback(subtotal_rub_after_discounts, points_requested, balance, rate) -> CashbackResult(applied_points, cashback_rub)`. Роут `/receipts/calculate` вызывает discount_calculator, суммирует, потом вызывает points_applier.

**Rationale**:
- Кешбек — на весь чек, не на позиции (FR-013 + user requirement). Разделение отвечает Single Responsibility.
- Чистая функция — легко unit-тестировать.

**Alternatives considered**:
- Встраивать cashback в discount_calculator: нарушает SRP; discount применяется к позициям, cashback — к итогу; отклонено.

---

## R10. Идемпотентность начисления баллов

**Decision**: Уникальный частичный индекс `UNIQUE (related_task_id) WHERE type = 'earn'` на `points_transaction`. Попытка повторной вставки → `IntegrityError` → сервис откатывает и возвращает уже существующую транзакцию (или просто игнорирует).

**Rationale**:
- Одно задание = максимум один earn. Retry воркера безопасен.
- Частичный индекс не мешает spend-транзакциям (у них `related_task_id IS NULL`).

**Alternatives considered**:
- Проверять существование транзакции перед вставкой (SELECT + INSERT): race condition возможен без транзакции с уровнем SERIALIZABLE; отклонено.
- Отдельная дедупликационная таблица (как `task_receipt_increment`): избыточно, если можно ограничиться индексом.

---

## R11. Мобильный экран баланса

**Decision**: `x5mobile/src/app/(app)/points.tsx` — экран со стандартным `Stack` layout, показывает `balance`, `rate_points_per_rub`, `balance_rub_equivalent` и последние 20 транзакций. Хук `usePoints.ts` — REST-запросы + локальное кэширование (SWR/react-query — на выбор; в PoC можно `useState + useEffect` + вручную refresh).

**Rationale**:
- Экран доступен ≤2 действия (Tab → «Мои баллы») — принцип II.
- Без нативных зависимостей; следует существующему паттерну `x5mobile/src/hooks/*` (бизнес-логика в хуках).

**Alternatives considered**:
- Пуш-уведомления о начислении баллов: BACKLOG (пуши в PoC вне scope, ARCHITECTURE.md).
- Интегрировать баланс в главный экран (дашборд): пока держим отдельно, чтобы не перегружать главный.

---

## R12. Расширение схемы receipts

**Decision**: В таблицу `receipts` добавляются три колонки:
- `cashback_applied_points INT NOT NULL DEFAULT 0 CHECK (cashback_applied_points >= 0)`
- `cashback_applied_rub INT NOT NULL DEFAULT 0 CHECK (cashback_applied_rub >= 0)` (целое, а не Decimal — списание кратно рублю)
- `points_rate_at_purchase INT NULL` (NULL для чеков без списания)

Существующие поля `receipt.*` и `receipt_item.*` не трогаются.

**Rationale**:
- Соответствие FR-025 (не переименовывать существующие поля).
- Наличие `points_rate_at_purchase` — для аудита + воспроизводимости расчётов.

**Alternatives considered**:
- Хранить cashback только в `points_transaction`, а в receipt агрегировать при чтении: увеличивает latency GET /receipts (JOIN); отклонено.
- Cashback как отдельная ReceiptDiscount-запись: перегружает discount-модель; отклонено.

---

## Summary of Decisions

| # | Decision |
|---|---|
| R1 | Начисление as-is: `points = int(reward_rub)`, курс не применяется |
| R2 | Курс списания = на момент POST /receipts (не на момент /calculate) |
| R3 | Баланс — denorm INT в `points_account` + DB constraint `>= 0` |
| R4 | Per-user row-lock `SELECT ... FROM points_account FOR UPDATE` |
| R5 | `create_reward_discount` удаляется; ветка Discount как награды — clean cutover |
| R6 | Курс — singleton row в `points_settings`, редактируется через API + `X-Terminal-Token` |
| R7 | Списание округляется вниз до кратного `rate`; всё — integer |
| R8 | `balance_rub_equivalent = balance // rate` (текущий курс) |
| R9 | `points_applier.py` — отдельно от `discount_calculator.py` |
| R10 | Идемпотентность earn — частичный уникальный индекс `(related_task_id) WHERE type='earn'` |
| R11 | Мобильный экран `points.tsx` + хук `usePoints.ts`; без нативных зависимостей |
| R12 | `receipts` расширяется 3 колонками (int + int + int null) |

Все `NEEDS CLARIFICATION` в Technical Context — разрешены. Фаза 0 закрыта.
