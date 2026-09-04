# API Contract: Product Catalog

**Base path**: `/catalog`
**Auth**:
- Read (GET): `Authorization: Bearer <access_token>` (JWT)
- Write (POST/PUT/DELETE): `X-Terminal-Token: <terminal_secret>` (env `TERMINAL_TOKEN`)

---

## Read Endpoints

### GET /catalog/categories

Список всех категорий.

**Auth**: JWT Bearer (CurrentUserUUID)

**Response 200**:
```json
[
  { "id": "uuid", "name": "молочные продукты и яйца" },
  { "id": "uuid", "name": "хлебобулочные изделия" }
]
```

**Errors**: `401` — отсутствует или невалидный токен.

---

### GET /catalog/products

Список товаров с фильтрацией по категории и пагинацией.

**Auth**: JWT Bearer (CurrentUserUUID)

**Query params**:
| Param | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `category_id` | UUID | No | — | Фильтр по категории |
| `page` | int | No | 1 | Номер страницы (начиная с 1) |
| `size` | int | No | 20 | Размер страницы (1–100) |

**Response 200**:
```json
{
  "items": [
    {
      "id": "uuid",
      "sku_id": "sku_0042",
      "name": "Молоко 2,5%",
      "current_price": "135.79",
      "category": { "id": "uuid", "name": "молочные продукты и яйца" }
    }
  ],
  "total": 142,
  "page": 1,
  "size": 20,
  "pages": 8
}
```

**Errors**: `401` — невалидный токен.

---

### GET /catalog/products/{sku_id}

Карточка товара по SKU.

**Auth**: JWT Bearer (CurrentUserUUID)

**Path param**: `sku_id` — строка, например `sku_0042`

**Response 200**:
```json
{
  "id": "uuid",
  "sku_id": "sku_0042",
  "name": "Молоко 2,5%",
  "current_price": "135.79",
  "category": { "id": "uuid", "name": "молочные продукты и яйца" }
}
```

**Errors**:
- `401` — невалидный токен
- `404` — товар с таким SKU не найден

---

## Write Endpoints (Terminal Only)

### POST /catalog/categories

Создать категорию.

**Auth**: `X-Terminal-Token` (TerminalTokenDep)

**Request body**:
```json
{ "name": "замороженные продукты" }
```

**Response 201**:
```json
{ "id": "uuid", "name": "замороженные продукты" }
```

**Errors**:
- `401` — неверный terminal token
- `409` — категория с таким именем уже существует

---

### POST /catalog/products

Создать товар.

**Auth**: `X-Terminal-Token` (TerminalTokenDep)

**Request body**:
```json
{
  "sku_id": "sku_9999",
  "name": "Кефир 1%",
  "current_price": 89.90,
  "category_id": "uuid",
  "brand_id": null
}
```

**Response 201**:
```json
{
  "id": "uuid",
  "sku_id": "sku_9999",
  "name": "Кефир 1%",
  "current_price": "89.90",
  "category": { "id": "uuid", "name": "молочные продукты и яйца" }
}
```

**Errors**:
- `401` — неверный terminal token
- `404` — category_id не найден
- `409` — sku_id уже существует

---

### PUT /catalog/products/{sku_id}

Обновить товар.

**Auth**: `X-Terminal-Token` (TerminalTokenDep)

**Request body** (все поля опциональны):
```json
{
  "name": "Кефир обезжиренный",
  "current_price": 79.90
}
```

**Response 200**: обновлённая `ProductResponse`

**Errors**:
- `401` — неверный terminal token
- `404` — товар не найден
- `404` — category_id (если передан) не найден

---

### DELETE /catalog/products/{sku_id}

Удалить товар.

**Auth**: `X-Terminal-Token` (TerminalTokenDep)

**Response 204**: No content

**Errors**:
- `401` — неверный terminal token
- `404` — товар не найден

---

## Router wiring (server.py)

```python
from webx5.routes.catalog import catalog_router
app.include_router(catalog_router)
```

`catalog_router = APIRouter(prefix="/catalog", tags=["Catalog"])`
