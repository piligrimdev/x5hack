# Tasks: Покупки, магазины и скидки

**Input**: Design documents from `specs/005-purchases-stores-discounts/`

**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/ ✅

**Organization**: Tasks grouped by user story for independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: User story label (US1–US6)

---

## Phase 1: Setup — DB Entities & Migration

**Purpose**: Создать все новые таблицы и SQLAlchemy-модели. Блокирует все пользовательские истории.

**⚠️ CRITICAL**: Сначала написать сущности, затем генерировать миграцию.

- [X] T001 [P] Создать SQLAlchemy-сущности StoreFormat и Store в `web/src/webx5/entities/store.py`
- [X] T002 [P] Создать SQLAlchemy-сущности DiscountType, DiscountLinkType, Discount, FormatDiscount, StoreDiscount в `web/src/webx5/entities/discount.py`
- [X] T003 [P] Создать SQLAlchemy-сущности Segment и LoyaltyCard в `web/src/webx5/entities/loyalty.py`
- [X] T004 [P] Создать SQLAlchemy-сущности Receipt и ReceiptItem в `web/src/webx5/entities/receipt.py`
- [X] T005 Создать Alembic-миграцию `add_purchases_tables` со всеми 11 таблицами (порядок: store_formats→stores→discount_types→discount_link_types→discounts→format_discounts→store_discounts→segments→loyalty_cards→receipts→receipt_items) и seed-записями для discount_types, discount_link_types, segments в `web/alembic/versions/`
- [X] T006 Добавить автоматическое создание LoyaltyCard (id=user.id) при регистрации пользователя в `web/src/webx5/services/auth.py`

**Checkpoint**: `docker compose up --build` и `alembic upgrade head` выполняются без ошибок; все 11 таблиц видны в БД.

---

## Phase 2: Foundational — Движок расчёта скидок

**Purpose**: DiscountRepository с запросом кандидатов и DiscountCalculatorService с best-price-wins. Блокирует US1 и US2.

**⚠️ CRITICAL**: Фаза 1 должна быть завершена перед этой фазой.

- [X] T007 Создать DiscountRepository с методом `find_applicable_for_cart(session, product_ids, store_id)` — возвращает все скидки-кандидаты (по product/category/brand) с учётом scope и дат — в `web/src/webx5/crud/discount.py`
- [X] T008 Создать DiscountCalculatorService с методом `calculate(items, store, loyalty_card_id, session)` — реализует best-price-wins: для каждого товара выбирает скидку с максимальным value, вычисляет paid_price и discounted_amount — в `web/src/webx5/services/discount_calculator.py`
- [X] T009 Создать composition root для discount_calculator_service в `web/src/webx5/core/purchases.py`

**Checkpoint**: Unit-тест: товар под тремя скидками (20%, 15%, 10%) → выбирается 20%.

---

## Phase 3: US1 — Расчёт скидок для кассы (Priority: P1) 🎯 MVP

**Goal**: Касса отправляет корзину, сервер возвращает best-price-wins цену для каждого товара.

**Independent Test**: `POST /receipts/calculate` с X-Terminal-Token, корзиной из 3 товаров и существующими скидками → ответ 200 с корректными paid_price и discounted_amount.

- [X] T010 [P] [US1] Создать Pydantic-схемы CalculateRequest и CalculateResponse (вложенные схемы для items) в `web/src/webx5/schemas/receipt.py`
- [X] T011 [US1] Реализовать `POST /receipts/calculate` route — принимает CalculateRequest, вызывает discount_calculator_service, возвращает CalculateResponse; валидация: 401 без X-Terminal-Token, 404 если store_id не найден, 422 если product_id неизвестен — в `web/src/webx5/routes/receipts.py`
- [X] T012 [US1] Зарегистрировать receipts_router в `web/src/webx5/core/server.py`

**Checkpoint**: `POST /receipts/calculate` с X-Terminal-Token → 200; без токена → 401; неизвестный product_id → 422.

---

## Phase 4: US2 — Фиксация чека (Priority: P1)

**Goal**: Касса фиксирует покупку; чек сохраняется с base_price, paid_price, discounted_amount; повторный запрос с тем же X-Idempotency-Key возвращает тот же чек.

**Independent Test**: `POST /receipts` с X-Idempotency-Key → 201; повторный → 200; та же запись в БД.

