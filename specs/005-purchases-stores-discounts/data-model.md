# Data Model: Покупки, магазины и скидки

**Branch**: `005-purchases-stores-discounts` | **Date**: 2026-09-04

> Базируется на `context/schema.md`. Существующие таблицы (`users`, `categories`, `products`) не переопределяются.

---

## Новые сущности

### store_formats

| Поле | Тип | Ограничения |
|------|-----|-------------|
| id | UUID | PK, default gen_random_uuid() |
| name | VARCHAR(100) | NOT NULL, UNIQUE |

Примеры: `Пятёрочка`, `Перекрёсток`, `Чижик`.

---

### stores

| Поле | Тип | Ограничения |
|------|-----|-------------|
| id | UUID | PK, default gen_random_uuid() |
| format_id | UUID | FK → store_formats.id, NOT NULL |
| geo_cluster | VARCHAR(200) | NOT NULL — район/геокластер для рейтинга |
| address | VARCHAR(500) | nullable — только для администрирования |

Index: `ix_stores_format_id`.

---

### discount_types

| Поле | Тип | Ограничения |
|------|-----|-------------|
| id | UUID | PK |
| name | VARCHAR(100) | NOT NULL, UNIQUE |

Значения seeds: `акция`, `лояльность`, `персональная`, `уценка`.

---

### discount_link_types

| Поле | Тип | Ограничения |
|------|-----|-------------|
| id | UUID | PK |
| name | VARCHAR(50) | NOT NULL, UNIQUE |

Значения seeds: `product`, `category`, `brand`.

---

### discounts

| Поле | Тип | Ограничения |
|------|-----|-------------|
| id | UUID | PK, default gen_random_uuid() |
| value | NUMERIC(5,2) | NOT NULL — процент скидки (0–100) |
| discount_type_id | UUID | FK → discount_types.id, NOT NULL |
| link_type_id | UUID | FK → discount_link_types.id, NOT NULL |
| entity_id | UUID | NOT NULL — полиморфная ссылка |
| scope | VARCHAR(20) | NOT NULL, CHECK IN ('all','by_format','by_store') |
| valid_from | TIMESTAMPTZ | nullable |
| valid_to | TIMESTAMPTZ | nullable |

Index: `ix_discounts_entity_id`, `ix_discounts_scope`.

**Constraint**: `valid_from < valid_to` (если оба не NULL).

---

### format_discounts (M2M)

| Поле | Тип | Ограничения |
|------|-----|-------------|
| discount_id | UUID | FK → discounts.id |
| format_id | UUID | FK → store_formats.id |

PK: `(discount_id, format_id)`.

Используется когда `discount.scope = 'by_format'`.

---

### store_discounts (M2M)

| Поле | Тип | Ограничения |
|------|-----|-------------|
| discount_id | UUID | FK → discounts.id |
| store_id | UUID | FK → stores.id |

PK: `(discount_id, store_id)`.

Используется когда `discount.scope = 'by_store'`.

---

### segments

| Поле | Тип | Ограничения |
|------|-----|-------------|
| id | UUID | PK |
| name | VARCHAR(100) | NOT NULL, UNIQUE |

Значения seeds: `подросток`, `семьянин`, `пожилой`.

---

### loyalty_cards

| Поле | Тип | Ограничения |
|------|-----|-------------|
| id | UUID | PK — совпадает с `users.id` (PoC упрощение) |
| loyalty_level | INTEGER | NOT NULL, default 1 |
| name | VARCHAR(200) | nullable |
| phone | VARCHAR(20) | nullable |
| gender | VARCHAR(10) | nullable |
| age | INTEGER | nullable |
| segment_id | UUID | FK → segments.id, nullable |

**PoC**: `loyalty_card.id = user.id`. Создаётся автоматически при регистрации.

---

### receipts

| Поле | Тип | Ограничения |
|------|-----|-------------|
| id | UUID | PK — **idempotency key**, переданный кассой |
| purchase_date | TIMESTAMPTZ | NOT NULL, default now() |
| payment_card_uid | VARCHAR(200) | nullable |
| loyalty_card_id | UUID | FK → loyalty_cards.id, nullable |
| store_id | UUID | FK → stores.id, NOT NULL |
| channel | VARCHAR(20) | NOT NULL, CHECK IN ('online','offline'), default 'offline' |

Index: `ix_receipts_loyalty_card_id`, `ix_receipts_store_id`, `ix_receipts_purchase_date`.

---

### receipt_items

| Поле | Тип | Ограничения |
|------|-----|-------------|
| id | UUID | PK, default gen_random_uuid() |
| receipt_id | UUID | FK → receipts.id, NOT NULL |
| product_id | UUID | FK → products.id, NOT NULL |
| quantity | INTEGER | NOT NULL, CHECK > 0 |
| base_price_at_purchase | NUMERIC(10,2) | NOT NULL |
| paid_price | NUMERIC(10,2) | NOT NULL |
| discounted_amount | NUMERIC(10,2) | NOT NULL, default 0 — = base - paid |
| discount_id | UUID | FK → discounts.id, nullable |

**Invariant**: `discounted_amount = base_price_at_purchase - paid_price` (проверяется в service).

Index: `ix_receipt_items_receipt_id`, `ix_receipt_items_product_id`.

---

## Временные структуры (не в БД)

### DiscountCalculationResult (Pydantic)

| Поле | Тип | Описание |
|------|-----|---------|
| product_id | UUID | Товар |
| base_price | Decimal | Полочная цена |
| paid_price | Decimal | Цена к оплате |
| discount_id | UUID \| None | Применённая скидка |
| discounted_amount | Decimal | Экономия на единицу |

Используется в ответе на `POST /receipts/calculate`.

---

## Диаграмма связей

```
store_formats ─── stores ──────────────────── receipts
                    │                              │
              store_discounts              loyalty_cards
              format_discounts                     │
                    │                           users
                discounts ── discount_types
                    │      ── discount_link_types
                    │
              receipt_items ── products ── categories
                    │
                 discounts
```

---

## Изменения в миграции

**Файл**: `web/alembic/versions/<hash>_add_purchases_tables.py`

Порядок создания (с учётом FK зависимостей):
1. `store_formats`
2. `stores` (FK → store_formats)
3. `discount_types`
4. `discount_link_types`
5. `discounts` (FK → discount_types, discount_link_types)
6. `format_discounts` (FK → discounts, store_formats)
7. `store_discounts` (FK → discounts, stores)
8. `segments`
9. `loyalty_cards` (FK → segments)
10. `receipts` (FK → loyalty_cards, stores)
11. `receipt_items` (FK → receipts, products, discounts)

Seeds в миграции: `discount_types`, `discount_link_types`, `segments`.
