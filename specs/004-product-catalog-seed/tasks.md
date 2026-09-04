# Tasks: Product Catalog and Seed Script

**Input**: Design documents from `specs/004-product-catalog-seed/`

**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/ ✅

**Organization**: Tasks grouped by user story for independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no cross-task dependencies)
- **[Story]**: User story label (US1–US4) from spec.md
- Tests included for service layer per Backend Technical Standards (constitution)

## Path conventions

All paths rooted at `/Users/pgdev/x5hack/` (repo root):

- Backend package: `web/src/webx5/`
- Tests mirror: `web/tests/webx5/`
- Scripts: `web/scripts/`
- Migrations: `web/alembic/versions/`

---

## Phase 1: Setup

**Purpose**: Add the single new dependency required by all user stories.

- [x] T001 Add `fastapi-pagination[sqlalchemy]` to `[tool.poetry.dependencies]` in `web/pyproject.toml` and run `poetry -C web lock --no-update` to update `poetry.lock`

**Checkpoint**: `poetry -C web install` succeeds; `import fastapi_pagination` works in the container.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Entities, migration, shared schemas, pagination dependency, repository and service — everything needed before any route is written.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [x] T002 [P] Create `Category` SQLAlchemy entity (`id: UUID PK`, `name: str UNIQUE NOT NULL`) in `web/src/webx5/entities/category.py`; register in `web/src/webx5/entities/__init__.py` so Alembic autodiscovers it
- [x] T003 [P] Create `Product` SQLAlchemy entity (`id: UUID PK`, `sku_id: str UNIQUE NOT NULL INDEX`, `name: str NOT NULL`, `current_price: Numeric(10,2) NOT NULL`, `category_id: UUID FK→categories`, `brand_id: UUID FK→brands nullable`) in `web/src/webx5/entities/product.py`; register in `web/src/webx5/entities/__init__.py`
- [x] T004 Generate Alembic migration for `categories` and `products` tables: `poetry -C web run alembic revision --autogenerate -m "add_catalog_tables"` → review and save output file under `web/alembic/versions/`
- [x] T005 [P] Create Pydantic read schemas — `CategoryResponse(id, name)` and `ProductResponse(id, sku_id, name, current_price, category: CategoryResponse)` — in `web/src/webx5/schemas/catalog.py` with `model_config = ConfigDict(from_attributes=True)`
- [x] T006 [P] Create reusable pagination params dependency using `fastapi_pagination.Params` in `web/src/webx5/dependencies/pagination.py`; set default `size=20`, `max_size=100`
- [x] T007 Create `CatalogRepository` in `web/src/webx5/crud/catalog.py` with methods: `get_all_categories(session)`, `get_products_query(session, category_id)` returning a SQLAlchemy select-statement (for use with `paginate()`), `get_product_by_sku(session, sku_id) → Product | None`, `get_or_create_category_by_name(session, name) → Category`
- [x] T008 Create `CatalogService` in `web/src/webx5/services/catalog.py` with constructor `__init__(self, repo: CatalogRepository)` and methods: `list_categories(session) → list[Category]`, `list_products(session, category_id) → Page[ProductResponse]`, `get_product_by_sku(session, sku_id) → Product` (raises `HTTPException(404)` if not found)

**Checkpoint**: All entities, schemas, repository and service exist; `poetry -C web run alembic upgrade head` applies without errors.

---

## Phase 3: User Story 1 — Просмотр каталога на мобильном устройстве (Priority: P1) 🎯 MVP

**Goal**: Авторизованный пользователь может получить список категорий и список товаров категории с пагинацией.

**Independent Test**: Выполни seed (Phase 5 checkpoint) → `GET /catalog/categories` возвращает категории; `GET /catalog/products?category_id=<id>&page=1&size=5` возвращает `{items, total, page, size, pages}`.

- [x] T009 Write unit tests for `CatalogService.list_categories` and `CatalogService.list_products` (mock `CatalogRepository`) in `web/tests/webx5/services/test_catalog.py`
- [ ] T010 [US1] Create `catalog_router = APIRouter(prefix="/catalog", tags=["Catalog"])` with `GET /catalog/categories` endpoint (auth: `CurrentUserUUID`, response: `list[CategoryResponse]`) in `web/src/webx5/routes/catalog.py`
- [ ] T011 [US1] Add `GET /catalog/products` endpoint to `web/src/webx5/routes/catalog.py` — params: optional `category_id: UUID | None`, `params: PaginationParams`; returns `Page[ProductResponse]` via `paginate(repo.get_products_query(...), params)`
- [ ] T012 [US1] Create `web/src/webx5/core/catalog.py` wiring file: instantiate `CatalogRepository()` and `CatalogService(repo=catalog_repo)` (mirrors pattern in `web/src/webx5/core/auth.py`)
- [ ] T013 [US1] Register `catalog_router` and call `add_pagination(app)` in `web/src/webx5/core/server.py` (add_pagination must be called AFTER all include_router calls)

