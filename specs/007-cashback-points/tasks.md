# Tasks: Кешбек в баллах вместо скидочной награды за задания

**Input**: Design documents from `/specs/007-cashback-points/`

**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/ ✅, quickstart.md ✅

**Tests**: включены как unit + integration покрытие ключевых инвариантов (SC-002, SC-003, SC-005, SC-007, SC-009). Не TDD-строгий флоу — тесты пишутся вместе с реализацией внутри той же user story. Тесты, отмеченные ⚠️, критичны для приёмки (нагрузка/идемпотентность/атомарность) — их пропускать нельзя.

**Организация**: Задачи сгруппированы по user story из [spec.md](./spec.md). US1–US3 — MVP (все P1). US4–US6 — P2 (полный релиз).

## Формат

`- [ ] TXXX [P?] [USn?] Описание с абсолютным путём файла`

- `[P]` — можно выполнять параллельно (независимые файлы).
- `[USn]` — маркер user story (только для фаз US1…US6).
- Пути даны относительно корня репозитория `/Users/pgdev/x5hack/`.

## Path Conventions

- **Backend**: `web/src/webx5/{entities,crud,services,routes,schemas,core}/`, миграции — `web/alembic/versions/`.
- **Backend tests**: `web/tests/webx5/{services,routes}/`.
- **Mobile**: `x5mobile/src/{app,hooks,components}/`.
- **Форматтер/линтер** запускается через `lint-format` subagent (правило из `.claude/rules/scripts-and-services.md`).

---

## Phase 1: Setup (Shared Infrastructure)

**Цель**: минимальные шаги перед началом. Проект уже существует (`web/`, `x5mobile/`), стенд `docker compose` работает.

- [X] T001 Убедиться, что стенд `docker compose up -d` поднимает `postgres`, `web`, `celery-worker` без ошибок; локальная БД доступна на порту из `.env`.
- [X] T002 [P] Проверить, что все существующие миграции применяются: `docker compose exec web poetry run alembic upgrade head`. Актуальный head — `f4a5b6c7d8ea_add_task_challenge_slot`.
- [X] T003 [P] Создать пустой файл ветки миграции-заглушки `web/alembic/versions/g5b6c7d8e9f0_add_points_tables.py` со `down_revision = "f4a5b6c7d8ea"`; тело — заполнится в T007.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Цель**: схема БД + модели + базовый доступ к настройкам курса. Всё, что нужно ДО реализации любой user story.

**⚠️ CRITICAL**: без завершения этой фазы ни одна US не стартует.

### Схема и миграции

- [X] T004 Создать сущности `PointsAccount`, `PointsTransaction`, `PointsSettings` (SQLAlchemy models, integer только) в `web/src/webx5/entities/points.py`. Constraints, индексы и частичный UNIQUE — согласно [data-model.md](./data-model.md).
- [X] T005 [P] Расширить `web/src/webx5/entities/receipt.py`: добавить в `Receipt` три колонки — `cashback_applied_points INT NOT NULL DEFAULT 0 CHECK >= 0`, `cashback_applied_rub INT NOT NULL DEFAULT 0 CHECK >= 0`, `points_rate_at_purchase INT NULL`.
- [X] T006 [P] Зарегистрировать импорт `webx5.entities.points` в `web/src/webx5/entities/__init__.py` (или в `base.py`, где сейчас регистрируются модели), чтобы Alembic видел таблицы через `Base.metadata`.
- [X] T007 Заполнить миграцию `web/alembic/versions/g5b6c7d8e9f0_add_points_tables.py`: (1) три таблицы, (2) один INSERT в `points_settings (1, 10, now())`, (3) три колонки в `receipts` с default, (4) частичный UNIQUE-индекс `ux_points_tx_earn_task ON points_transaction (related_task_id) WHERE type='earn'`, (5) индекс `(points_account_id, created_at DESC)`. Downgrade — reverse-order DROP.
- [X] T008 Прогнать миграцию локально: `docker compose exec web poetry run alembic upgrade head` → таблицы созданы, singleton-row вставлен, existing `receipts.*` не тронуты.

### Repository и wiring

