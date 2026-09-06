# Tasks: Колесо фортуны и купоны

**Input**: Design documents from `specs/009-fortune-wheel-coupons/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/api-contracts.md, quickstart.md

**Organization**: Задачи сгруппированы по пользовательским историям. Каждая история независимо реализуема и тестируема.

**Tests**: Unit-тесты слоя Service включены (конституция + plan.md). Это не TDD-контрактные тесты: пишутся вместе с реализацией истории.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Можно выполнять параллельно (разные файлы, нет незавершённых зависимостей)
- **[Story]**: К какой пользовательской истории относится задача

## Path Conventions

Всё в рамках существующего FastAPI-сервиса `web/`:

- Entities: `web/src/webx5/entities/`
- CRUD: `web/src/webx5/crud/`
- Services: `web/src/webx5/services/`
- Schemas: `web/src/webx5/schemas/`
- Routes: `web/src/webx5/routes/`
- Core wiring: `web/src/webx5/core/`
- Migrations: `web/alembic/versions/`
- Tests: `web/tests/webx5/`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: SQLAlchemy-сущности и env-заготовка до миграций и сервисов.

- [X] T001 Создать `CouponAccount` и `CouponTransaction` в `web/src/webx5/entities/coupon.py` (поля и CHECK/UNIQUE по `specs/009-fortune-wheel-coupons/data-model.md`: balance ≥ 0; type ∈ weekly_grant|task_complete|spin; частичные unique через `Index` + `postgresql_where`)
- [X] T002 [P] Создать `WheelSpin` в `web/src/webx5/entities/wheel.py` (loyalty_card_id, sector_code, prize_type, prize_label, cashback_rub, gift_reward_id nullable без FK на первом шаге или FK на `gift_reward.id`, coupons_spent=1, created_at)
- [X] T003 Добавить `related_spin_id` (UUID NULL, FK `wheel_spin.id` ON DELETE SET NULL) в `web/src/webx5/entities/reward.py` у `GiftReward`
- [X] T004 [P] Добавить `related_spin_id` и частичный UNIQUE `ux_points_tx_earn_spin` в `web/src/webx5/entities/points.py` у `PointsTransaction`
- [X] T005 Зарегистрировать `CouponAccount`, `CouponTransaction`, `WheelSpin` в `web/src/webx5/entities/__init__.py`
- [X] T006 [P] Добавить `FORTUNE_WHEEL_WEEKLY_COUPONS=3` в `.env.example`

**Checkpoint**: Entity-классы видны Alembic; env задокументирован.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Схема БД, репозитории, каталог секторов, каркас купонов. Без этого нельзя отдать `/wheel` и списать купон.

**⚠️ CRITICAL**: Пользовательские истории не начинать, пока фаза не закрыта.

- [X] T007 Написать миграцию `web/alembic/versions/n2c3d4e5f6a7_fortune_wheel_coupons.py` (`down_revision = m1b2c3d4e5f6`): `coupon_account` → `wheel_spin` (без gift FK) → `coupon_transaction` (три частичных UNIQUE) → `gift_reward.related_spin_id` → `points_transaction.related_spin_id` + unique earn-by-spin → `wheel_spin.gift_reward_id`; downgrade — обратный порядок
- [X] T008 Применить миграцию: `poetry -C web run alembic -c web/alembic.ini upgrade head`
- [X] T009 Создать `CouponRepository` в `web/src/webx5/crud/coupon.py`: `get_or_create_account`, `lock_account_for_update` (`SELECT … FOR UPDATE`), `bump_balance`, `debit_balance`, `insert_transaction`, `list_transactions`, `count_transactions`, `has_weekly_grant(account_id, week_start)`
- [X] T010 [P] Создать `WheelSpinRepository` в `web/src/webx5/crud/wheel.py`: `create`, `set_gift_reward_id`, `list_for_user`, `count_for_user`, `get`
- [X] T011 [P] Создать протокол `PrizeCatalogProvider` и `FixedPrizeCatalog` в `web/src/webx5/services/prize_catalog.py` (4 сектора из спеки; `get_sectors(user_id)`; сумма `probability_percent` = 100; gift резолвит `categories.name = 'кондитерка'` в UUID, иначе бросает понятную ошибку)
- [X] T012 [P] Создать схемы `SectorOut`, `GiftSectorOut`, `WheelStateOut`, `SpinOut`, `SpinHistoryItem`, `SpinPage` в `web/src/webx5/schemas/wheel.py` по `specs/009-fortune-wheel-coupons/contracts/api-contracts.md`
- [X] T013 [P] Создать схемы `CouponTxOut`, `CouponTxPage` в `web/src/webx5/schemas/coupon.py`
- [X] T014 Создать `web/src/webx5/core/wheel.py`: чтение `FORTUNE_WHEEL_WEEKLY_COUPONS` (int ≥ 0, иначе ошибка конфигурации), константа пояса `Europe/Moscow`, функция `current_week_start()`, wiring репозиториев/сервисов без side effects на импорте crud
- [X] T015 Создать `CouponService` в `web/src/webx5/services/coupon.py` с DI на `CouponRepository`: `get_or_create_account`, `get_balance` (ленивый create, без weekly grant)

**Checkpoint**: `alembic current` = HEAD. Можно писать `GET /wheel` и спин.

---

## Phase 3: User Story 1 — Сектора колеса и баланс купонов (Priority: P1) 🎯 MVP

**Goal**: Авторизованный пользователь одним запросом получает сектора (название, тип, вероятность, параметры приза) и текущий баланс купонов. Без купонов сектора всё равно видны, крутить нельзя (`can_spin=false`).

**Independent Test**: `GET /wheel` с JWT → ≥2 сектора, сумма вероятностей 100%, есть cashback и gift; без JWT → 401. Новый пользователь без гранта: `coupons=0`, `can_spin=false`.

### Implementation for User Story 1

- [X] T016 [US1] Реализовать `WheelService.get_state(session, user_id)` в `web/src/webx5/services/wheel.py`: каталог + `CouponService.get_balance`; `can_spin = coupons > 0`; `weekly_coupons` из env; `week_start` из `core/wheel.py` (еженедельный грант ещё не вызывать — это US3)
- [X] T017 [US1] Добавить `GET /wheel` в `web/src/webx5/routes/wheel.py` (`CurrentUserUUID` + `SessionDep` → `WheelService.get_state`; 401 без JWT)
- [X] T018 [US1] Подключить `wheel_router` в `web/src/webx5/core/server.py`
- [X] T019 [P] [US1] Unit-тесты `FixedPrizeCatalog` в `web/tests/webx5/services/test_prize_catalog.py`: 4 сектора, сумма 100%, оба типа призов, `get_sectors` принимает `user_id`
- [X] T020 [US1] Тесты маршрута в `web/tests/webx5/routes/test_wheel_routes.py`: 401 без токена; 200 с токеном — инварианты контракта `GET /wheel`

**Checkpoint**: Мобильный клиент может нарисовать колесо. Спин ещё не работает.

---

## Phase 4: User Story 2 — Кручение и выдача приза (Priority: P1)

**Goal**: `POST /wheel/spin` списывает 1 купон, сервер выбирает сектор по весам, выдаёт кешбэк или `gift_reward` атомарно. Клиентский `sector_code` в теле игнорируется.

**Independent Test**: Выставить `coupon_account.balance=1` через репозиторий, вызвать спин → баланс 0, есть `wheel_spin` и либо баллы, либо active gift. Повторный спин → 409 `INSUFFICIENT_COUPONS`.

### Implementation for User Story 2

- [X] T021 [US2] Добавить `PointsRepository.insert_earn_for_spin` (без `session.rollback` при IntegrityError) в `web/src/webx5/crud/points.py` и `PointsService.award_for_spin(session, loyalty_card_id, amount_rub, spin_id)` в `web/src/webx5/services/points.py` — та же формула, что `award_for_task`
- [X] T022 [P] [US2] Добавить nullable `related_spin_id` в `TransactionOut` в `web/src/webx5/schemas/points.py` и прокинуть в `web/src/webx5/routes/points.py`
- [X] T023 [US2] Добавить `CouponService.debit_for_spin(session, user_id, spin_id)` в `web/src/webx5/services/coupon.py`: lock → если balance < 1 вернуть отказ; иначе −1 и транзакция type=`spin` amount=`-1`
- [X] T024 [US2] Реализовать `WheelService.spin(session, user_id)` в `web/src/webx5/services/wheel.py`: lock купонов → (хук weekly grant оставить no-op до US3) → debit → `SystemRandom().choices` по секторам → insert `wheel_spin` → `award_for_spin` или `GiftRewardRepository.create` (`task_id=None`, `related_spin_id`, `valid_to=now+7d`, category `кондитерка`) → `set_gift_reward_id`; одна сессия/транзакция; лишние поля тела не читать
- [X] T025 [US2] Добавить `POST /wheel/spin` в `web/src/webx5/routes/wheel.py`: пустое/`{}` тело; 200 `SpinOut`; 409 `{"detail":"INSUFFICIENT_COUPONS"}`; 503 если категория подарка не резолвится (транзакция откатилась)
- [X] T026 [US2] Unit-тесты в `web/tests/webx5/services/test_wheel_service.py`: успех cashback и gift; отказ при balance=0; параллельные два спина / один купон — один успех; клиентский sector_code не влияет (вызывать сервис без этого аргумента)

**Checkpoint**: Кручение выдаёт приз только с сервера. GET /rewards и GET /points/balance отражают выигрыш.

---

## Phase 5: User Story 3 — Еженедельные купоны из env (Priority: P1)

**Goal**: При первом `GET /wheel` или `POST /wheel/spin` на календарной неделе (пн, Europe/Moscow) начислить N купонов идемпотентно. Прошлые недели не догоняются. N=0 — строки гранта нет, баланс не растёт.

**Independent Test**: Новый пользователь, N=3 → первый GET /wheel даёт `coupons=3`; второй GET на той же неделе — всё ещё 3 (без спинов). Сменить N на 5 — текущая неделя не пересчитывается; новая неделя даёт 5.

### Implementation for User Story 3

- [X] T027 [US3] Реализовать `CouponService.ensure_weekly_grant(session, user_id)` в `web/src/webx5/services/coupon.py`: под `FOR UPDATE` проверить unique недели; если N>0 и гранта нет — `bump_balance(N)` + tx `weekly_grant`; если N=0 — ничего не писать
- [X] T028 [US3] Вызвать `ensure_weekly_grant` в начале `WheelService.get_state` и `WheelService.spin` в `web/src/webx5/services/wheel.py` (до проверки баланса / списания)
- [X] T029 [US3] Тесты в `web/tests/webx5/services/test_coupon_service.py`: идемпотентность на одной неделе; N=0; смена N не переписывает уже выданный пакет; пропуск недели не доначисляет долг (только текущий `week_start`)

**Checkpoint**: Сценарий 1 quickstart: первый заход = N купонов.

---

## Phase 6: User Story 4 — Купоны за выполненное задание (Priority: P2)

**Goal**: Закрытие задания начисляет +1 купон сверх основной награды. Повтор обработки того же задания купон не дублирует. Истечение купона не даёт.

**Independent Test**: Закрыть задание → в `coupon_transaction` одна строка `task_complete` amount=1; повтор `apply_receipt` вторую не создаёт; expiration sweep без `task_complete`.

### Implementation for User Story 4

- [X] T030 [US4] Добавить `CouponService.award_for_task(session, task)` в `web/src/webx5/services/coupon.py`: +1, tx type=`task_complete`, unique по `related_task_id`; при конфликте — no-op
- [X] T031 [US4] Вызвать `award_for_task` в конце успешного завершения в `web/src/webx5/services/task_completion.py` (после gift или `award_for_task` баллов, в той же сессии); ветку истечения не трогать
- [X] T032 [US4] Тесты в `web/tests/webx5/services/test_task_completion_coupon.py`: +1 вместе с основной наградой; 100 повторных закрытий одного task → одна tx; истечение без купона

**Checkpoint**: Контур «задание → купон → спин» замкнут.

---

## Phase 7: User Story 5 — История кручений и леджер купонов (Priority: P2)

**Goal**: Пользователь видит спины (приз, дата, статус подарка) и операции с купонами.

**Independent Test**: Два спина → `GET /wheel/spins` возвращает 2 записи DESC; без спинов — пустой `items`. `GET /coupons/transactions` содержит weekly_grant / spin / task_complete.

### Implementation for User Story 5

- [X] T033 [US5] Добавить `GET /wheel/spins` в `web/src/webx5/routes/wheel.py` (limit/offset как `/points/transactions`; `gift_status` из связанного `gift_reward` или null)
- [X] T034 [P] [US5] Создать `GET /coupons/transactions` в `web/src/webx5/routes/coupons.py` через `CouponService.list_transactions`
- [X] T035 [US5] Подключить `coupons_router` в `web/src/webx5/core/server.py`
- [X] T036 [US5] Дописать проверки истории в `web/tests/webx5/routes/test_wheel_routes.py`: пустая история 200; порядок DESC; 401 без JWT на оба новых пути

**Checkpoint**: Сценарии 5–6 quickstart выполняются.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Логи, проверка e2e, мелочи совместимости.

- [X] T037 Добавить structlog-события `wheel.spin`, `coupon.weekly_grant`, `coupon.task_complete`, `coupon.spin_denied` в `web/src/webx5/services/wheel.py` и `web/src/webx5/services/coupon.py` (без `print`)
- [X] T038 [P] Проставить structlog в `web/src/webx5/services/points.py` для `award_for_spin` (`points.awarded_spin`)
- [X] T039 Прогнать сценарии `specs/009-fortune-wheel-coupons/quickstart.md` против живого API (401, первый GET /wheel = N, спин, 409, леджер)
- [X] T040 [P] Сверить OpenAPI Scalar (`GET /docs`) с `specs/009-fortune-wheel-coupons/contracts/api-contracts.md`: четыре пути, схемы, 409 detail

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: сразу
- **Foundational (Phase 2)**: после Setup — **блокирует все истории**
- **US1 (Phase 3)**: после Phase 2
- **US2 (Phase 4)**: после Phase 2; для живого демо удобнее после US1 (тот же `/wheel`), но спин тестируется сидом баланса
- **US3 (Phase 5)**: после US1 (хук в `get_state`); желательно до/вместе с US2, чтобы спин в новую неделю видел пакет
- **US4 (Phase 6)**: после Phase 2 (нужен `CouponService`); не зависит от спина
- **US5 (Phase 7)**: после US2 (нужны записи `wheel_spin`)
- **Polish (Phase 8)**: после выбранных историй

### User Story Dependencies

- **US1**: только фундамент
- **US2**: фундамент + `CouponService.debit`; независимый тест через ручной balance=1
- **US3**: патчит `WheelService` из US1/US2
- **US4**: параллельно с US1–US3 после фундамента
- **US5**: после US2 (и лучше после US3/US4, чтобы леджер был полным)

```text
Phase 1 → Phase 2 ┬─ US1 → US3 ─┐
                  ├─ US2 ───────┼─ US5 → Polish
                  └─ US4 ───────┘