- [X] T013 [P] [US2] Создать ReceiptRepository с методами `create(session, receipt_id, data)` — идемпотентный через IntegrityError→SELECT паттерн — и `get_by_id(session, receipt_id, loyalty_card_id)` в `web/src/webx5/crud/receipt.py`
- [X] T014 [P] [US2] Расширить схемы в `web/src/webx5/schemas/receipt.py`: ReceiptCreate (с X-Idempotency-Key из header), ReceiptItemCreate, ReceiptResponse, ReceiptItemResponse
- [X] T015 [US2] Создать ReceiptService с методом `create_receipt(session, receipt_id, data)` — верифицирует скидки (422 при истёкшей/неприменимой), записывает base_price_at_purchase из product.current_price, вычисляет discounted_amount, синхронно обновляет task.quantity_current для активных заданий пользователя — в `web/src/webx5/services/receipt.py`
- [X] T016 [US2] Добавить receipt_service в composition root `web/src/webx5/core/purchases.py`
- [X] T017 [US2] Реализовать `POST /receipts` route — читает X-Idempotency-Key из заголовка (обязательный, 401 если отсутствует), вызывает receipt_service.create_receipt, возвращает 201/200 в зависимости от idempotency — в `web/src/webx5/routes/receipts.py`

**Checkpoint**: `POST /receipts` с X-Idempotency-Key и корректным discount_id → 201; повторно → 200; с истёкшей скидкой → 422.

---

## Phase 5: US3 + US4 — История покупок и экономия (Priority: P2)

**Goal**: Авторизованный пользователь видит список чеков, детализацию и суммарную экономию. Мобильный экран экономии.

**Independent Test (US3)**: `GET /receipts` с Bearer → список чеков пользователя. `GET /receipts/{id}` → детализация.
**Independent Test (US4)**: `GET /economy` с Bearer → `{ "total_saved": ..., "receipts_count": ... }`. Мобильный экран отображает цифру.

### Backend (US3 + US4)

- [X] T018 [P] [US3] Добавить в ReceiptRepository методы `list_by_loyalty_card(session, loyalty_card_id, page, size)` и `get_with_items(session, receipt_id, loyalty_card_id)` в `web/src/webx5/crud/receipt.py`
- [X] T019 [P] [US4] Добавить в ReceiptRepository метод `get_economy_summary(session, loyalty_card_id)` → `{ total_saved, receipts_count }` в `web/src/webx5/crud/receipt.py`
- [X] T020 [P] [US3] Добавить Pydantic-схемы ReceiptListItem, ReceiptDetailResponse, PaginatedReceiptList в `web/src/webx5/schemas/receipt.py`
- [X] T021 [P] [US4] Добавить Pydantic-схему EconomyResponse в `web/src/webx5/schemas/receipt.py`
- [X] T022 [US3] Реализовать `GET /receipts` и `GET /receipts/{id}` routes — CurrentUserUUID, 403 если чек принадлежит другому пользователю, 404 если не найден — в `web/src/webx5/routes/receipts.py`
- [X] T023 [US4] Реализовать `GET /economy` route — CurrentUserUUID — в `web/src/webx5/routes/receipts.py`

### Mobile (US3 + US4)

- [X] T024 [P] [US3] Создать хук `useReceipts(page?)` для GET /receipts в `x5mobile/src/hooks/useReceipts.ts`
- [X] T025 [P] [US3] Создать хук `useReceiptDetail(receiptId)` для GET /receipts/{id} в `x5mobile/src/hooks/useReceiptDetail.ts`
- [X] T026 [P] [US4] Создать хук `useEconomy()` для GET /economy в `x5mobile/src/hooks/useEconomy.ts`
- [X] T027 [US3] Создать экран списка чеков `x5mobile/src/app/(tabs)/purchases/index.tsx` — список с ReceiptListItem компонентами, заголовок с суммарной экономией (useEconomy), пустой стейт
- [X] T028 [US3] Создать переиспользуемый компонент ReceiptListItem в `x5mobile/src/components/screens/ReceiptListItem.tsx` — дата, магазин, итоговая сумма, экономия
- [X] T029 [US3] Создать экран детализации чека `x5mobile/src/app/(tabs)/purchases/[id].tsx` — позиции с названием, количеством, ценой без скидки, ценой со скидкой
- [X] T030 [US4] Добавить блок суммарной экономии на главный экран `x5mobile/src/app/index.tsx` — заменить хардкоженную цифру 2 450 ₽ на данные из useEconomy

**Checkpoint**: GET /receipts → список; GET /economy → цифра; мобильный экран покупок отображает чеки и суммарную экономию.

---

## Phase 6: US5 + US6 — Магазины и скидки (Priority: P3)

**Goal**: Публичное чтение магазинов и скидок; касса создаёт и обновляет справочники.

