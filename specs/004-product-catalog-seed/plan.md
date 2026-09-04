# Implementation Plan: Product Catalog and Seed Script

**Branch**: `004-product-catalog-seed` | **Date**: 2026-09-04 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/004-product-catalog-seed/spec.md`

---

## Summary

Реализуем справочник товаров и категорий: REST API для просмотра (мобильный клиент, кассовый аппарат), CRUD-управление каталогом через кассовый аппарат (terminal token), и seed-скрипт для первичного наполнения БД из JSONL-файла. Пагинация через `fastapi-pagination` реализована как переиспользуемая зависимость.

---

## Technical Context

**Language/Version**: Python 3.12

**Primary Dependencies**:
- FastAPI 0.115, SQLAlchemy 2.x (sync), Pydantic v2, structlog
- `fastapi-pagination[sqlalchemy]` — добавляется в `web/pyproject.toml`

**Storage**: PostgreSQL (существующий, через SQLAlchemy sync engine)

**Testing**: pytest + httpx (существующие)

**Target Platform**: Linux server (Docker, `docker compose up`)

**Project Type**: Web service (REST API), дополнительно standalone script

**Performance Goals**: Отклик каталога < 200ms при демо-нагрузке (одиночные запросы)

**Constraints**: Seed script — идемпотентный, UPSERT-based; пагинация — max_size=100

**Scale/Scope**: ~1000 товаров, ~20–30 категорий (демо-стенд)

---

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Принцип | Статус | Комментарий |
|---------|--------|-------------|
| I. Экономия как единая метрика | ✅ Pass | Каталог — инфраструктура. Не создаёт новых абстрактных механик |
| II. Минимальный когнитивный барьер | ✅ Pass | API-фича, UI не затрагивается |
| III. ИИ-персонализация | ✅ Pass | Не применимо к каталогу |
| IV. Экономическая обоснованность | ✅ Pass | Инфраструктурная фича, не игровая механика |
| V. Privacy by Design | ✅ Pass | Каталог не содержит PII |
| Backend RSI | ✅ Pass | Отдельные crud/, services/, routes/ в пакете webx5 |
| DI | ✅ Pass | CatalogService получает CatalogRepository через аргументы |
| Poetry | ✅ Pass | Все зависимости через `web/pyproject.toml` |
| Логирование | ✅ Pass | Сервис — structlog; seed-скрипт — print (по правилам) |

**Нет нарушений.** Complexity Tracking не требуется.

---

## Project Structure

### Documentation (this feature)

```text
specs/004-product-catalog-seed/
├── plan.md              ← этот файл
├── research.md          ← Phase 0 ✅
├── data-model.md        ← Phase 1 ✅
├── contracts/
│   ├── api.md           ← Phase 1 ✅
│   └── seed-script.md   ← Phase 1 ✅
├── quickstart.md        ← Phase 1 ✅
├── checklists/
│   └── requirements.md
└── tasks.md             ← Phase 2 (/speckit-tasks — не создаётся этой командой)
```

### Source Code (repository)

```text
web/
├── pyproject.toml                    # + fastapi-pagination[sqlalchemy]
├── scripts/
│   └── seed_products.py              # Seed script (NEW)
├── alembic/
│   └── versions/
│       └── XXXX_add_catalog_tables.py  # Alembic migration (NEW)
└── src/webx5/
    ├── core/
    │   └── server.py                 # + include catalog_router + add_pagination(app)
    ├── entities/
    │   ├── category.py               # Category SQLAlchemy entity (NEW)
    │   └── product.py                # Product SQLAlchemy entity (NEW)
    ├── crud/
    │   └── catalog.py                # CategoryRepository, ProductRepository (NEW)
    ├── services/
    │   └── catalog.py                # CatalogService (NEW)
    ├── routes/
    │   └── catalog.py                # catalog_router: GET + write endpoints (NEW)
    ├── schemas/
    │   └── catalog.py                # CategoryResponse, ProductResponse, create/update schemas (NEW)
    └── dependencies/
        └── pagination.py             # PaginationParams reusable Depends (NEW)

tests/webx5/
├── services/
│   └── test_catalog.py              # Unit tests for CatalogService (NEW)
└── routes/
    └── test_catalog.py              # Integration tests for catalog routes (NEW)
```

**Structure Decision**: Расширяем существующий пакет `webx5` по сложившейся RSI-структуре. Seed-скрипт вынесен в `web/scripts/` — отдельная директория вне пакета, как предписывают правила проекта.

---

## Implementation Notes (for tasks phase)

### Порядок реализации

1. **Entities + Migration**: `category.py`, `product.py` → Alembic migration
2. **Pagination dependency**: `dependencies/pagination.py` + `add_pagination(app)` в server.py
3. **Repository (crud)**: `CategoryRepository`, `ProductRepository` с методами get_all, get_by_id, get_by_sku, create, upsert, update, delete
4. **Schemas**: `CategoryResponse`, `ProductResponse`, `ProductCreate`, `ProductUpdate`, `CategoryCreate`
5. **Service**: `CatalogService` с бизнес-логикой (проверка category_id при создании товара, 404/409)
6. **Routes**: `catalog_router` — GET-эндпоинты (CurrentUserUUID) + write-эндпоинты (TerminalTokenDep)
7. **Wiring**: `core/server.py`, `core/catalog.py` (инстанс service)
8. **Seed script**: `web/scripts/seed_products.py`
9. **Tests**: unit (CatalogService), integration (routes)

### Pagination wiring (key detail)

```python
# server.py
from fastapi_pagination import add_pagination
from webx5.routes.catalog import catalog_router

app.include_router(catalog_router)
add_pagination(app)  # обязательно ПОСЛЕ include_router
```

```python
# routes/catalog.py — пример использования
from fastapi_pagination import Page
from fastapi_pagination.ext.sqlalchemy import paginate

@catalog_router.get("/products", response_model=Page[ProductResponse])
def list_products(
    category_id: UUID | None = None,
    session: SessionDep,
    _user_id: CurrentUserUUID,
) -> Page[ProductResponse]:
    return catalog_service.list_products(session, category_id)
```

### UPSERT в seed script

```python
from sqlalchemy.dialects.postgresql import insert

stmt = insert(Product).values(**product_data)
stmt = stmt.on_conflict_do_update(
    index_elements=["sku_id"],
    set_={"name": stmt.excluded.name, "current_price": stmt.excluded.current_price, "category_id": stmt.excluded.category_id}
)
session.execute(stmt)
```