```

### Parallel Opportunities

- Phase 1: T002 ∥ T004 ∥ T006; T001 и T003 перед T005
- Phase 2: T010 ∥ T011 ∥ T012 ∥ T013 после T008
- После Phase 2: US4 можно вести параллельно с US1
- US1: T019 ∥ T016 (тесты каталога не ждут роут)

---

## Parallel Example: User Story 1

```text
Task: "FixedPrizeCatalog tests in web/tests/webx5/services/test_prize_catalog.py"
Task: "WheelService.get_state in web/src/webx5/services/wheel.py"
# затем роут и server.py последовательно
```

## Parallel Example: After Foundational

```text
Dev A: Phase 3 US1 (GET /wheel)
Dev B: Phase 6 US4 (купон за задание) — другой набор файлов кроме coupon.py
# coupon.py: не править параллельно без разведения методов
```

---

## Implementation Strategy

### MVP (P1: US1 + US2 + US3)

1. Phase 1 + Phase 2
2. US1 — клиент рисует колесо
3. US3 — появляются купоны
4. US2 — спин и приз
5. **STOP**: quickstart сценарии 1–3

Без US3 спин в демо требует ручного баланса; для показа жюри берите US1+US3+US2 вместе.

### Incremental Delivery

1. Setup + Foundational
2. US1 → сектора
3. US3 → недельные купоны
4. US2 → кручение
5. US4 → купон за челлендж
6. US5 → история
7. Polish → quickstart целиком

### Suggested MVP scope

**US1 + US3 + US2** (все P1). US4 и US5 — второй инкремент доверия и контура «задание → купон».

---

## Notes

- `[P]` только если разные файлы и нет дыр в зависимостях
- Не ретраить `POST /wheel/spin` из клиента (research R13)
- `insert_earn_for_spin` не должен вызывать `session.rollback()` (research R6)
- Мобильный UI (`x5mobile/`) в этих задачах не менять
- Колесо не позиционировать как «готово к пилоту» без поправки конституции (план, Принцип II/IV)