**Independent Test (US5)**: `GET /stores` без авторизации → список магазинов. `GET /discounts` → только актуальные скидки.
**Independent Test (US6)**: `POST /stores` с X-Terminal-Token → 201; без токена → 401. `POST /discounts` с истёкшим valid_to → 422.

### Stores

- [X] T031 [P] [US5] Создать Pydantic-схемы StoreFormatResponse, StoreResponse в `web/src/webx5/schemas/store.py`
- [X] T032 [P] [US5] Создать StoreRepository с методами `list_all`, `get_by_id`, `list_formats` в `web/src/webx5/crud/store.py`
- [X] T033 [P] [US6] Добавить в StoreRepository методы `create` и `update` в `web/src/webx5/crud/store.py`
- [X] T034 [P] [US6] Добавить Pydantic-схемы StoreCreate, StoreUpdate в `web/src/webx5/schemas/store.py`
- [X] T035 [US5] Реализовать `GET /stores`, `GET /stores/{id}`, `GET /store-formats` routes (публичные) в `web/src/webx5/routes/stores.py`
- [X] T036 [US6] Добавить `POST /stores` и `PUT /stores/{id}` routes с TerminalTokenDep в `web/src/webx5/routes/stores.py`
- [X] T037 [US5] Зарегистрировать stores_router в `web/src/webx5/core/server.py`

### Discounts

- [X] T038 [P] [US5] Создать Pydantic-схемы DiscountTypeResponse, DiscountResponse в `web/src/webx5/schemas/discount.py`
- [X] T039 [P] [US5] Добавить в DiscountRepository метод `list_active(session, entity_id?, link_type?)` — фильтр по дате — в `web/src/webx5/crud/discount.py`
- [X] T040 [P] [US5] Добавить в DiscountRepository метод `list_types` в `web/src/webx5/crud/discount.py`
- [X] T041 [P] [US6] Добавить в DiscountRepository методы `create(session, data)` и `update(session, id, data)` — включая запись в format_discounts / store_discounts — в `web/src/webx5/crud/discount.py`
- [X] T042 [P] [US6] Добавить Pydantic-схемы DiscountCreate, DiscountUpdate в `web/src/webx5/schemas/discount.py`
- [X] T043 [US5] Реализовать `GET /discounts`, `GET /discounts/{id}`, `GET /discount-types` routes (публичные) в `web/src/webx5/routes/discounts.py`
- [X] T044 [US6] Добавить `POST /discounts` и `PUT /discounts/{id}` routes с TerminalTokenDep в `web/src/webx5/routes/discounts.py`
- [X] T045 [US6] Зарегистрировать discounts_router в `web/src/webx5/core/server.py`

**Checkpoint**: `GET /stores` → список; `POST /stores` без токена → 401; `POST /stores` с токеном → 201; `GET /discounts` → только актуальные.

---

## Phase 7: Seed Scripts (данные для демо)

**Purpose**: Скрипты заполнения БД синтетическими данными из датасета. Зависят от Phase 1 (DB entities) и Phase 6 (stores/discounts repos существуют для upsert).

**⚠️ Порядок запуска**: `seed_products.py` → `seed_stores.py` → `seed_discounts.py` → `seed_receipts.py`

- [X] T049 Создать `web/scripts/seed_stores.py` — идемпотентно создаёт форматы сети (Пятёрочка, Перекрёсток, Чижик) и по одному дефолтному магазину на формат (geo_cluster='demo'); паттерн аналогичен `seed_products.py`
- [X] T050 Создать `web/scripts/seed_discounts.py` — читает JSONL (SEED_FILE_PATH), собирает уникальные пары (category_name, discount_pct) где discount_pct > 0, создаёт Discount-записи: discount_type='акция', link_type='category', entity_id=category.id (lookup по name), scope='all', valid_to=NULL; идемпотентен
- [X] T051 Создать `web/scripts/seed_receipts.py` — читает JSONL (SEED_FILE_PATH), обрабатывает до SEED_LIMIT пользователей (default=100, env-configurable), для каждого: upsert LoyaltyCard (user_id→id, chain→store_id lookup, district_id→geo_cluster), затем upsert Receipt (receipt_id как UUID, idempotency через IntegrityError), затем upsert ReceiptItems (sku_id→product lookup; on_promo→discount lookup по (category, discount_pct), NULL если не найдено; base_price_at_purchase=regular_unit_price_rub, paid_price=paid_unit_price_rub, discounted_amount=savings_rub)
- [X] T052 Добавить команды запуска seed-скриптов в `README.md` (аналогично секции «Заполнение каталога товарами»)