- [X] T009 Создать `web/src/webx5/crud/points.py` с `PointsRepository`:
  - `get_or_create_account(session, loyalty_card_id) -> PointsAccount` (лениво, race-safe через ON CONFLICT DO NOTHING + повторный SELECT);
  - `lock_account_for_update(session, loyalty_card_id) -> PointsAccount` (`SELECT ... FOR UPDATE`);
  - `insert_earn(session, account_id, task_id, amount) -> PointsTransaction | None` (возвращает None при `IntegrityError` от частичного UNIQUE);
  - `insert_spend(session, account_id, receipt_id, amount, rate) -> PointsTransaction`;
  - `bump_balance(session, account, delta)` (для earn) и `deduct_balance(session, account, points)` (для spend);
  - `list_transactions(session, account_id, limit, offset) -> list[PointsTransaction]`, `count_transactions(session, account_id) -> int`;
  - `get_rate(session) -> int`, `set_rate(session, new_rate: int) -> int`.
- [X] T010 [P] Создать `web/src/webx5/schemas/points.py`: Pydantic-схемы `BalanceResponse`, `TransactionOut`, `TransactionsPage`, `RateResponse`, `RateUpdate` — согласно `contracts/points_api.yaml`.
- [X] T011 Создать `web/src/webx5/core/points.py`: composition root — `points_repo = PointsRepository()`, `points_service = PointsService(points_repo)`. Импортится из `routes/points.py` и `services/task_completion.py`, `services/receipt.py`.

**Checkpoint**: Foundation готова. Таблицы созданы, singleton курса = 10, репозиторий доступен. Можно параллельно стартовать US1, US2, US3.

---

## Phase 3: User Story 1 — Начисление баллов за выполненное задание (Priority: P1) 🎯 MVP

**Goal**: при переходе задания в «выполнено» начисляется `int(reward_rub)` баллов; курс не применяется; идемпотентно.

**Independent Test** (см. quickstart Scenario 1): задание с `reward_rub=50` закрывается → `balance += 50`, одна `earn`-транзакция с `rate_at_time=NULL`, повторные попытки обработать тот же task не удваивают.

- [X] T012 [US1] Создать `web/src/webx5/services/points.py` со скелетом `PointsService(repo: PointsRepository)`. Добавить метод `award_for_task(session, task) -> int` — возвращает начисленное количество баллов (0 если уже был начислён).
- [X] T013 [US1] Реализовать `PointsService.award_for_task` в `web/src/webx5/services/points.py`: (1) `points = int(task.reward_rub)`; если 0 — no-op, return 0; (2) `account = repo.get_or_create_account(...)`; (3) `tx = repo.insert_earn(session, account.id, task.id, points)`; (4) если `tx is None` — уже начислено, return 0; (5) `repo.bump_balance(session, account, points)`; (6) `structlog.info("points.awarded", ...)`; (7) return points. Всё — в текущей SQL-транзакции (сервис не коммитит).
- [X] T014 [US1] Изменить `web/src/webx5/services/task_completion.py:150-152`: заменить вызов `self.task_repo.create_reward_discount(...)` + `self.task_repo.mark_completed(session, task, reward.id)` на `awarded = points_service.award_for_task(session, task)` + `self.task_repo.mark_completed_without_reward(session, task)`. Импорт `points_service` — из `webx5.core.points` (внутри функции, чтобы не ломать unit-тесты уровня модуля).
- [X] T015 [US1] В `web/src/webx5/crud/task.py`: добавить `mark_completed_without_reward(self, session, task) -> Task` (без `reward_id`, без `Discount`); удалить/пометить `create_reward_discount` как unused (пометка через `# BACKLOG-cleanup`, чтобы не ломать существующие импорты сразу). Удалить импорт `Discount`/`DiscountType`/`DiscountLinkType`/`timedelta`, если больше не используется.
- [X] T016 [P] [US1] Unit-тест `web/tests/webx5/services/test_points_award.py`: happy-path award (reward_rub=50 → balance +50, earn-tx rate_at_time=None); reward_rub=0 → no-op; повторный вызов → +0 (идемпотентность).
- [X] T017 [P] [US1] ⚠️ Integration-тест `web/tests/webx5/services/test_task_completion_awards_points.py` (SC-009): создать task с criterion product=X, quantity_target=2; отправить чек с 2×X; вызвать `TaskCompletionService.apply_receipt` 100 раз параллельно (threads на in-memory session pool) → одна `earn`-tx, `points_account.balance` увеличился ровно на `int(reward_rub)`, task в статусе «выполнено».

