# Tasks: Составные задания, типы наград и вайб

**Input**: Design documents from `specs/008-composite-challenges-rewards-vibe/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/api-contracts.md

**Organization**: Задачи сгруппированы по пользовательским историям. Каждая история независимо реализуема и тестируема.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Можно выполнять параллельно (разные файлы, нет незавершённых зависимостей)
- **[Story]**: К какой пользовательской истории относится задача

## Path Conventions

Всё в рамках `web/` (существующий FastAPI-сервис):
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

**Purpose**: Новые SQLAlchemy-классы сущностей — до написания миграций и любого кода фичи.

- [X] T001 Добавить класс `TaskItem` в `web/src/webx5/entities/task.py` (поля: id, task_id FK, criterion_type CHECK, criterion_entity_id, quantity_target, quantity_current DEFAULT 0, label nullable; relationship к Task)
- [X] T002 [P] Создать `web/src/webx5/entities/vibe.py` с классом `VibeType` (поля: id, name UNIQUE, description, llm_context, created_at, updated_at)
- [X] T003 [P] Создать `web/src/webx5/entities/reward.py` с классом `GiftReward` (поля: id, task_id FK SET NULL, loyalty_card_id FK CASCADE, criterion_type CHECK, criterion_entity_id, quantity, status CHECK DEFAULT active, valid_to, created_at)
- [X] T004 Обновить `web/src/webx5/entities/user.py`: заменить поля `vibe_category: str` и `vibe_month: date` на `vibe_type_id: UUID FK vibe_type.id ON DELETE SET NULL nullable`; добавить relationship к `VibeType`
- [X] T005 Зарегистрировать `TaskItem`, `VibeType`, `GiftReward` в `web/src/webx5/entities/__init__.py`

**Checkpoint**: Все entity-классы готовы, alembic autogenerate может их обнаружить.

---

## Phase 2: Foundational (Блокирующие миграции)

**Purpose**: Схема БД должна быть полностью актуальна до реализации любой пользовательской истории.

**⚠️ CRITICAL**: Ни одна пользовательская история не реализуется до полного прохождения этой фазы.

- [X] T006 Написать миграцию M1 `web/alembic/versions/<hash>_create_vibe_type.py`: CREATE TABLE vibe_type; INSERT 6 строк из `VIBE_CATEGORIES` (`synth/challenges.py:101`) с заполнением llm_context списком категорий через запятую
- [X] T007 Написать миграцию M2 `web/alembic/versions/<hash>_add_user_vibe_type_fk.py`: ADD COLUMN users.vibe_type_id FK; UPDATE по совпадению имени; DROP COLUMN vibe_category, vibe_month (downgrade — обратная последовательность)
- [X] T008 [P] Написать миграцию M3 `web/alembic/versions/<hash>_create_task_item.py`: CREATE TABLE task_item; INSERT backfill — 1 task_item на каждый существующий task (берёт criterion_type, criterion_entity_id, quantity_target, quantity_current из task)
- [X] T009 [P] Написать миграцию M4 `web/alembic/versions/<hash>_extend_task_reward_type.py`: DROP CONSTRAINT ck_task_reward_type; ADD CONSTRAINT CHECK reward_type IN ('discount', 'cashback', 'gift')
- [X] T010 [P] Написать миграцию M5 `web/alembic/versions/<hash>_create_gift_reward.py`: CREATE TABLE gift_reward с index ix_gift_reward_user_status (loyalty_card_id, status)
- [X] T011 Применить все миграции: `poetry -C web run alembic -c web/alembic.ini upgrade head`; убедиться что все 5 миграций применились без ошибок

**Checkpoint**: `alembic current` показывает HEAD. Новые таблицы присутствуют в БД. Можно запускать пользовательские истории.

---

## Phase 3: US1 — Составное задание (Priority: P1) 🎯 MVP

**Goal**: Задание хранит N пунктов, прогресс по каждому отслеживается независимо; задание считается выполненным только когда все пункты закрыты.

**Independent Test**: Создать task с двумя task_item, применить чек с товаром только первого пункта — task остаётся открытым; применить чек со вторым товаром — task переходит в «выполнено».

### Implementation for User Story 1

- [X] T012 [US1] Добавить `TaskItemRepository` в `web/src/webx5/crud/task.py`: методы `create_item(session, *, task_id, criterion_type, criterion_entity_id, quantity_target, label)`, `get_items_for_task(session, task_id) -> list[TaskItem]`, `bump_item_progress(session, item, delta) -> TaskItem`, `all_items_complete(session, task_id) -> bool`
- [X] T013 [US1] Обновить `web/src/webx5/services/task_completion.py`: метод `apply_receipt` должен итерировать task_item для задания, независимо применять дельту к каждому пункту по соответствующему criterion_type/criterion_entity_id; задание завершается только когда `TaskItemRepository.all_items_complete()` → True (заменить проверку `task.quantity_current >= task.quantity_target`)
- [X] T014 [US1] Обновить `web/src/webx5/services/challenge_adapter.py`: в `persist_challenge()` после создания Task вызывать `task_item_repo.create_item()` с теми же полями (criterion_type, criterion_entity_id, quantity_target, label из `script_result.get("label")`); для одиночных заданий — ровно 1 task_item
- [X] T015 [P] [US1] Добавить `TaskItemOut` в `web/src/webx5/schemas/challenge.py` (поля: id, label, criterion_type, criterion_entity_id, quantity_target, quantity_current); добавить поле `items: list[TaskItemOut]` в схему ответа `ChallengeOut`
- [X] T016 [US1] Обновить `web/src/webx5/routes/challenges.py`: в GET /challenges при загрузке каждого Task дополнительно подгружать task_item через `TaskItemRepository.get_items_for_task()` и включать в ответ; обновить сервис в `web/src/webx5/core/challenges.py` если нужны новые зависимости
- [X] T017 [US1] Написать unit-тесты в `web/tests/webx5/services/test_task_item_progress.py`: проверить что (a) частичное выполнение пунктов не завершает task, (b) один товар засчитывается в оба применимых пункта параллельно, (c) все пункты выполнены → task завершается

**Checkpoint**: GET /challenges возвращает `items[]` для каждого задания. Частичное выполнение не закрывает задание.

---

## Phase 4: US2 — Награда-подарок (Priority: P1)

**Goal**: Пользователь получает gift_reward при выполнении задания; подарок автоматически применяется как скидка на самый дешёвый подходящий товар при предпросмотре корзины и создании чека.

**Independent Test**: Создать активный gift_reward для пользователя, добавить подходящий товар в корзину — в preview появляется gift_discounts с суммой скидки; оформить чек — paid_price = 0 для этого товара; GET /rewards возвращает status='used'.

### Implementation for User Story 2

- [X] T018 [P] [US2] Создать `web/src/webx5/crud/reward.py` с `GiftRewardRepository`: методы `create(session, *, task_id, loyalty_card_id, criterion_type, criterion_entity_id, quantity, valid_to)`, `get_active_for_user(session, user_id) -> list[GiftReward]` (фильтр status='active' AND valid_to > now()), `mark_used(session, reward) -> GiftReward`
- [X] T019 [P] [US2] Создать `web/src/webx5/schemas/reward.py`: схема `GiftRewardOut` (id, reward_type='gift', description, criterion_type, criterion_entity_id, quantity, status, valid_to, applicable: bool)
- [X] T020 [US2] Обновить `web/src/webx5/services/task_completion.py`: в ветке завершения задания — если `task.reward_type == 'gift'`, создавать `GiftReward` через `GiftRewardRepository.create()` с valid_to = task.deadline; `GiftRewardRepository` передаётся через DI в `TaskCompletionService`
- [X] T021 [US2] Обновить `web/src/webx5/services/discount_calculator.py`: метод `calculate()` принимает опциональный список активных `GiftReward` пользователя; для каждого reward ищет подходящие строки корзины (по product_id или category_id); применяет скидку (paid_price=0 на 1 единицу) к самому дешёвому matching товару; возвращает примененные gift_discounts отдельным полем
- [X] T022 [US2] Обновить `web/src/webx5/services/receipt.py`: после успешного создания чека вызывать `GiftRewardRepository.mark_used()` для всех gift_reward, которые были применены к строкам чека (paid_price=0)
- [X] T023 [US2] Создать `web/src/webx5/routes/rewards.py` с `rewards_router`: GET /rewards (JWT auth) — возвращает активные GiftReward пользователя через `GiftRewardRepository.get_active_for_user()`
- [X] T024 [US2] Обновить `web/src/webx5/schemas/basket.py` и `web/src/webx5/routes/basket.py`: добавить поле `gift_discounts: list[GiftDiscountApplied]` в ответ POST /basket/preview; `GiftDiscountApplied` содержит gift_reward_id, description, applied_to_item_id, discount_rub
- [X] T025 [US2] Прокинуть зависимости: добавить `GiftRewardRepository` в `web/src/webx5/core/purchases.py`; добавить `rewards_router` в `web/src/webx5/core/server.py`
- [X] T026 [US2] Написать unit-тесты в `web/tests/webx5/services/test_gift_reward_apply.py`: (a) gift_reward применяется к самому дешёвому category-товару, (b) gift_reward не применяется если товара нет в корзине, (c) mark_used вызывается после создания чека, (d) просроченный gift_reward не возвращается get_active_for_user

**Checkpoint**: POST /basket/preview возвращает gift_discounts. POST /receipts обнуляет цену подарочного товара. GET /rewards показывает статус.

---

## Phase 5: US3 + US4 — Вайб (Priority: P2)

**Goal**: Кассовый аппарат управляет каталогом вайбов (CRUD); пользователь выбирает / меняет / сбрасывает вайб за 1 вызов; вайб влияет на генерацию заданий и рекомендации корзины.

**Independent Test**: POS создаёт вайб через POST /vibes (с X-Terminal-Token); пользователь выбирает его через PUT /users/me/vibe; POS удаляет вайб — у пользователя vibe_id = null. Сгенерированное задание содержит категории из llm_context вайба.

**Note**: US4 (POS CRUD) реализуется первым внутри фазы — без типов вайба US3 нетестируема.

### Implementation for User Story 3 & 4

- [X] T027 [US3] Создать `web/src/webx5/crud/vibe.py` с `VibeRepository`: методы `create(session, *, name, description, llm_context)`, `get_all(session) -> list[VibeType]`, `get_by_id(session, vibe_id) -> VibeType | None`, `update(session, vibe, *, name?, description?, llm_context?) -> VibeType`, `delete(session, vibe)` (ON DELETE SET NULL срабатывает автоматически через FK)
- [X] T028 [US3] Создать `web/src/webx5/services/vibe.py` с `VibeService`: тонкий слой над `VibeRepository`; метод `create` проверяет 409 при дублировании имени (IntegrityError → raise HTTPException 409); метод `delete` находит вайб или raises 404
- [X] T029 [P] [US3] Создать `web/src/webx5/schemas/vibe.py`: схемы `VibeIn` (name, description, llm_context), `VibeUpdate` (все поля Optional), `VibeOut` (id, name, description — без llm_context для пользователей), `VibeFullOut` (+ llm_context, для POS если нужно)
- [X] T030 [US4] Создать `web/src/webx5/routes/vibes.py` с `vibes_router` (prefix=/vibes): GET /vibes (публичный, возвращает `list[VibeOut]`); POST /vibes (TerminalTokenDep → 201 VibeOut); PUT /vibes/{vibe_id} (TerminalTokenDep → 200 VibeOut); DELETE /vibes/{vibe_id} (TerminalTokenDep → 204)
- [X] T031 [US3] Добавить PUT /users/me/vibe в `web/src/webx5/routes/auth.py` (или новый `routes/users.py`): принимает `{"vibe_id": uuid | null}`; обновляет `user.vibe_type_id`; 404 если vibe_id указан но не найден; использует `CurrentUserUUID`
- [X] T032 [US3] Прокинуть зависимости: создать `web/src/webx5/core/vibes.py` с VibeService + VibeRepository; добавить `vibes_router` в `web/src/webx5/core/server.py`; добавить маршрут /users/me/vibe
- [X] T033 [US3] Обновить `web/src/webx5/services/challenge_adapter.py`: заменить `_resolve_vibe_category()` (который вызывал `pick_vibe_category`) на чтение `user.vibe_type` (relationship); если `user.vibe_type_id is None` — не передавать vibe-контекст в `build_profile`; если есть — передавать `VibeType.llm_context` вместо строки-имени категории; обновить ключ в профиле с `"vibe_category"` на `"vibe_context"` или обновить synth-генератор
- [X] T034 [US3] Обновить `web/src/webx5/crud/basket.py` метод `get_shopping_context()`: добавить поле `vibe_context` из `user.vibe_type.llm_context` (если вайб выбран) вместо детерминированного pick_vibe_category; обновить `web/src/webx5/services/basket_assistant.py` — передавать vibe_context в system prompt
- [X] T035 [US3] Написать unit-тесты в `web/tests/webx5/services/test_vibe_service.py`: (a) создание с дублирующимся именем → 409, (b) get_all возвращает все вайбы, (c) удаление вайба → пользователи с этим vibe_type_id получают NULL (проверить через БД в integration-тесте или мок), (d) пользователь без вайба получает рекомендации без vibe_context

**Checkpoint**: GET /vibes возвращает список. POST /vibes (с токеном) создаёт тип. DELETE каскадно сбрасывает вайб у пользователей. PUT /users/me/vibe выбирает/сбрасывает вайб. Генерация заданий учитывает llm_context.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Завершающие штрихи, затрагивающие несколько историй.

- [X] T036 Обновить `synth/challenges.py`: если `build_vibe_prompt` получает `vibe_context` (llm_context из VibeType) вместо `vibe_category` (имя из VIBE_CATEGORIES), скорректировать логику `allowed_categories` — парсить список из llm_context или передавать явно; `pick_vibe_category` оставить для seed/тестов, убрать из production flow
- [X] T037 Добавить автоматическую экспирацию gift_reward в `web/src/webx5/crud/reward.py`: метод `expire_overdue(session) -> list[GiftReward]` — SET status='expired' WHERE status='active' AND valid_to < now(); вызывать в celery-воркере или при GET /rewards
- [X] T038 Провалидировать сценарии из `specs/008-composite-challenges-rewards-vibe/quickstart.md`: выполнить все 4 curl-сценария против локального окружения, убедиться что ожидаемые ответы совпадают
- [X] T039 Обновить `BACKLOG.md`: закрыть пункт «Составные задания (multi-criterion)» как реализованный; добавить при необходимости новые технические долги (например, gift_reward UI выбора если потребуется)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: Нет зависимостей — стартует немедленно
- **Foundational (Phase 2)**: Зависит от Phase 1 (entity-классы должны быть написаны до миграций) — **БЛОКИРУЕТ все пользовательские истории**
- **US1 (Phase 3)**: Зависит от Phase 2 — независима от US2, US3, US4
- **US2 (Phase 4)**: Зависит от Phase 2 — независима от US1, US3, US4
- **US3+US4 (Phase 5)**: Зависит от Phase 2 — независима от US1, US2
- **Polish (Phase 6)**: Зависит от всех желаемых историй

### User Story Dependencies

- **US1 (P1)**: Старт после Phase 2 — нет зависимостей от других историй
- **US2 (P1)**: Старт после Phase 2 — нет зависимостей от других историй
- **US3+US4 (P2)**: Старт после Phase 2 — US4 реализуется первым внутри фазы

### Within Each Phase

- Entity-классы → миграции → регистрация → применение (`alembic upgrade head`)
- Repository → Service → Schema → Route → Core wiring
- Тесты пишутся после реализации (конституция требует покрытие Service-слоя)

### Parallel Opportunities

- T002, T003 (entity-классы) — параллельно
- T008, T009, T010 (миграции M3, M4, M5) — параллельно между собой (после T006, T007)
- T015, T018, T019, T029 (схемы) — параллельно в своих историях
- US1, US2, US3+US4 — три истории параллельно при наличии разработчиков

---

## Parallel Example: Phase 2

```bash
# Сначала последовательно (T006 → T007 для vibe FK зависит от vibe_type):
Task T006: "Написать миграцию M1 create_vibe_type"
Task T007: "Написать миграцию M2 add_user_vibe_type_fk"

