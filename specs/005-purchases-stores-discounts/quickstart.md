# Quickstart & Validation Guide: Покупки, магазины и скидки

**Branch**: `005-purchases-stores-discounts` | **Date**: 2026-09-04

## Предварительные требования

- Docker Desktop запущен
- `cp .env.example .env` (значения по умолчанию работают)
- `TERMINAL_TOKEN=test-terminal-token` добавлен в `.env`

## Запуск

```bash
docker compose up --build
```

После запуска: `curl http://localhost:8000/health` → `{"status":"ok"}`

---

## Сценарий 1: Создание справочников (касса)

### 1.1 Создать формат сети

```bash
curl -X POST http://localhost:8000/store-formats \
  -H "X-Terminal-Token: test-terminal-token" \
  -H "Content-Type: application/json" \
  -d '{"name": "Пятёрочка"}'
# → 201, { "id": "<format_id>", "name": "Пятёрочка" }
```

### 1.2 Создать магазин

```bash
curl -X POST http://localhost:8000/stores \
  -H "X-Terminal-Token: test-terminal-token" \
  -H "Content-Type: application/json" \
  -d '{"format_id": "<format_id>", "geo_cluster": "Хамовники", "address": "ул. Пречистенка, 1"}'
# → 201, { "id": "<store_id>", "format_name": "Пятёрочка", "geo_cluster": "Хамовники" }
```

### 1.3 Создать скидку (акция, скидка 20% на продукт)

```bash
curl -X POST http://localhost:8000/discounts \
  -H "X-Terminal-Token: test-terminal-token" \
  -H "Content-Type: application/json" \
  -d '{
    "value": 20.0,
    "discount_type_id": "<discount_type_акция_id>",
    "link_type_id": "<discount_link_type_product_id>",
    "entity_id": "<product_id>",
    "scope": "all",
    "valid_from": null,
    "valid_to": null,
    "store_ids": [],
    "format_ids": []
  }'
# → 201, { "id": "<discount_id>", "value": "20.00", ... }
```

**Ожидаемый результат**: магазин и скидка появляются в `GET /stores` и `GET /discounts`.

---

## Сценарий 2: Расчёт скидок (касса)

### 2.1 Зарегистрировать покупателя (если нужна привязка карты)

```bash
curl -X POST http://localhost:8000/register \
  -H "Content-Type: application/json" \
  -d '{"phone": "+79001234567", "password": "testpass123"}'
# → { "access_token": "...", "refresh_token": "..." }
# loyalty_card_id = user.id из JWT payload
```

### 2.2 Запросить расчёт скидок

```bash
curl -X POST http://localhost:8000/receipts/calculate \
  -H "X-Terminal-Token: test-terminal-token" \
  -H "Content-Type: application/json" \
  -d '{
    "loyalty_card_id": "<user_id>",
    "store_id": "<store_id>",
    "items": [
      { "product_id": "<product_id>", "quantity": 2 }
    ]
  }'
```

**Ожидаемый результат**:
```json
{
  "items": [{
    "product_id": "...",
    "base_price": "199.90",
    "paid_price": "159.92",
    "discount_id": "<discount_id>",
    "discounted_amount": "39.98"
  }],
  "total_saved": "79.96"
}
```

Проверить: `paid_price = base_price * 0.80`, `discounted_amount = base_price - paid_price`.

---

## Сценарий 3: Фиксация чека (идемпотентность)

### 3.1 Первый запрос — создание чека

```bash
RECEIPT_UUID=$(python3 -c "import uuid; print(uuid.uuid4())")

curl -X POST http://localhost:8000/receipts \
  -H "X-Terminal-Token: test-terminal-token" \
  -H "X-Idempotency-Key: $RECEIPT_UUID" \
  -H "Content-Type: application/json" \
  -d '{
    "loyalty_card_id": "<user_id>",
    "store_id": "<store_id>",
    "channel": "offline",
    "items": [
      { "product_id": "<product_id>", "quantity": 2, "discount_id": "<discount_id>" }
    ]
  }'
# → 201, { "id": "$RECEIPT_UUID", "total_saved": "79.96", ... }
```

### 3.2 Повторный запрос — идемпотентность

```bash
curl -X POST http://localhost:8000/receipts \
  -H "X-Terminal-Token: test-terminal-token" \
  -H "X-Idempotency-Key: $RECEIPT_UUID" \
  -H "Content-Type: application/json" \
  -d '{ /* same body */ }'
# → 200, тот же чек (не создаётся дубль)
```

**Проверить**: в БД ровно одна строка с `id = $RECEIPT_UUID`.

---

## Сценарий 4: Просмотр покупок (пользователь)

### 4.1 Список чеков

```bash
curl http://localhost:8000/receipts \
  -H "Authorization: Bearer <access_token>"
# → { "items": [...], "total": 1 }
```

### 4.2 Детализация чека

```bash
curl http://localhost:8000/receipts/$RECEIPT_UUID \
  -H "Authorization: Bearer <access_token>"
# → полный чек с позициями
```

### 4.3 Суммарная экономия

```bash
curl http://localhost:8000/economy \
  -H "Authorization: Bearer <access_token>"
# → { "total_saved": "79.96", "receipts_count": 1 }
```

**Проверить**: `total_saved` совпадает с суммой `discounted_amount` по всем позициям чека.

---

## Сценарий 5: Проверка ошибок

### 5.1 Истёкшая скидка

Создать скидку с `valid_to` в прошлом, попытаться зафиксировать чек с ней.
```
→ 422, { "detail": "Discount expired or not applicable", "invalid_items": [...] }
```

### 5.2 Несуществующий product_id

```bash
curl -X POST http://localhost:8000/receipts/calculate \
  -H "X-Terminal-Token: test-terminal-token" \
  -d '{"store_id": "...", "items": [{"product_id": "00000000-0000-0000-0000-000000000000", "quantity": 1}]}'
# → 422, { "detail": "Unknown product_ids", "unknown_product_ids": [...] }
```

### 5.3 Доступ пользователя к чужому чеку

```bash
curl http://localhost:8000/receipts/$RECEIPT_UUID \
  -H "Authorization: Bearer <other_user_token>"
# → 403
```

### 5.4 Создание магазина без токена

```bash
curl -X POST http://localhost:8000/stores -d '{"format_id": "...", "geo_cluster": "test"}'
# → 401
```

---

## Артефакты для проверки

- [data-model.md](data-model.md) — схема БД
- [contracts/receipts.md](contracts/receipts.md) — контракт чеков
- [contracts/stores.md](contracts/stores.md) — контракт магазинов
- [contracts/discounts.md](contracts/discounts.md) — контракт скидок
