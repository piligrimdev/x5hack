# Implementation Plan: Покупки, магазины и скидки

**Branch**: `005-purchases-stores-discounts` | **Date**: 2026-09-04 | **Spec**: [spec.md](spec.md)

## Summary

Добавить полный цикл покупки: кассовый аппарат рассчитывает best-price-wins скидки для корзины и фиксирует чек; пользователь видит историю покупок и суммарную экономию. Реализуется через новый пакет `purchases/` в FastAPI-монолите, Alembic-миграция добавляет недостающие бизнес-сущности (магазин, скидка, карта лояльности, чек).

## Technical Context

**Language/Version**: Python 3.12 (backend), TypeScript / React Native (mobile)

**Primary Dependencies**: FastAPI, SQLAlchemy (sync), Alembic, Pydantic v2; Expo 57 + Expo Router (mobile)

**Storage**: PostgreSQL 16. Существующие таблицы: `users`, `categories`, `products`. Требуются: `store_formats`, `stores`, `discount_types`, `discount_link_types`, `discounts`, `format_discounts`, `store_discounts`, `segments`, `loyalty_cards`, `receipts`, `receipt_items`.

**Testing**: pytest (backend unit-тесты на сервисном слое)

**Target Platform**: Linux (Docker), iOS/Android (mobile)

**Performance Goals**: Расчёт скидок для корзины из 20 товаров — < 2 с (SC-001). Запрос истории чеков — < 1 с.

**Constraints**: Sync SQLAlchemy (async в BACKLOG). TerminalTokenDep уже реализован. Idempotency key = UUID, передаётся кассой в заголовке `X-Idempotency-Key`, хранится как `receipt.id`.

**Scale/Scope**: PoC. Небольшая нагрузка, без кэша. Celery/Redis — не требуются для базовой записи чека в этой фиче (фоновые задачи — отдельная фича).

## Constitution Check

| Принцип | Статус | Комментарий |
|---------|--------|-------------|
| I. Экономия как единая метрика | ✅ | GET /economy возвращает суммарный discounted_amount; мобильный экран экономии — обязательный элемент |
| II. ≤2 действия | ✅ | Экономия доступна с главного экрана без промежуточных шагов |
| III. ИИ-персонализация | — | Не затрагивается в этой фиче |
| IV. Экономическая обоснованность | ✅ | Скидки — реальные данные из БД; best-price-wins защищает маржу |
| V. Privacy by Design | ✅ | GET /stores возвращает geo_cluster, не адрес; рейтинг без персональных данных |
| Backend RSI | ✅ | Новый пакет `receipts/`, `stores/`, `discounts/` с раздельными crud/service/routes |
| Mobile standards | ✅ | Expo 57, Expo Router, хуки для бизнес-логики |

**GATE: пройден**. Нарушений нет.

## Project Structure

### Documentation (this feature)

```text
specs/005-purchases-stores-discounts/
├── plan.md              # This file
├── research.md          # Phase 0
├── data-model.md        # Phase 1
├── quickstart.md        # Phase 1
└── contracts/           # Phase 1
    ├── receipts.md
    ├── stores.md
    └── discounts.md
```

### Source Code

```text
# Backend (Option 3: Mobile + API)
web/src/webx5/
├── entities/
│   ├── store.py           # StoreFormat, Store
│   ├── discount.py        # DiscountType, DiscountLinkType, Discount, FormatDiscount, StoreDiscount
│   ├── loyalty.py         # Segment, LoyaltyCard
│   └── receipt.py         # Receipt, ReceiptItem
├── crud/
│   ├── store.py           # StoreRepository
│   ├── discount.py        # DiscountRepository
│   ├── loyalty.py         # LoyaltyCardRepository
│   └── receipt.py         # ReceiptRepository
├── services/
│   ├── discount_calculator.py   # best-price-wins
│   └── receipt.py               # ReceiptService
├── routes/
│   ├── stores.py          # GET/POST/PUT stores
│   ├── discounts.py       # GET/POST/PUT discounts
│   └── receipts.py        # POST /calculate, POST /receipts, GET /receipts, GET /economy
└── schemas/
    ├── store.py
    ├── discount.py
    └── receipt.py

web/alembic/versions/
└── <hash>_add_purchases_tables.py   # store_formats, stores, discount_*, segments, loyalty_cards, receipts, receipt_items

# Mobile
x5mobile/src/
├── app/
│   └── (tabs)/
│       └── purchases/
│           ├── index.tsx       # Список чеков + суммарная экономия
│           └── [id].tsx        # Детализация чека
├── hooks/
│   ├── useReceipts.ts          # Список чеков
│   ├── useReceiptDetail.ts     # Детализация
│   └── useEconomy.ts           # Суммарная экономия
└── components/screens/
    ├── ReceiptListScreen.tsx
    └── ReceiptDetailScreen.tsx
```

**Structure Decision**: Option 3 (Mobile + API). Бэкенд — FastAPI-монолит, мобилка — Expo Router.

## Complexity Tracking

> Нарушений конституции нет — таблица не заполняется.
