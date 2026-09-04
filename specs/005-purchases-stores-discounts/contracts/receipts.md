# API Contract: Receipts (Чеки)

**Auth**: `POST /receipts/calculate` и `POST /receipts` — `X-Terminal-Token` (TerminalTokenDep).
`GET /receipts*` и `GET /economy` — `Authorization: Bearer <access_token>` (CurrentUserUUID).

---

## POST /receipts/calculate

Предварительный расчёт скидок для корзины. Чек не создаётся.

**Auth**: X-Terminal-Token

**Request Body**:
```json
{
  "loyalty_card_id": "uuid | null",
  "store_id": "uuid",
  "items": [
    { "product_id": "uuid", "quantity": 2 }
  ]
}
```

**Response 200**:
```json
{
  "store_id": "uuid",
  "loyalty_card_id": "uuid | null",
  "items": [
    {
      "product_id": "uuid",
      "product_name": "string",
      "quantity": 2,
      "base_price": "199.90",
      "paid_price": "159.92",
      "discount_id": "uuid | null",
      "discounted_amount": "39.98"
    }
  ],
  "total_base": "399.80",
  "total_paid": "319.84",
  "total_saved": "79.96"
}
```

**Response 401**: Неверный X-Terminal-Token.

**Response 404**:
```json
{ "detail": "Store not found" }
```

**Response 422**:
```json
{
  "detail": "Unknown product_ids",
  "unknown_product_ids": ["uuid1", "uuid2"]
}
```

---

## POST /receipts

Фиксация чека. Идемпотентный: повторный запрос с тем же `X-Idempotency-Key` возвращает существующий чек.

**Auth**: X-Terminal-Token

**Headers**:
- `X-Idempotency-Key: <UUID>` — обязательный, генерируется кассой

**Request Body**:
```json
{
  "loyalty_card_id": "uuid | null",
  "store_id": "uuid",
  "channel": "offline",
  "payment_card_uid": "string | null",
  "items": [
    {
      "product_id": "uuid",
      "quantity": 2,
      "discount_id": "uuid | null"
    }
  ]
}
```

**Response 201** (новый чек) / **200** (дубль по idempotency key):
```json
{
  "id": "uuid",
  "purchase_date": "2026-09-04T10:30:00+03:00",
  "store_id": "uuid",
  "loyalty_card_id": "uuid | null",
  "channel": "offline",
  "items": [
    {
      "id": "uuid",
      "product_id": "uuid",
      "quantity": 2,
      "base_price_at_purchase": "199.90",
      "paid_price": "159.92",
      "discounted_amount": "39.98",
      "discount_id": "uuid | null"
    }
  ],
  "total_base": "399.80",
  "total_paid": "319.84",
  "total_saved": "79.96"
}
```

**Response 401**: Неверный X-Terminal-Token или отсутствует X-Idempotency-Key.

**Response 422**:
```json
{
  "detail": "Discount expired or not applicable",
  "invalid_items": [
    { "product_id": "uuid", "discount_id": "uuid", "reason": "discount_expired" }
  ]
}
```

---

## GET /receipts

Список чеков текущего пользователя.

**Auth**: Bearer

**Query params**: `page` (int, default 1), `size` (int, default 20)

**Response 200**:
```json
{
  "items": [
    {
      "id": "uuid",
      "purchase_date": "2026-09-04T10:30:00+03:00",
      "store_name": "Пятёрочка, р-н Хамовники",
      "total_base": "399.80",
      "total_paid": "319.84",
      "total_saved": "79.96",
      "items_count": 3
    }
  ],
  "total": 42,
  "page": 1,
  "size": 20
}
```

**Response 401**: Нет Bearer токена.

---

## GET /receipts/{receipt_id}

Детализация одного чека.

**Auth**: Bearer

**Response 200**:
```json
{
  "id": "uuid",
  "purchase_date": "2026-09-04T10:30:00+03:00",
  "store": { "id": "uuid", "format_name": "Пятёрочка", "geo_cluster": "Хамовники" },
  "channel": "offline",
  "items": [
    {
      "product_id": "uuid",
      "product_name": "Молоко Простоквашино",
      "quantity": 2,
      "base_price_at_purchase": "199.90",
      "paid_price": "159.92",
      "discounted_amount": "39.98",
      "discount_id": "uuid | null"
    }
  ],
  "total_base": "399.80",
  "total_paid": "319.84",
  "total_saved": "79.96"
}
```

**Response 401**: Нет Bearer токена.

**Response 403**: Чек принадлежит другому пользователю.

**Response 404**: Чек не найден.

---

## GET /economy

Суммарная экономия текущего пользователя.

**Auth**: Bearer

**Response 200**:
```json
{
  "total_saved": "1245.60",
  "receipts_count": 42
}
```

**Response 401**: Нет Bearer токена.