**Checkpoint**: US1 закрыта. `POST /receipts` → фоновая обработка → задание закрывается с баллами. Discount-награда больше не создаётся новыми задачами.

---

## Phase 4: User Story 2 — Списание баллов при фиксации чека (Priority: P1)

**Goal**: `POST /receipts` принимает `points_to_spend`, атомарно списывает баллы и создаёт чек с полями `cashback_applied_*`.

**Independent Test** (quickstart Scenario 2): пользователь с balance=50, курс 10:1, `points_to_spend="all"` → чек `cashback_applied_points=50`, `cashback_applied_rub=5`, balance=0, одна `spend`-tx.

### Общая функция apply_cashback (используется и US2, и US3)

- [X] T018 [US2] Создать `web/src/webx5/services/points_applier.py` с чистой функцией:
  ```
  @dataclass
  class CashbackResult:
      applied_points: int; cashback_rub: int; capped_by: Literal["none","balance","receipt_total"]
  def apply_cashback(subtotal_rub: int, points_requested: int, balance: int, rate: int) -> CashbackResult
  ```
  Логика: `raw = min(points_requested, balance, subtotal_rub * rate)`; `applied = (raw // rate) * rate`; `cashback_rub = applied // rate`; `capped_by` — из того, какой из трёх min победил. Никаких SQL, никаких сайд-эффектов.
- [X] T019 [P] [US2] Хелпер парсинга `points_to_spend` в `web/src/webx5/services/points_applier.py`: `resolve_points_to_spend(raw: int | str | None, balance: int) -> int` — `None|0 → 0`, `"all" → balance`, `int ≥ 0 → сам int`; всё остальное — ValueError.
- [X] T020 [P] [US2] Unit-тест `web/tests/webx5/services/test_points_applier.py`: покрывает 6 случаев из quickstart Scenario 2 + edge cases (raw кратен rate, не кратен, balance=0, subtotal=0, `points_requested=0`).

### Списание в PointsService

- [X] T021 [US2] Добавить в `web/src/webx5/services/points.py` метод `spend_for_receipt(session, loyalty_card_id, points_requested, receipt_subtotal_rub, receipt_id) -> tuple[int, int, int]` (returns `applied_points, cashback_rub, rate_used`). Порядок: (1) `rate = repo.get_rate(session)`; (2) `account = repo.lock_account_for_update(session, loyalty_card_id)`; (3) вызвать `apply_cashback(...)`; (4) если `applied_points == 0` — return `(0, 0, rate)` без insert; (5) `repo.deduct_balance(session, account, applied_points)`; (6) `repo.insert_spend(session, account.id, receipt_id, -applied_points, rate)`; (7) `structlog.info(...)`; (8) return tuple.

### Интеграция с POST /receipts

