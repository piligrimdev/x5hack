# API Contract: Discounts (Скидки)

**Auth**: GET — публичный. POST/PUT — `X-Terminal-Token`.

---

## GET /discounts

Список актуальных скидок (valid_from ≤ now ≤ valid_to или valid_to = NULL). Публичный.

**Query params**:
- `entity_id` (uuid, optional) — фильтр по entity_id
- `link_type` (string, optional) — `product`, `category`, `brand`

**Response 200**:
```json
[
  {
    "id": "uuid",
    "value": "20.00",
    "discount_type": "акция",
    "link_type": "product",
    "entity_id": "uuid",
    "scope": "all",
    "valid_from": "2026-09-01T00:00:00+03:00",
    "valid_to": "2026-09-30T23:59:59+03:00"
  }
]
```

---

## GET /discounts/{discount_id}

**Response 200**: Одна скидка (те же поля).

**Response 404**: Скидка не найдена.

---

## POST /discounts

**Auth**: X-Terminal-Token

**Request Body**:
```json
{
  "value": 20.0,
  "discount_type_id": "uuid",
  "link_type_id": "uuid",
  "entity_id": "uuid",
  "scope": "all",
  "valid_from": "2026-09-01T00:00:00+03:00",
  "valid_to": "2026-09-30T23:59:59+03:00",
  "store_ids": [],
  "format_ids": []
}
```

`store_ids` — массив UUID для `scope = 'by_store'`.
`format_ids` — массив UUID для `scope = 'by_format'`.

**Response 201**: созданная скидка.

**Response 401**: Неверный X-Terminal-Token.

**Response 422**: Невалидные значения (value > 100, неверный scope).

---

## PUT /discounts/{discount_id}

**Auth**: X-Terminal-Token

**Request Body**: те же поля что в POST (все опциональны).

**Response 200**: обновлённая скидка.

**Response 401**: Неверный X-Terminal-Token.

**Response 404**: Скидка не найдена.

---

## GET /discount-types

Справочник типов скидок. Публичный.

**Response 200**:
```json
[
  { "id": "uuid", "name": "акция" },
  { "id": "uuid", "name": "лояльность" },
  { "id": "uuid", "name": "персональная" },
  { "id": "uuid", "name": "уценка" }
]
```