**Checkpoint**: `GET /catalog/categories` with Bearer token returns `200 [{id, name}, ...]`; `GET /catalog/products?page=1&size=5` returns paginated response with `items`, `total`, `pages`.

---

## Phase 4: User Story 2 — Поиск товара кассовым аппаратом по SKU (Priority: P1)

**Goal**: Клиент (касса или мобильный) получает карточку товара по `sku_id` за один запрос; 404 если не найден.

**Independent Test**: `GET /catalog/products/sku_0001` → `200 {id, sku_id, name, current_price, category: {…}}`; `GET /catalog/products/sku_9999` → `404`.

- [ ] T014 [US2] Add unit test for `CatalogService.get_product_by_sku` (found case + 404 case) in `web/tests/webx5/services/test_catalog.py`
- [ ] T015 [US2] Add `GET /catalog/products/{sku_id}` endpoint (auth: `CurrentUserUUID`, response: `ProductResponse`, raises 404 via service) to `web/src/webx5/routes/catalog.py`

**Checkpoint**: Lookup by known SKU → 200 с вложенным category; несуществующий SKU → 404.

---

## Phase 5: User Story 3 — Импорт товаров из JSONL-файла (Priority: P2)

**Goal**: Оператор запускает скрипт, который идемпотентно наполняет БД товарами и категориями из JSONL.

**Independent Test**: Запустить скрипт с тестовым файлом из 5 строк → 5 товаров и нужные категории в БД; повторный запуск → счётчик `Imported: 0, Updated: 5`.

- [ ] T016 [US3] Create `web/scripts/` directory; add `web/scripts/seed_products.py` — reads `SEED_FILE_PATH` from env (via `python-dotenv`), iterates JSONL line-by-line, validates required fields (`sku_id`, `item`, `category`, `regular_unit_price_rub > 0`), calls `get_or_create_category_by_name` then executes PostgreSQL UPSERT via `sqlalchemy.dialects.postgresql.insert(...).on_conflict_do_update(index_elements=["sku_id"], set_={"name": ..., "current_price": ..., "category_id": ...})`, prints per-row warnings and final `Imported/Updated/Skipped` summary; uses `db.get_sync_session()` from `core/db.py`

**Checkpoint**: Seed script exits 0; categories and products exist in DB; re-run → no new rows added.

---

## Phase 6: User Story 4 — Управление каталогом кассовым аппаратом (Priority: P3)

**Goal**: Аутентифицированный кассовый аппарат (X-Terminal-Token) может создавать, обновлять и удалять товары и категории через API.

**Independent Test**: `POST /catalog/products` с terminal token → 201; `GET /catalog/products/{sku_id}` → 200; `PUT` → обновлённая цена; `DELETE` → 204, последующий `GET` → 404.

- [ ] T017 [P] [US4] Add write schemas to `web/src/webx5/schemas/catalog.py`: `CategoryCreate(name: str)`, `ProductCreate(sku_id, name, current_price: Decimal > 0, category_id: UUID, brand_id: UUID | None = None)`, `ProductUpdate(name, current_price, category_id, brand_id — все optional)`
- [ ] T018 [P] [US4] Add write repository methods to `web/src/webx5/crud/catalog.py`: `create_category(session, name) → Category` (409 if duplicate), `create_product(session, data) → Product` (409 if sku_id duplicate, 404 if category_id missing), `update_product(session, sku_id, data) → Product` (404 if not found), `delete_product(session, sku_id)` (404 if not found)
- [ ] T019 [US4] Add write service methods to `web/src/webx5/services/catalog.py`: `create_category`, `create_product`, `update_product`, `delete_product` — делегируют в репозиторий, пробрасывают HTTPException
- [ ] T020 [P] [US4] Add `POST /catalog/categories` endpoint (auth: `TerminalTokenDep`, status 201) to `web/src/webx5/routes/catalog.py`
- [ ] T021 [P] [US4] Add `POST /catalog/products` endpoint (auth: `TerminalTokenDep`, status 201) to `web/src/webx5/routes/catalog.py`
- [ ] T022 [P] [US4] Add `PUT /catalog/products/{sku_id}` endpoint (auth: `TerminalTokenDep`, response: `ProductResponse`) to `web/src/webx5/routes/catalog.py`
- [ ] T023 [P] [US4] Add `DELETE /catalog/products/{sku_id}` endpoint (auth: `TerminalTokenDep`, status 204) to `web/src/webx5/routes/catalog.py`