- [X] T022 [US2] Расширить `web/src/webx5/schemas/receipt.py`: в `ReceiptCreate` добавить `points_to_spend: int | Literal["all"] | None = None`; в `ReceiptResponse` — `cashback_applied_points: int = 0`, `cashback_applied_rub: int = 0`, `points_rate_at_purchase: int | None = None`.
- [X] T023 [US2] Изменить `web/src/webx5/services/receipt.py`: `create_receipt(...)` — после сохранения `receipt` и позиций (в той же транзакции): (1) если `data.loyalty_card_id is None` и `points_to_spend` в теле > 0 → raise HTTPException 422 «баллами можно оплачивать только по карте лояльности»; (2) вычислить `subtotal_rub = int(sum(paid_price × quantity))`; (3) вызвать `points_service.spend_for_receipt(...)`; (4) записать в `receipt.cashback_applied_points/rub/points_rate_at_purchase`; (5) убедиться, что row-lock на points_account берётся ДО row-lock на users (симметрично FR-014 спеки 006).
- [X] T024 [US2] Обновить `web/src/webx5/routes/receipts.py` (функция `create_receipt`): передать `data.points_to_spend` в сервис; в `ReceiptResponse` заполнить три новых поля из `receipt`.
- [X] T025 [P] [US2] ⚠️ Integration-тест `web/tests/webx5/routes/test_receipts_with_points.py` (SC-002, SC-005): (1) balance=50, points_to_spend="all", subtotal=200 → чек с cashback=5 руб, balance=0; (2) balance=100, points_to_spend=5000, subtotal=500 → capped by receipt_total, applied=5000, cashback=500, balance=95; (3) balance=0 или без loyalty_card_id + points_to_spend>0 → 422; (4) idempotency: тот же X-Idempotency-Key → баланс не списан второй раз.
- [X] T026 [P] [US2] ⚠️ Integration-тест `web/tests/webx5/services/test_points_concurrent_spend.py` (SC-003): создать аккаунт с balance=1000; запустить 100 потоков, каждый спендит 100 баллов через `PointsService.spend_for_receipt`; проверить `balance=0`, sum(spend-tx.amount) = -1000, ни одна tx не привела к отрицательному балансу (перехватить IntegrityError, если случится).

**Checkpoint**: US2 закрыта. Кассир может передать `points_to_spend`, баллы списываются атомарно, инвариант balance>=0 держится под нагрузкой.

---

## Phase 5: User Story 3 — Предварительный расчёт с учётом кешбека (Priority: P1)

**Goal**: `POST /receipts/calculate` возвращает блок `cashback` с прогнозом списания. Read-only, не меняет счёт.

**Independent Test** (quickstart Scenario 2 шаг 2): balance=50, subtotal=50 руб → response.cashback: `points_to_apply=50, cashback_rub=5, total_paid_rub=45, points_balance_after=0`.

- [X] T027 [US3] Расширить `web/src/webx5/schemas/receipt.py`: в `CalculateRequest` добавить `points_to_spend: int | Literal["all"] | None = None`; в `CalculateResponse` — `cashback: CashbackBlock | None = None`, где `CashbackBlock` содержит `points_available, points_to_apply, cashback_rub, total_paid_rub, points_balance_after, points_capped_by, rate_points_per_rub` (все int, capped_by — enum как в контракте).
- [X] T028 [US3] Добавить в `web/src/webx5/services/points.py` метод `preview_for_calculate(session, loyalty_card_id, points_requested_raw, subtotal_rub) -> CashbackPreview | None`. Возвращает None для `loyalty_card_id is None`. Внутри: `rate = repo.get_rate(session)`; `account = repo.get_or_create_account(session, loyalty_card_id)`; НЕТ FOR UPDATE (read-only); `resolved = resolve_points_to_spend(points_requested_raw, account.balance)`; `result = apply_cashback(subtotal_rub, resolved, account.balance, rate)`; вернуть Preview со всеми полями схемы.
- [X] T029 [US3] Изменить `web/src/webx5/routes/receipts.py` (функция `calculate_discounts`): после вычисления `total_paid = sum(paid_price × qty)` — вызвать `points_service.preview_for_calculate(session, data.loyalty_card_id, data.points_to_spend, int(total_paid))`; заполнить `CalculateResponse.cashback` полученным блоком.
- [X] T030 [P] [US3] Unit-тест `web/tests/webx5/routes/test_calculate_with_cashback.py`: (1) анонимный запрос (loyalty_card_id=None) → cashback=None; (2) пользователь без счёта → cashback.points_available=0, points_to_apply=0; (3) полный сценарий из quickstart; (4) NB: /calculate НЕ должен создавать записи в `points_transaction` и НЕ должен менять `points_account.balance` — assert-ы после запроса.

**Checkpoint**: US3 закрыта. MVP-триада P1 (US1+US2+US3) завершена. Кешбек работает end-to-end: начисление → расчёт → списание.

---

## Phase 6: User Story 4 — Просмотр баланса и истории (Priority: P2)

**Goal**: авторизованный пользователь видит свой баланс, курс, эквивалент в рублях и последние 20 транзакций через REST + мобильный экран.

