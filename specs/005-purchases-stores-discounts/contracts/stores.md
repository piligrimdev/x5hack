# API Contract: Stores (Магазины)

**Auth**: GET — публичный (без аутентификации). POST/PUT — `X-Terminal-Token`.

---

## GET /stores

Список магазинов. Публичный.

**Response 200**:
```json
[
  {
    "id": "uuid",
    "format_id": "uuid",
    "format_name": "Пятёрочка",
    "geo_cluster": "Хамовники"
  }
]
```

---

## GET /stores/{store_id}

**Response 200**:
```json
{
  "id": "uuid",
  "format_id": "uuid",
  "format_name": "Пятёрочка",
  "geo_cluster": "Хамовники"
}
```

**Response 404**: Магазин не найден.

---

## POST /stores

**Auth**: X-Terminal-Token

**Request Body**:
```json
{
  "format_id": "uuid",
  "geo_cluster": "Хамовники",
  "address": "ул. Пречистенка, 1"
}
```

**Response 201**:
```json
{
  "id": "uuid",
  "format_id": "uuid",
  "format_name": "Пятёрочка",
  "geo_cluster": "Хамовники"
}
```

**Response 401**: Неверный X-Terminal-Token.

**Response 422**: Невалидный format_id.

---

## PUT /stores/{store_id}

**Auth**: X-Terminal-Token

**Request Body**: те же поля что в POST (все опциональны).

**Response 200**: обновлённый магазин.

**Response 401**: Неверный X-Terminal-Token.

**Response 404**: Магазин не найден.

---

## GET /store-formats

Список форматов сети. Публичный.

**Response 200**:
```json
[
  { "id": "uuid", "name": "Пятёрочка" },
  { "id": "uuid", "name": "Перекрёсток" },
  { "id": "uuid", "name": "Чижик" }
]
```
