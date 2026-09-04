# Data Model: Product Catalog

**Branch**: `004-product-catalog-seed` | **Date**: 2026-09-04

---

## Entities

### Category

**Table**: `categories`

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | UUID | PK, default=uuid4 | Внутренний идентификатор |
| `name` | VARCHAR(255) | UNIQUE, NOT NULL, INDEX | Название категории (точное совпадение при поиске) |

**SQLAlchemy entity**: `web/src/webx5/entities/category.py`

**Uniqueness**: Имя категории уникально. При seed-импорте — INSERT ... ON CONFLICT (name) DO NOTHING.

---

### Product

**Table**: `products`

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | UUID | PK, default=uuid4 | Внутренний идентификатор |
| `sku_id` | VARCHAR(50) | UNIQUE, NOT NULL, INDEX | Внешний идентификатор товара (из источника данных) |
| `name` | VARCHAR(500) | NOT NULL | Название товара |
| `current_price` | NUMERIC(10, 2) | NOT NULL, CHECK > 0 | Актуальная полочная цена в рублях |
| `category_id` | UUID | FK → categories.id, NOT NULL | Принадлежность к категории |
| `brand_id` | UUID | FK → brands.id, NULL | Бренд товара (NULL если не задан) |

**SQLAlchemy entity**: `web/src/webx5/entities/product.py`

**Uniqueness**: `sku_id` уникален. При seed-импорте — INSERT ... ON CONFLICT (sku_id) DO UPDATE name, current_price, category_id.

**Note**: `brands` таблица и связь `brand_id` уже ожидаются в схеме БД (из `context/schema.md`). Данная фича только добавляет `categories` и `products`.

---

## Relations

```
categories
  └── products (category_id → categories.id, NOT NULL)

brands (existing or future)
  └── products (brand_id → brands.id, nullable)
```

---

## Alembic Migration

**File**: `web/alembic/versions/XXXX_add_catalog_tables.py`

Создаёт в порядке: `categories` → `products` (из-за FK зависимости).

```python
# Pseudo-DDL

CREATE TABLE categories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL UNIQUE
);
CREATE INDEX ix_categories_name ON categories(name);

CREATE TABLE products (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sku_id VARCHAR(50) NOT NULL UNIQUE,
    name VARCHAR(500) NOT NULL,
    current_price NUMERIC(10, 2) NOT NULL,
    category_id UUID NOT NULL REFERENCES categories(id),
    brand_id UUID REFERENCES brands(id)  -- nullable
);
CREATE INDEX ix_products_sku_id ON products(sku_id);
CREATE INDEX ix_products_category_id ON products(category_id);
```

---

## JSONL → DB Field Mapping

| JSONL field | DB column | Notes |
|---|---|---|
| `sku_id` | `products.sku_id` | Уникальный ключ для UPSERT |
| `item` | `products.name` | |
| `regular_unit_price_rub` | `products.current_price` | Только > 0 |
| `category` | `categories.name` → `products.category_id` | Lookup/create по имени |
| `unit_cost_rub` | — | Не хранится в PoC |
| `gross_margin_rub` | — | Не хранится в PoC |

---

## Pydantic Schemas

### CategoryResponse
```
id: UUID
name: str
```

### ProductResponse
```
id: UUID
sku_id: str
name: str
current_price: Decimal
category: CategoryResponse   # вложенный объект, не category_id
```

### ProductCreate (write endpoint)
```
sku_id: str
name: str
current_price: Decimal  (> 0)
category_id: UUID
brand_id: UUID | None = None
```

### ProductUpdate (write endpoint)
```
name: str | None = None
current_price: Decimal | None = None   (> 0 если задано)
category_id: UUID | None = None
brand_id: UUID | None = None
```

### CategoryCreate (write endpoint)
```
name: str
```

### PaginatedProductResponse
```
Page[ProductResponse]  # fastapi-pagination: items, total, page, size, pages
```
