# User Flow: Покупка end-to-end

## Участники

- **Касса** — авторизуется статичным `X-Terminal-Token` (env-переменная)
- **Пользователь** — авторизуется через Bearer JWT (`POST /login` с номером телефона)

### Идентификация пользователя

`user.id == loyalty_card_id` — один и тот же UUID. При регистрации автоматически создаётся запись в `loyalty_cards` с тем же `id`. Касса передаёт `loyalty_card_id` из JWT пользователя.

У пользователя есть `loyalty_level` (целое число, по умолчанию 1). Уровень влияет на доступные скидки.

---

## Фаза 1 — Касса: расчёт корзины

```
POST /receipts/calculate
X-Terminal-Token: <secret>

{
  "store_id": "<uuid магазина>",
  "loyalty_card_id": "<user.id или null для анонимной покупки>",
  "items": [
    { "product_id": "<uuid>", "quantity": 2 },
    { "product_id": "<uuid>", "quantity": 1 }
  ]
}
```

Сервер возвращает итоговые цены по каждому товару:

```json
{
  "store_id": "...",
  "loyalty_card_id": "...",
  "total_base": 450.00,
  "total_paid": 382.50,
  "total_saved": 67.50,
  "items": [
    {
      "product_id": "...",
      "product_name": "Молоко 2,5%",
      "quantity": 2,
      "base_price": 135.79,
      "paid_price": 115.42,
      "discount_id": "<uuid скидки>",
      "discounted_amount": 20.37
    }
  ]
}
```

Все числовые поля возвращаются как `float`. Касса показывает покупателю финальные цены. **`discount_id` каждого товара сохраняется** — он понадобится при фиксации чека.

---

## Фаза 2 — Касса: фиксация чека

После оплаты касса отправляет чек. UUID в `X-Idempotency-Key` генерируется кассой заранее (до попытки оплаты) — при сетевом сбое можно безопасно повторить запрос.

```
POST /receipts
X-Terminal-Token: <secret>
X-Idempotency-Key: <uuid, сгенерированный кассой>

{
  "store_id": "<uuid>",
  "loyalty_card_id": "<user.id или null>",
  "channel": "offline",
  "payment_card_uid": "****1234",
  "items": [
    { "product_id": "<uuid>", "quantity": 2, "discount_id": "<uuid из /calculate>" },
    { "product_id": "<uuid>", "quantity": 1, "discount_id": null }
  ]
}
```

| Статус | Значение |
|--------|----------|
| **201** | Чек создан впервые |
| **200** | Чек уже существует с таким `X-Idempotency-Key` (повтор после сбоя) |
| **422** | Скидка истекла между `/calculate` и `/receipts` — касса должна пересчитать |

В БД записывается:
- `base_price_at_purchase` — `product.current_price` на момент покупки (снапшот, не ссылка)
- `paid_price` — цена после скидки
- `discounted_amount` — разница

---

## Фаза 3 — Пользователь: просмотр в приложении

```
GET /receipts          Authorization: Bearer <jwt>   — список чеков (пагинация)
GET /receipts/{id}     Authorization: Bearer <jwt>   — детализация конкретного чека
GET /receipts/economy  Authorization: Bearer <jwt>   — суммарная экономия
```

Доступ ограничен: сервер проверяет `receipt.loyalty_card_id == current_user_id`. Чужой чек → 403.

`GET /receipts/economy` возвращает:
```json
{
  "total_saved": 312.50,
  "total_paid": 4187.50,
  "receipts_count": 14
}
```

---

## Механизм выбора скидки (best-price-wins)

### Шаг 1 — Сбор кандидатов

Для всех товаров в корзине собираются `entity_id`:
- `product_id` каждого товара
- `category_id` каждого товара
- `brand_id` каждого товара (если есть)

Два SQL-запроса:

```sql
-- Скидки на конкретные сущности
SELECT * FROM discounts
WHERE entity_id IN (<все id>)
  AND (valid_from IS NULL OR valid_from <= now)
  AND (valid_to   IS NULL OR valid_to   >= now)

-- Скидки типа "all" — на все товары без привязки к сущности
SELECT * FROM discounts
WHERE link_type_id = <id записи "all" в discount_link_types>
  AND (valid_from IS NULL OR valid_from <= now)
  AND (valid_to   IS NULL OR valid_to   >= now)
```

### Шаг 2 — Фильтрация по scope

| scope | Условие применения |
|-------|--------------------|
| `all` | Действует везде, проходит всегда |
| `by_format` | Только для указанных форматов сети — проверяется по `format_discounts` |
| `by_store` | Только для конкретных магазинов — проверяется по `store_discounts` |

### Шаг 3 — Фильтрация по уровню лояльности

Если у скидки задан `min_loyalty_level` — она применяется только если `user.loyalty_level >= min_loyalty_level`.

Анонимный покупатель (без `loyalty_card_id`) считается уровнем 0.

### Шаг 4 — Фильтрация персональных скидок

Скидки с `discount_type = "персональная"` отсеиваются по правилам:

| Условие | Результат |
|---------|-----------|
| Нет `loyalty_card_id` в запросе | Все персональные отсеиваются |
| `discount.loyalty_card_id IS NULL` | Применяется ко всем держателям карты |
| `discount.loyalty_card_id = X`, запрос с `loyalty_card_id = X` | Применяется |
| `discount.loyalty_card_id = X`, запрос с `loyalty_card_id ≠ X` | Отсеивается |

### Шаг 5 — Best-price-wins для каждого товара

Для каждого товара кандидаты:
- скидки по `product_id`
- скидки по `category_id`
- скидки по `brand_id`
- скидки с `link_type = "all"` (применяются к каждому товару)

Выбирается скидка, дающая **минимальный `paid_price`**:

```
paid = base_price × (1 − discount.value / 100)   [ROUND_HALF_UP до копеек]
```

`discount_id` победителя возвращается в ответе — касса обязана передать именно его при фиксации чека.

### Пример

```
Молоко, base_price = 135.79 ₽, пользователь loyalty_level = 2

  Скидка A: категория "молочные",  link_type=category, 15%,  min_level=null → 115.42 ₽
  Скидка B: бренд "Простоквашино", link_type=brand,    10%,  min_level=null → 122.21 ₽
  Скидка C: лояльность,            link_type=all,      5%,   min_level=2    → 129.00 ₽
  Скидка D: персональная (для этого user), link_type=category, 25% → 101.84 ₽

Без карты лояльности → победитель A (115.42 ₽), экономия 20.37 ₽
С картой (level=1)   → победитель A (115.42 ₽), Скидка C и D недоступны
С картой (level=2)   → победитель D (101.84 ₽), экономия 33.95 ₽
```

Скидки **не суммируются** — применяется только одна, лучшая для покупателя.

---

## Справочные эндпоинты (публичные)

```
GET /discounts/link-types   — типы связи скидки: product, category, brand, all
GET /discounts/types        — типы скидок: акция, лояльность, персональная, уценка
GET /discounts              — активные скидки (фильтры: entity_id, link_type)
GET /stores                 — список магазинов
GET /stores/formats         — форматы сетей (Пятёрочка, Перекрёсток, Чижик)
```

## Управление (только касса, `X-Terminal-Token`)

```
POST /discounts             — создать скидку
PUT  /discounts/{id}        — обновить скидку
POST /stores                — создать магазин
PUT  /stores/{id}           — обновить магазин
```