**Checkpoint**: Все 4 write-операции работают с корректным terminal token; без token → 401; дублирующий sku_id → 409.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [ ] T024 Write integration tests for catalog routes (seed test DB, assert status codes and response shapes) in `web/tests/webx5/routes/test_catalog.py`
- [ ] T025 Run end-to-end validation against quickstart.md checklist (`specs/004-product-catalog-seed/quickstart.md`)
- [ ] T026 [P] Run lint and format on all new catalog files: `poetry -C web/src/tooling run ruff format ../webx5/entities/category.py ../webx5/entities/product.py ../webx5/crud/catalog.py ../webx5/services/catalog.py ../webx5/routes/catalog.py ../webx5/schemas/catalog.py ../webx5/dependencies/pagination.py ../webx5/core/catalog.py` and `ruff check --fix` on same files

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: Без зависимостей — стартуем сразу
- **Foundational (Phase 2)**: Зависит от Phase 1 — блокирует все user story фазы
- **US1 (Phase 3)**: Зависит от Phase 2 — можно стартовать как только Phase 2 завершён
- **US2 (Phase 4)**: Зависит от Phase 2 (+ Phase 3 частично, т.к. работают в одном routes-файле)
- **US3 (Phase 5)**: Зависит от Phase 2 только (seed script не использует routes)
- **US4 (Phase 6)**: Зависит от Phase 3 (routes file уже создан)
- **Polish (Phase 7)**: Зависит от завершения всех нужных user story

### User Story Dependencies

- **US1 (P1)**: Стартует после Phase 2. Независим от US2/US3/US4.
- **US2 (P1)**: Стартует после Phase 3 (добавляет endpoint в уже созданный routes-файл). Независим от US3/US4.
- **US3 (P2)**: Стартует после Phase 2. Полностью независим от US1/US2/US4 (другой файл).
- **US4 (P3)**: Стартует после Phase 3. Независим от US2/US3.

### Parallel Opportunities

```bash
# Phase 2: параллельно
Task: T002  # entities/category.py
Task: T003  # entities/product.py
Task: T005  # schemas/catalog.py (read schemas)
Task: T006  # dependencies/pagination.py

# После T002 + T003: T004 (migration), T007 (crud), T008 (service)

# US3 и US1 можно вести параллельно после Phase 2:
Developer A: T009 → T010 → T011 → T012 → T013  (US1)
Developer B: T016                                 (US3, seed script)

# US4: параллельно внутри фазы
Task: T017  # schemas write
Task: T018  # crud write methods
# затем: T019, T020 [P], T021 [P], T022 [P], T023 [P]
```

---

## Implementation Strategy

### MVP First (User Story 1 + 2)

1. ✅ Phase 1: Add dependency
2. ✅ Phase 2: Foundational (entities, migration, schemas, repo, service)
3. ✅ Phase 3: US1 — browse catalog (GET categories + GET products)
4. ✅ Phase 4: US2 — SKU lookup
5. **STOP & VALIDATE**: Запусти seed script (Phase 5) чтобы наполнить данными, проверь quickstart сценарии 4–6
6. Demo ready — мобильный клиент и касса читают каталог

### Incremental Delivery

1. Setup + Foundational → база готова
2. US1 → листинг каталога на мобильном (MVP!)
3. US2 → SKU-lookup для кассы (MVP+ для чеков)
4. US3 → seed script (нужен для наполнения демо-данными)
5. US4 → write API для кассы (расширенный функционал)
6. Polish → тесты, lint, quickstart-чеклист

---

## Notes

- Все [P]-таски работают с разными файлами и не конфликтуют
- `add_pagination(app)` ОБЯЗАТЕЛЬНО вызывается ПОСЛЕ всех `app.include_router(...)` в `server.py`
- Seed script использует `db.get_sync_session()` из `core/db.py` — не создаёт новый движок
- `TerminalTokenDep` уже реализован в `dependencies/auth.py` — импортировать, не переписывать
- `CurrentUserUUID` аналогично уже готов в `dependencies/auth.py`
- UPSERT seed script: `from sqlalchemy.dialects.postgresql import insert` — не `session.merge()`