**Independent Test** (quickstart Scenario 7): пользователь с 3 транзакциями (2 earn, 1 spend) → `GET /points/balance` возвращает корректный баланс; `GET /points/transactions` — 3 объекта в правильном порядке.

### Backend

- [X] T031 [US4] Добавить методы в `PointsService` (`web/src/webx5/services/points.py`): `get_balance(session, loyalty_card_id) -> BalanceView` (BalanceView содержит balance, rate, balance_rub_equivalent — считается `balance // rate`); `list_transactions(session, loyalty_card_id, limit, offset) -> tuple[list, int]`.
- [X] T032 [US4] Создать `web/src/webx5/routes/points.py` с эндпоинтами `GET /points/balance`, `GET /points/transactions` (query: limit default 20 max 100, offset default 0). Оба — под `CurrentUserUUID`. Если аккаунта нет — сервис возвращает `balance=0, transactions=[]`, счёт лениво создаётся при первом чтении balance.
- [X] T033 [US4] Зарегистрировать `points_router` в `web/src/webx5/core/server.py` (или где регистрируются все роутеры) через `api.server.include_router(points_router)`.
- [X] T034 [P] [US4] Integration-тест `web/tests/webx5/routes/test_points_routes.py`: (1) без JWT → 401 на оба эндпоинта; (2) новый пользователь → balance=0, transactions=[]; (3) пользователь с историей → корректные поля, порядок DESC по created_at; (4) пагинация limit/offset.

### Mobile

- [X] T035 [P] [US4] Создать `x5mobile/src/hooks/usePoints.ts`: два хука — `usePointsBalance()` (GET /points/balance) и `usePointsTransactions(limit=20)` (GET /points/transactions). TypeScript strict, использовать существующий fetch-wrapper из `x5mobile/src/hooks/`. Ошибки → возвращать `{data, error, loading, refresh}`.
- [X] T036 [US4] Создать экран `x5mobile/src/app/(app)/points.tsx`: показывает `balance`, `rate_points_per_rub`, `balance_rub_equivalent` крупно; ниже — FlatList из 20 транзакций (type, amount, дата, ссылка на task/receipt). Pull-to-refresh. Используются `StyleSheet.create`, функциональный компонент. Соблюдение принципа II — экран доступен из главного через один Tab.
- [X] T037 [US4] Добавить пункт «Мои баллы» в существующую tab-навигацию мобильного (`x5mobile/src/app/(app)/_layout.tsx` или как называется layout табов). Иконка — @expo/vector-icons, семантически подходящая (например, `star-outline`).

**Checkpoint**: US4 закрыта. Экран баллов доступен на мобильном ≤2 тапа от главного; данные подгружаются с бэкенда.

---

## Phase 7: User Story 5 — Экономия учитывает кешбек (Priority: P2)

**Goal**: `GET /receipts/economy` и детализация чека показывают экономию = скидки + кешбек.

**Independent Test** (quickstart Scenario 6): 2 чека с `sum(discounted_amount)=100/50` и `cashback_applied_rub=0/30` → `GET /receipts/economy.total_saved = 180`.

- [X] T038 [US5] Изменить `web/src/webx5/crud/receipt.py::ReceiptRepository.get_economy_summary`: включить `SUM(cashback_applied_rub)` в `total_saved`. Итоговый `total_saved = sum(base_price×qty - paid_price×qty) + sum(cashback_applied_rub)`.
- [X] T039 [US5] Изменить `web/src/webx5/routes/receipts.py::list_receipts` — `total_saved` по чеку = `(total_base - total_paid) + int(receipt.cashback_applied_rub)`. Ответ уже содержит `total_saved`, только формула другая.
- [X] T040 [US5] Изменить `web/src/webx5/routes/receipts.py::get_receipt`: аналогично + добавить в `ReceiptDetailResponse` (в `web/src/webx5/schemas/receipt.py`) поля `cashback_applied_points`, `cashback_applied_rub`, `points_rate_at_purchase` для показа детализации.
- [X] T041 [P] [US5] Integration-тест `web/tests/webx5/routes/test_economy_with_cashback.py`: два чека, второй с cashback → total_saved корректный; детализация чека возвращает поля кешбека.