# Параллельно (независимые миграции):
Task T008: "Написать миграцию M3 create_task_item"
Task T009: "Написать миграцию M4 extend task reward_type CHECK"
Task T010: "Написать миграцию M5 create_gift_reward"
```

## Parallel Example: User Story 2

```bash
# Параллельно:
Task T018: "Создать GiftRewardRepository в crud/reward.py"
Task T019: "Создать GiftRewardOut schema в schemas/reward.py"

# После T018 + T019:
Task T020: "Обновить TaskCompletionService — создание gift_reward"
Task T021: "Обновить DiscountCalculatorService — применение gift_reward"
```

---

## Implementation Strategy

### MVP First (US1 Only — Composite Tasks)

1. Завершить Phase 1: Setup (entity-классы)
2. Завершить Phase 2: Миграции (только T006–T011)
3. Завершить Phase 3: US1 (T012–T017)
4. **СТОП и ВАЛИДАЦИЯ**: проверить GET /challenges возвращает items[], частичное выполнение не закрывает задание
5. Deploy/demo

### Incremental Delivery

1. Phase 1 + Phase 2 → Foundation готова
2. Phase 3 → Составные задания работают → Demo (MVP!)
3. Phase 4 → Gift reward работает → Demo
4. Phase 5 → Vibe работает → Demo
5. Phase 6 → Polish

### Parallel Team Strategy

С двумя разработчиками (после Phase 2):
- Developer A: US1 (Phase 3) + US3+US4 (Phase 5)
- Developer B: US2 (Phase 4) + Polish (Phase 6)
