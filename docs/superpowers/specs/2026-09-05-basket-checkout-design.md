# Оформление заказа из корзины на неделю — Design

**Дата:** 2026-09-05
**Статус:** approved (в чате, 2026-09-05)
**Связанные документы:** [2026-09-04-basket-ai-assistant-design.md](2026-09-04-basket-ai-assistant-design.md) — базовая корзина/ассистент "Аппи", на который эта фича опирается.

## Контекст

Фича "корзина на неделю" (AI-подбор товаров + ассистент "Аппи" для add/remove) уже
реализована и работает: `GET /basket/suggested`, `POST /basket/assistant`. Корзина
стейтлес — фронт хранит список товаров и пересылает его целиком на каждый запрос,
в БД ничего не сохраняется.

Пользователь хочет завершить цикл: кнопка "Оформить заказ" в корзине, которая
реально фиксирует покупку — создаёт `Receipt`, который затем попадает в экономию,
рейтинг и прогресс челленджей (все три уже читают данные из `receipts`).

**Важное открытие при разборе:** единственный существующий способ создать `Receipt` —
`POST /receipts`, защищённый `TerminalTokenDep` (общий секрет для кассового
терминала — см. `web/src/webx5/dependencies/auth.py::verify_terminal_token`).
Мобильное приложение сейчас его не вызывает вообще. Использовать этот же
эндпоинт из приложения означало бы зашить `TERMINAL_TOKEN` в клиент — секрет,
который может создать чек на любую `loyalty_card_id`, что для мобильного клиента
неприемлемо. Поэтому нужен новый, привязанный к текущему пользователю (`CurrentUserUUID`)
путь создания чека, который переиспользует существующую бизнес-логику, а не
дублирует её.

**Соответствие constitution.md:** Principle II (NON-NEGOTIABLE) запрещает новые
*механики* сверх аватара/челленджа/рейтинга. Чек/экономия — не отдельная механика,
а данные, на которых уже построены все три. Оформление заказа не добавляет новый
экран и не превышает лимит ≤2 действий от главного экрана (кнопка — часть уже
одобренной корзины на экране экономии). Кейсодатель также подтвердил приоритет
офлайн-покупок над онлайн-заказами (`CONTEXT_PACK.md`, Q&A p.6) — это укрепляет
трактовку "оформить заказ" как симуляцию офлайн-покупки (`channel="offline"`),
а не запуск полноценного e-commerce потока.

## Архитектура

Новой персистентности не добавляется. Переиспользуются существующие сервисы,
уже собранные в `web/src/webx5/core/purchases.py`:

- `DiscountCalculatorService.calculate()` — подбирает лучшую скидку на каждый
  товар (то же, что делает `/receipts/calculate` для терминала).
- `ReceiptService.create_receipt()` — создаёт `Receipt`+`ReceiptItem`, списывает
  баллы (если запрошено — здесь не запрашиваем), запускает Celery-обработку
  чека (`process_receipt.apply_async`, обновляет прогресс челленджей).

`BasketService` (уже существует, `web/src/webx5/services/basket_assistant.py`)
получает новый метод `checkout()` и три новые зависимости через DI (конструктор):
`discount_calc: DiscountCalculatorService`, `receipt_service: ReceiptService`,
`store_repo: StoreRepository`. Плюс уже имеющийся `self.repo: BasketRepository`
даёт каталог товаров, а новый `receipt_repo: ReceiptRepository` — историю чеков
для выбора магазина.

```
routes/basket.py (POST /basket/checkout)
        │  CurrentUserUUID, SessionDep
        ▼
BasketService.checkout(session, user_id, items)
        │
        ├── receipt_repo.list_by_loyalty_card(user_id, page=1, size=1)
        │       → store_id последнего чека, иначе store_repo.list_all()[0]
        │
        ├── validate: все product_id есть в каталоге (BasketRepository.get_full_catalog)
        │
        ├── discount_calc.calculate(cart_items, store, user_id, session)
        │       → CalculatedItem[] с discount_id на каждый товар
        │
        └── receipt_service.create_receipt(session, uuid4(), ReceiptCreate(...))
                → Receipt (channel="offline", loyalty_card_id=user_id)
                → build_receipt_response() → ReceiptResponse
```

