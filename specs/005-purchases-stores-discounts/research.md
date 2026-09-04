# Research: Покупки, магазины и скидки

**Date**: 2026-09-04 | **Branch**: `005-purchases-stores-discounts`

## R-001: Idempotency key для POST /receipts

**Decision**: Касса передаёт `X-Idempotency-Key: <UUID>` в заголовке. Сервер сохраняет этот UUID как `receipt.id` (PRIMARY KEY). При повторном запросе с тем же ключом PostgreSQL выбросит UNIQUE violation; сервер перехватывает его, загружает существующий чек и возвращает `200 OK` с тем же телом.

**Rationale**: `receipt.id` — UUID, выданный кассой — является естественным idempotency key. Хранить отдельную таблицу ключей избыточно. UNIQUE constraint на PK даёт дедупликацию бесплатно.

**Alternatives considered**:
- Отдельная таблица `idempotency_keys` — избыточна для PoC.
- Дедупликация по `{loyalty_card_id, store_id, items hash, date}` — ненадёжна при часовых поясах и edge cases.

**Implementation note**: В `ReceiptRepository.create()` — `try: session.add(); session.commit() except IntegrityError: session.rollback(); return existing receipt`.

---

## R-002: Best-price-wins алгоритм

**Decision**: Для каждого `product_id` в корзине:
1. Собрать кандидатов: скидки, где `entity_id = product.id AND link_type = product` ИЛИ `entity_id = product.category_id AND link_type = category` ИЛИ `entity_id = product.brand_id AND link_type = brand`.
2. Фильтр по дате: `(valid_from IS NULL OR valid_from <= now()) AND (valid_to IS NULL OR valid_to >= now())`.
3. Фильтр по scope: `scope = 'all'` — всегда; `scope = 'by_format'` — если `store.format_id` в `format_discounts`; `scope = 'by_store'` — если `store_id` в `store_discounts`.
4. Выбрать скидку с максимальным `value` (процент). `paid_price = base_price * (1 - value/100)`.
5. `discounted_amount = base_price - paid_price`.

**Rationale**: Единый SQL-запрос с JOIN по трём link_type невозможен без UNION или полиморфного подхода. Оптимально — загрузить все кандидаты одним запросом через `OR` по `entity_id`, затем фильтровать в Python. Для корзины из 20 товаров при ~100 скидках в БД — достаточно быстро.

**Alternatives considered**:
- Отдельный SQL-запрос на каждый товар — N+1, неприемлемо.
- Materialized view по скидкам + product join — over-engineering для PoC.

**Implementation note**: `DiscountCalculatorService.calculate(cart_items, store, loyalty_card_id, session)` → возвращает список `DiscountCalculationResult`.

---

## R-003: Полиморфная связь скидок (discount.entity_id)

**Decision**: Использовать паттерн Generic Foreign Key: `discount.link_type_id` определяет к какой таблице относится `discount.entity_id`. SQLAlchemy не имеет встроенного polymorphic FK — работаем с `entity_id` как с `UUID` без FK constraint, фильтруя в Python после JOIN.

**Rationale**: Альтернатива — три опциональных FK (`product_id`, `category_id`, `brand_id`) — нарушает нормализацию и требует CHECK constraint. Generic FK чище и соответствует существующей схеме в `context/schema.md`.

**Alternatives considered**:
- Три отдельные таблицы `product_discounts`, `category_discounts`, `brand_discounts` — избыточно, усложняет запросы.

---

## R-004: Лояльность — связь пользователя с loyalty_card

**Decision**: В рамках PoC `loyalty_card` — отдельная сущность без прямой FK на `users`. Касса идентифицирует покупателя по `loyalty_card.id` (переданному в чеке). Мобильное приложение получает историю чеков через свой `loyalty_card_id`, который хранится в JWT-payload или передаётся как query param после связки в `/me`.

**Rationale**: Схема в `context/schema.md` определяет `loyalty_card` без FK на `users`. Связка пользователь↔карта — отдельная задача (вероятно через phone). Для PoC: при регистрации создаём `loyalty_card` и привязываем к `user.id`, либо делаем loyalty_card_id = user.id (упрощение).

**Alternatives considered**:
- loyalty_card_id = user.id (UUID совпадают) — допустимо для PoC, упрощает связку.

**Implementation note**: Для PoC — при регистрации автоматически создаём `loyalty_card` с тем же `id` что и `user.id`. GET /me/receipts использует `loyalty_card_id = current_user_uuid`.

---

## R-005: Обновление прогресса заданий (task.quantity_current)

**Decision**: После успешной записи чека — синхронно в рамках той же транзакции обновлять `task.quantity_current` для активных заданий пользователя. В ARCHITECTURE.md это вынесено в Celery (`update_economy`), но Celery/Redis в этой фиче не поднимается. Синхронное обновление — допустимое упрощение для PoC.

**Rationale**: Celery добавляет инфраструктурный overhead. Для хакатона важнее показать работающий flow, чем идеальную асинхронность. Переход на async — в BACKLOG.

**Alternatives considered**:
- Celery task — предусмотрен архитектурой, реализуем в следующей фиче.

---

## R-006: GET /economy — агрегация экономии

**Decision**: `SELECT SUM(discounted_amount) FROM receipt_items ri JOIN receipts r ON r.id = ri.receipt_id WHERE r.loyalty_card_id = :uid`. Возвращать `{ "total_saved": <Decimal> }`. Без кэша — прямой SQL.

**Rationale**: Простейшая агрегация. При масштабировании — добавить `loyalty_card.savings_total` денормализованную колонку (в ARCHITECTURE.md уже предусмотрена). Для PoC — on-the-fly вычисление.

---

## Resolved NEEDS CLARIFICATION

Все NEEDS CLARIFICATION из спецификации устранены в сессии `/speckit-clarify`:
- Idempotency key → R-001
- Истёкшая скидка → 422 в FR-007
- X-Terminal-Token → уже реализован, см. `dependencies/auth.py`
- Отсутствующий product_id → 422 в FR-001