**Checkpoint**: US5 закрыта. Единый счётчик экономии = скидки + кешбек (принцип I конституции соблюдён).

---

## Phase 8: User Story 6 — Настройка курса баллов к валюте (Priority: P2)

**Goal**: терминал может изменить курс; последующие начисления as-is (не зависят), последующие списания используют новый курс.

**Independent Test** (quickstart Scenario 3): `PUT /points/settings/rate` с токеном → курс изменился; списание идёт по новому курсу; неавторизованный запрос — 401; курс=0 — 422.

- [X] T042 [US6] Добавить в `web/src/webx5/routes/points.py`: `GET /points/settings/rate` — публичный, `PUT /points/settings/rate` — под `TerminalTokenDep`. Body для PUT: `RateUpdate` из `schemas/points.py`. Валидация `rate > 0` — Pydantic constraint (`Field(gt=0)`) + сервисный CHECK.
- [X] T043 [US6] Добавить в `web/src/webx5/services/points.py`: `set_rate(session, new_rate) -> int` — вызывает `repo.set_rate`, логирует `structlog.info("points.rate_changed", old=..., new=...)`. Возвращает применённый курс.
- [X] T044 [P] [US6] Integration-тест `web/tests/webx5/routes/test_points_rate_routes.py` (SC-007): (1) GET публичен, возвращает 10 из seed; (2) PUT без токена → 401; (3) PUT c токеном и valid rate=20 → 200, GET возвращает 20; (4) PUT с rate=0 или -1 → 422; (5) уже проведённая транзакция сохранила `rate_at_time=10`, новый rate не пересчитывает историю.
- [X] T045 [P] [US6] Mobile: показать текущий курс в шапке экрана `x5mobile/src/app/(app)/points.tsx` (уже фетчится в US4; убедиться, что подпись «X баллов = 1 руб» отображается). Это делает курс явно видимым пользователю (принцип I — прозрачность).

**Checkpoint**: US6 закрыта. Все 6 user stories работают.

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: чистка, документация, финальная валидация.

- [X] T046 [P] Запустить `lint-format` subagent по `web/src/webx5/` и `web/tests/webx5/` — все новые файлы проходят `ruff check` и `ruff format`.
- [X] T047 [P] Обновить `README.md`: в разделе «Endpoints» добавить `/points/*`; в разделе «Cashback flow» — краткое описание жизненного цикла баллов (2-3 предложения + ссылка на `specs/007-cashback-points/`).
- [X] T048 [P] Обновить `BACKLOG.md`: (1) удалить неактуальные поля `task.reward_id`/`task.reward_type` отдельной миграцией; (2) возврат/отмена чека и откат баллов; (3) сгорание баллов по сроку; (4) дробный курс (Decimal); (5) cleanup orphan `points_account` при удалении `loyalty_card`; (6) push-уведомление о начислении.
- [X] T049 [P] Прогнать все сценарии из `specs/007-cashback-points/quickstart.md` вручную на локальном стенде; убедиться, что traceability-таблица (US → FR → SC) проходит.
- [X] T050 Смок-тест мобильного: `cd x5mobile && npm run start` → открыть на iOS Simulator, проверить, что таб «Мои баллы» открывается, экран показывает данные с локального `web`.
- [X] T051 Валидация принципа II: измерить, что «главный экран → экран баллов» — ровно 1 тап; «главный экран → экономия с cashback» — ≤2 тапа. Если больше — переделать навигацию до PoC-демо.
- [X] T052 Финальная проверка SC (Success Criteria из spec.md): все 9 SC покрыты либо тестами, либо ручными сценариями quickstart; проставить галочки в `specs/007-cashback-points/checklists/requirements.md` при необходимости.

---

## Phase 10: Convergence

**Источник:** `ARCHITECTURE.md` trade-off #8, `BACKLOG.md` §lazy-imports, §apply_discount-encapsulation, `USER_FLOW.md` §basket-assistant. Basket-модуль (`dima`).