## API

### `POST /basket/checkout`

Авторизация: `CurrentUserUUID` (как у `/basket/suggested`, `/basket/assistant`).

**Request** (переиспользует `BasketItemIn` из `schemas/basket.py`):
```json
{"items": [{"product_id": "uuid", "quantity": 2}]}
```

**Response 201** — существующая схема `ReceiptResponse` (`schemas/receipt.py`):
поля `id`, `purchase_date`, `store_id`, `items`, `total_base`, `total_paid`,
`total_saved`, `discount_saved_rub`, `cashback_applied_points/rub`, и т.д.

**Ошибки:**
- `items` пуст → `422 {"detail": "Корзина пуста"}`
- `product_id` не найден в каталоге → `422 {"detail": "Unknown product_ids", "unknown_product_ids": [...]}`
  (проверяется явно в `checkout()` — иначе `DiscountCalculatorService.calculate()`
  молча пропускает неизвестные товары, а не поднимает ошибку)
- в БД вообще нет ни одного магазина → `422 {"detail": "Не найдено ни одного магазина"}`
  (крайний случай, сейчас в БД 60 магазинов)

## Response-builder для Receipt

`routes/receipts.py::create_receipt` уже содержит ~30 строк сборки
`ReceiptResponse` из `Receipt` + `get_items_with_products` (total_base/total_paid/
discount_saved/cashback). Чтобы не дублировать это во втором месте, логика
переносится в `ReceiptService.build_receipt_response(session, receipt) -> ReceiptResponse`
и используется новым маршрутом. Существующий терминальный маршрут не трогаем
(не входит в объём этой задачи) — рефактор его на использование нового метода
можно сделать отдельно, см. `BACKLOG.md`.

## Фронтенд

`x5mobile/src/hooks/useBasket.ts` — новая функция `checkout(): Promise<void>`:
- шлёт `POST /basket/checkout` с текущим `items`
- на успех: `setItems([])`, `setMessage` с текстом вида
  `"Заказ оформлен! Сэкономлено {total_saved} ₽"`, вызывает переданный колбэк
  `onOrderPlaced` (для обновления карточки экономии)
- на ошибку: `setMessage(e.message)`, корзина не меняется

`x5mobile/src/hooks/useEconomy.ts` — добавить `refetch(): void`, возвращаемый
из хука (сейчас данные грузятся только один раз при монтировании).

`x5mobile/src/components/screens/savings-view.tsx`:
- новая проп `onOrderPlaced: () => void` (прокидывается из `index.tsx`,
  вызывает `refetch` из `useEconomy`)
- кнопка "Оформить заказ" в карточке корзины, под полем ввода ассистента;
  `disabled` при пустой корзине или `basketLoading`

`x5mobile/src/app/index.tsx`: `SavingsView` получает `onOrderPlaced={refetchEconomy}`.

## Тестирование

Unit-тест `web/tests/webx5/services/test_basket_assistant.py` (расширение
существующего файла, если есть, иначе новый) для `BasketService.checkout()` —
моки `BasketRepository`, `ReceiptRepository`, `StoreRepository`,
`DiscountCalculatorService`, `ReceiptService`:
1. Скидка применяется (discount_id пробрасывается в `ReceiptItemCreate`).
2. Магазин берётся из последнего чека пользователя.
3. Fallback на первый магазин при пустой истории чеков.
4. Пустая корзина → исключение/422 до похода в БД.
5. Неизвестный `product_id` → 422 с `unknown_product_ids`.

Ручная E2E-проверка: `POST /basket/checkout` через curl на живом стеке (как для
`/basket/assistant` ранее в этой сессии) + проверка, что `GET /receipts/economy`
и `GET /receipts` отражают новый чек.

## Вне объёма (BACKLOG.md)

- Списание баллов лояльности при оформлении заказа из корзины (`points_to_spend`).
- Выбор магазина пользователем вручную.
- Рефактор `routes/receipts.py::create_receipt` на использование
  `ReceiptService.build_receipt_response()`.