**Checkpoint**: После `seed_stores.py` → `seed_discounts.py` → `seed_receipts.py` (SEED_LIMIT=10): в БД есть loyalty_cards, receipts, receipt_items; GET /economy возвращает ненулевую экономию для тестового пользователя.

---

## Phase 8: Polish & Validation

**Purpose**: End-to-end проверка, unit-тесты ключевой бизнес-логики.

- [X] T053 [P] Написать unit-тесты для DiscountCalculatorService (best-price-wins, scope-фильтрация, expired-скидки) в `tests/webx5/services/test_discount_calculator.py`
- [X] T054 [P] Написать unit-тесты для ReceiptService (idempotency, 422 при истёкшей скидке, discounted_amount инвариант) в `tests/webx5/services/test_receipt_service.py`
- [X] T055 Прогнать сценарии из `specs/005-purchases-stores-discounts/quickstart.md` end-to-end с `docker compose up --build`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: Независима — начинать немедленно
- **Phase 2 (Foundational)**: Зависит от Phase 1 — блокирует US1, US2
- **Phase 3 (US1)**: Зависит от Phase 2
- **Phase 4 (US2)**: Зависит от Phase 2 + Phase 3 (discount_calculator_service)
- **Phase 5 (US3+US4)**: Зависит от Phase 4 (нужны записи в receipts)
- **Phase 6 (US5+US6)**: Зависит от Phase 1; **независима от Phase 2–5** (параллельно с US1–US4)
- **Phase 7 (Seed Scripts)**: Зависит от Phase 1 + Phase 6 (нужны store/discount repos); идеально — после Phase 6 полностью завершена
- **Phase 8 (Polish)**: Зависит от всех предыдущих фаз

### User Story Dependencies

- **US1 (P1)**: Depends on Phase 2 — нет зависимости от других US
- **US2 (P1)**: Depends on US1 (использует discount_calculator_service)
- **US3+US4 (P2)**: Depends on US2 (нужны чеки в БД)
- **US5 (P3)**: Depends on Phase 1 — нет зависимости от US1–US4
- **US6 (P3)**: Depends on US5 (расширяет те же routes)

### Parallel Opportunities

- Phase 1: T001–T004 можно параллельно
- Phase 6 (US5+US6) можно начать параллельно с Phase 3+4+5
- Внутри Phase 5: backend tasks (T018–T023) параллельно с mobile tasks (T024–T030)
- Внутри Phase 6: Stores tasks (T031–T037) параллельно с Discounts tasks (T038–T045)

---

## Parallel Example: Phase 5 (US3+US4)

```text
Backend track (запускать параллельно):
  T018: ReceiptRepository.list_by_loyalty_card + get_with_items
  T019: ReceiptRepository.get_economy_summary
  T020: Pydantic схемы ReceiptListItem, ReceiptDetailResponse
  T021: Pydantic схема EconomyResponse

Mobile track (запускать параллельно, после T018-T021):
  T024: useReceipts hook
  T025: useReceiptDetail hook
  T026: useEconomy hook
```

---

## Implementation Strategy

### MVP (US1 + US2 — кассовый flow)

1. Завершить Phase 1 (Setup)
2. Завершить Phase 2 (DiscountCalculatorService)
3. Завершить Phase 3 (POST /receipts/calculate)
4. Завершить Phase 4 (POST /receipts)
5. **STOP и VALIDATE**: Полный кассовый flow работает end-to-end
6. Демо: касса рассчитывает скидки и фиксирует покупку

### Incremental Delivery

1. Setup + Foundational → база готова
2. US1 + US2 → касса работает (MVP!)
3. US3 + US4 → пользователь видит историю и экономию
4. US5 + US6 → управление справочниками через API
5. Polish → тесты и финальная валидация

### Parallel Team Strategy

При двух разработчиках после Phase 1+2:
- Dev A: Phase 3 → Phase 4 → Phase 5 backend (US1 → US2 → US3/US4)
- Dev B: Phase 6 (US5 + US6) — независимо от Dev A
- После Phase 5 backend: Dev A и Dev B вместе делают Phase 5 mobile

---

## Notes

- [P] = разные файлы, нет незавершённых зависимостей — безопасно запускать параллельно
- [Story] — трассировка задачи к пользовательской истории
- Каждая US независимо тестируется на своём checkpoint
- Паттерн: сущность → repo → service → core wiring → route → server.py registration
- LoyaltyCard.id = User.id (PoC-упрощение, задокументировано в research.md R-004)
- Idempotency: IntegrityError на PK → rollback + SELECT существующего чека (R-001)
- best-price-wins: максимальный discount.value после scope- и date-фильтра (R-002)