- [X] T053 Создать `web/src/webx5/tasks/basket.py` — Celery task `basket_apply_instruction(user_id_str, items_json, instruction)` в очереди `receipts`: десериализует `items_json → list[BasketItemIn]`, вызывает `basket_service.apply_instruction(session, items, instruction)`, возвращает сериализованный `AssistantResponse.model_dump()`. Session берётся через `db.get_sync_session()` по аналогии с `tasks/generation.py`. per ARCHITECTURE.md §trade-off #8 (contradicts)
- [X] T054 [P] Зарегистрировать `webx5.tasks.basket` в списке `_TASK_MODULES` в `web/src/webx5/core/celery_app.py`. per ARCHITECTURE.md §trade-off #8 (missing)
- [X] T055 [P] Добавить в `web/src/webx5/schemas/basket.py` схему `AssistantTaskEnqueuedResponse(task_id: str, status: Literal["pending"])` и `AssistantTaskResultResponse(status: Literal["pending","complete","failed"], result: AssistantResponse | None = None)`. per USER_FLOW.md §basket-assistant (missing)
- [X] T056 Изменить `web/src/webx5/routes/basket.py::post_basket_assistant`: принять `data.items` и `data.instruction`, сериализовать `items → json`, вызвать `basket_apply_instruction.delay(str(user_id), items_json, data.instruction)`, вернуть `AssistantTaskEnqueuedResponse(task_id=str(result.id), status="pending")` со статусом 202. per ARCHITECTURE.md §trade-off #8 (contradicts)
- [X] T057 Добавить в `web/src/webx5/routes/basket.py` эндпоинт `GET /basket/assistant/{task_id}`: читает `celery_app.AsyncResult(task_id)`; если `PENDING` → `{status:"pending"}`; если `SUCCESS` → `{status:"complete", result: AssistantResponse(**r.result)}`; если `FAILURE` → `{status:"failed", result:None}`. `task_id` — строка, validate как UUID-format через Pydantic (Path). per USER_FLOW.md §basket-assistant (missing)
- [X] T058 Обновить `x5mobile/src/hooks/useBasket.ts::applyInstruction()`: если `POST /basket/assistant` вернул 202, войти в цикл poll `GET /basket/assistant/{task_id}` с интервалом 800 мс (не более 15 секунд); при `status="complete"` применить `result.items`; при `status="failed"` или таймауте — показать сообщение об ошибке. Промежуточный статус → отображать `loading` в UI. per USER_FLOW.md §basket-assistant (partial)
- [X] T059 [P] Убрать lazy imports из `web/src/webx5/routes/basket.py`: перенести `from webx5.core.basket import basket_service` на уровень модуля (строки 20, 28, 36, 44). Циклического импорта нет — цепочка `server.py → routes/basket.py → core/basket.py` не замыкается. per BACKLOG §«Lazy import basket_service» (partial)
- [X] T060 [P] Перевести `apply_discount` из module-level функции в `@staticmethod DiscountCalculatorService.apply_discount(base_price, discount)` в `web/src/webx5/services/discount_calculator.py`; внутри `calculate()` заменить вызов `apply_discount(...)` на `self.apply_discount(...)` (или `DiscountCalculatorService.apply_discount(...)`). В `web/src/webx5/services/receipt.py` заменить `from webx5.services.discount_calculator import apply_discount` на `from webx5.services.discount_calculator import DiscountCalculatorService` и вызов `apply_discount(base_price, discount)` на `DiscountCalculatorService.apply_discount(base_price, discount)`. per BACKLOG §«apply_discount как публичная функция» (contradicts)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)** → без зависимостей, стартует сразу.
- **Phase 2 (Foundational)** → зависит от Phase 1. Блокирует все user stories.
- **Phase 3 (US1)** → после Phase 2. Независима от US2/US3.
- **Phase 4 (US2)** → после Phase 2. Независима от US1/US3 (T023 не трогает task_completion).
- **Phase 5 (US3)** → после Phase 2 + T018 (apply_cashback из US2, если пойти строго последовательно; но T018 можно сделать в любой из US2/US3 — общий утиль).
- **Phase 6 (US4)** → после Phase 2. Может идти параллельно с US1/US2/US3.
- **Phase 7 (US5)** → после US2 (нужны заполненные `cashback_applied_rub` в чеках, чтобы тест был осмысленным). Реально код меняется независимо.
- **Phase 8 (US6)** → после Phase 2. Независима.
- **Phase 9 (Polish)** → после всех предыдущих.

