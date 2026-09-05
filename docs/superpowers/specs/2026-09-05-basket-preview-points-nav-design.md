# Превью цены/скидки в корзине, списание баллов, навигация из таб-бара — Design

**Дата:** 2026-09-05
**Статус:** approved (в чате, 2026-09-05)
**Связанные документы:**
[2026-09-04-basket-ai-assistant-design.md](2026-09-04-basket-ai-assistant-design.md) — базовая корзина/ассистент "Аппи".
[2026-09-05-basket-checkout-design.md](2026-09-05-basket-checkout-design.md) — оформление заказа (реальный чек).

## Контекст

После того как оформление заказа заработало, пользователь запросил четыре
связанные вещи:

1. Нижний таб-бар (`CustomTabBar`, вкладка "Корзина") никуда не ведёт —
   `screen === 'cart'` нигде не обрабатывается в `index.tsx`.
2. В карточке корзины на экране "Экономия" видно только название и
   количество товара — ни базовой цены, ни цены со скидкой.
3. При оформлении заказа нельзя списать баллы лояльности, хотя бэкенд это
   уже умеет для терминала (`ReceiptService.create_receipt` уже принимает
   `points_to_spend` и вызывает `PointsService.spend_for_receipt`).
4. Прогресс в челленджи при покупке — **уже работает**: `checkout()`
   создаёт `Receipt` через тот же `create_receipt`, который уже
   диспатчит Celery-таску `process_receipt` (условие: `is_new and
   loyalty_card_id is not None`, оба всегда true для чекаута из корзины).
   Ничего не меняем.

## Архитектура

Всё переиспользует уже существующие сервисы — новой персистентности нет.

### Общий хелпер выбора магазина

`BasketService.checkout()` уже содержит логику "магазин из последнего чека,
иначе первый магазин в БД, иначе 422". Новый метод превью использует ту же
логику — выносим её в приватный метод `BasketService._resolve_store(session,
user_id) -> Store`, поднимающий `HTTPException(422)` при отсутствии
магазинов. `checkout()` тоже переключается на этот метод (без изменения
поведения — чистый рефакторинг, дублирование убрано).

### `POST /basket/preview` — новый эндпоинт

Авторизация: `CurrentUserUUID`. Ничего не пишет в БД.

**Request** — новая схема `BasketPreviewRequest`:
```json
{"items": [{"product_id": "uuid", "quantity": 2}], "points_to_spend": null}
```
`items` может быть пустым (превью пустой корзины — валидный случай, не
ошибка, в отличие от чекаута). `points_to_spend` — тип `PointsToSpend`
(`int | Literal["all"] | None`, уже есть в `schemas/receipt.py`).

**Response** — переиспользуем существующую схему `CalculateResponse`
(`schemas/receipt.py`, та же, что отдаёт терминальный `/receipts/calculate`):
`items: list[CalculatedItemOut]` (product_id, product_name, quantity,
base_price, paid_price, discount_id, discounted_amount),
`total_base`, `total_paid`, `total_saved`, `cashback: CashbackBlock | null`.

`BasketService.preview(session, user_id, items, points_to_spend) ->
CalculateResponse`:
1. Если `items` не пуст — валидация unknown `product_id` (как в `checkout()`,
   через каталог `BasketRepository.get_full_catalog`). Пустой список —
   валиден, сразу возвращаем нулевой `CalculateResponse` без похода за
   магазином/скидками.
2. `store = self._resolve_store(session, user_id)`.
3. `calculated = self.discount_calc.calculate(cart_items, store, user_id,
   session)` — те же `CalculatedItem`, что использует чекаут.
4. Собираем `CalculatedItemOut` из `calculated` (маппинг 1:1, как делает
   `routes/receipts.py::calculate_discounts` сегодня для терминала).
5. `total_base`/`total_paid` — суммы по items.
6. `cashback = self.points_service.preview_for_calculate(session,
   loyalty_card_id=user_id, points_requested_raw=points_to_spend,
   subtotal_rub=int(total_paid))` — метод уже существует
   (`services/points.py:150`), возвращает `CashbackPreview | None`
   (`None` только когда `loyalty_card_id is None`, что здесь никогда не
   бывает — auth гарантирует `user_id`).
7. `total_saved = (total_base - total_paid) + (cashback.cashback_rub if
   cashback else 0)` — та же формула, что в `calculate_discounts`.

`BasketService` получает новую зависимость `points_service: PointsService`
через конструктор (переиспользуем существующий singleton из
`web/src/webx5/core/points.py`).

### `POST /basket/checkout` — добавляем баллы

`CheckoutRequest` получает поле `points_to_spend: PointsToSpend = None`.
`BasketService.checkout()` пробрасывает его в `ReceiptCreate(...,
points_to_spend=points_to_spend)` — остальная логика (`create_receipt`
уже вызывает `points_service.spend_for_receipt` при `wants_points`)
не меняется.

## Фронтенд

### Навигация (таб-бар)

`x5mobile/src/app/index.tsx`: `onTabPress` для `CustomTabBar` меняется с
`(tab) => navigate(tab)` на `(tab) => navigate(tab === 'cart' ? 'savings' :
tab)`. Остальные вкладки (`catalog`/`appi`/`profile`) остаются как есть
(вне объёма этой задачи — уже были нерабочими заглушками).

### `useBasket` — превью цены и баллов

Новое состояние `preview: CalculateResponse | null` и `spendPoints: boolean`
(тумблер), плюс `setSpendPoints`. `useEffect` перезапрашивает
`POST /basket/preview` при изменении `items` или `spendPoints` (debounce не
нужен — вызывается не на каждое нажатие клавиши, а на смену списка товаров
после ответа `/basket/suggested` или `/basket/assistant`, и на тумблер).
`checkout()` передаёт `points_to_spend: spendPoints ? "all" : null` в теле
запроса.

### `savings-view.tsx` — отображение

Под каждым товаром в списке корзины — базовая цена (зачёркнутая, если
`paid_price < base_price`) и цена со скидкой. Под списком, над кнопкой
"Оформить заказ" — блок итогов: "Итого: X ₽", "Скидка: −Y ₽" (если > 0),
переключатель "Списать баллы" с доступным балансом (`usePointsBalance`,
уже есть и используется на главном экране), "Итого с баллами: Z ₽" (если
тумблер включён и `cashback.cashback_rub > 0`).

## Вне объёма (BACKLOG.md)

- Точный ввод количества баллов для списания (сейчас — только вкл/выкл,
  списывается максимум через `points_to_spend="all"`).
- Реализация вкладок "Каталог"/"Аппи"/"Профиль" в таб-баре — остаются
  нерабочими заглушками, не входит в эту задачу.