### Within Each User Story

- Модели/схемы → сервис → роут → тесты (тесты можно писать параллельно с реализацией — не TDD-строго).
- Мобильный код (US4, US6) — после того, как соответствующий REST-эндпоинт готов.

### Parallel Opportunities

- **Phase 1**: T002 и T003 — параллельно.
- **Phase 2**: T005, T006 — параллельно с T004 (после того, как T004 создал класс `PointsAccount`); T010 параллельно с T009.
- **Phase 3 (US1)**: T016, T017 — оба test-файла независимы, [P].
- **Phase 4 (US2)**: T019, T020 — [P] с T018 (разные файлы); T025, T026 — [P].
- **Phase 5 (US3)**: T030 — [P].
- **Phase 6 (US4)**: T034, T035 — [P]; T036 после T035; T037 после T036.
- **Phase 7 (US5)**: T041 — [P] с реализацией.
- **Phase 8 (US6)**: T044, T045 — [P].
- **Phase 9**: T046, T047, T048, T049 — все [P].

### Cross-story parallelism (multiple developers)

После завершения Phase 2 можно параллельно запускать:
- Dev A: US1 (Phase 3)
- Dev B: US2 (Phase 4) — T018 и `points_applier.py` шарит с US3
- Dev C: US4 (Phase 6, backend + mobile)

US3, US5, US6 подхватываются, как только освобождаются разработчики.

---

## Parallel Example: MVP-триада (US1 + US2 + US3)

```bash
# После Phase 2 (foundational) три P1-story идут параллельно:
Developer A (US1): T012 → T013 → T014 → T015 → T016 → T017
Developer B (US2): T018 → T019 → T020 → T021 → T022 → T023 → T024 → T025 → T026
Developer C (US3): T027 → T028 → T029 → T030
                   (ждёт готовности T018 из US2; далее — независимо)

# Затем Phase 6 (US4) — уходит другим разработчиком одновременно:
Developer D (US4 backend): T031 → T032 → T033 → T034
Developer E (US4 mobile):  T035 → T036 → T037

# После MVP-триады и US4 — Polish (Phase 9) параллельно:
T046, T047, T048, T049 (все [P])
```

---

## Implementation Strategy

### MVP First (US1 + US2 + US3 — все P1)

1. Phase 1 (Setup) — быстро.
2. Phase 2 (Foundational) — критический путь.
3. Phase 3 (US1) — начисление работает. Демо: закрыл задание → баланс вырос.
4. Phase 4 (US2) — списание работает. Демо: касса берёт баллы.
5. Phase 5 (US3) — расчёт с кешбеком. Демо: кассир видит выгоду до подтверждения.
6. **STOP + VALIDATE MVP**: quickstart Scenarios 1–3 проходят end-to-end. Уже готово для базовой демонстрации хакатонного жюри.

### Incremental Delivery (P2-релизы)

7. Phase 6 (US4) — user-facing экран баланса.
8. Phase 7 (US5) — счётчик экономии (принцип I виден).
9. Phase 8 (US6) — гибкость курса (принцип IV — калибровка).

### Полный релиз

10. Phase 9 (Polish) — линт, доки, ручная приёмка quickstart, метрики принципа II.

---

## Notes

- Тесты — не TDD-строго. Пишутся параллельно с реализацией внутри одной user story. `⚠️` — тесты, которые нельзя пропускать: это проверка ключевых инвариантов (SC-002, SC-003, SC-005, SC-007, SC-009).
- Комментарии в коде — только там, где WHY не очевиден (правило из CLAUDE.md). Не писать docstring на каждый метод.
- Форматирование и линт — только через subagent `lint-format` (правило из `scripts-and-services.md`). Не запускать `ruff` руками.
- Каждая user story — независимо коммитабельна и демонстрируется отдельно.
- Не удалять поля `task.reward_id`/`task.reward_type` в этой ветке — вынесено в BACKLOG (T048), чтобы не блокировать спеку миграциями.
- Все денежные значения этой фичи — integer. Никаких Decimal/float в points_*.
