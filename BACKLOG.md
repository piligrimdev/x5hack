# Backlog

## В PoC не делаем (откладываем)

### Аватар-механика
- Таблица прогресса аватара (уровень, очки, история изменений)
- Кастомизация аватара за баллы
- Печать аватара на чеке (офлайн/онлайн)
- Связь: карта лояльности → аватар

### Районный рейтинг экономии
- Сущность "магазин" с геокластером/районом
- Агрегированная таблица/view рейтинга по кластерам
- Анонимное сравнение: юзер vs. дом/район (без ФИО/адресов)
- Периодические снэпшоты рейтинга

### Купоны
- Схема сущности купона и связей

### Фрод
- Скоринг по uid карт оплаты (сигнал: 4 последние банковские карты на карту лояльности)

### Апельсинки / баллы лояльности
- ~~Таблица транзакций баллов: начисление (за задание), списание (на кассе)~~ — реализовано в feature 007 (`points_transaction`).
- ~~Кэш-баланс на карте лояльности (денормализованный)~~ — реализовано (`points_account.balance`).
- ~~Интеграция апельсинок как частичной оплаты чека (points_redeemed на чеке)~~ — реализовано (`receipt.cashback_applied_*`).
- **Не реализовано** (осталось):
  - Начисление баллов за сам факт покупки (сейчас — только за задания).
  - Срок истечения баллов (`expired_at`, автосгорание).
  - Возврат/отмена чека — откат `spend`, отзыв `earn` за отменённое задание.
  - Cleanup orphan `points_account` при удалении `loyalty_card`.
  - Push-уведомление о начислении баллов.
  - Дробный курс (Decimal `rate_points_per_rub`) — сейчас только integer.

### Cashback (feature 007) — переосмысление устаревших полей
- `task.reward_id` и `task.reward_type` (введены в feature 006) новыми задачами не заполняются: награда = баллы, а не Discount. Отдельной миграцией удалить/переосмыслить.
- `TaskRepository.create_reward_discount` помечен `# BACKLOG-cleanup` — удалить после подтверждения, что нет внешних вызовов.
- Sanity-check скрипт: пересчитывать `points_account.balance = SUM(amount) FROM points_transaction WHERE account_id=...` периодически, для выявления рассинхронизации.

### Concurrent-spend integration test (SC-003)
- Реальный integration-тест с 100 параллельными потоками против живой Postgres, проверяющий инвариант `balance >= 0` (сейчас — только логика через MagicMock + DB constraint).

### Составные задания (multi-criterion)
- task_progress таблица: task_id, criterion_id, current_value, target_value
- Поддержка нескольких критериев на одно задание

### Скидки по расписанию
- Скидки по дням недели / времени суток (is_recurrent, schedule)

### Уценка как фиксированная сумма
- ~~value_type на скидке (percent / fixed_rub)~~ — реализовано в feature 006 для награды за задание. Уценку кассой ещё нужно смоделировать явно.

### Персистентная корзина ассистента
- Сейчас корзина живёт только в локальном стейте фронтенда (`useBasket`) и
  целиком пересылается с каждым `POST /basket/assistant`; обновление
  страницы теряет несохранённые правки
- Осознанное упрощение PoC, см. "Явно вне скоупа" в
  `docs/superpowers/specs/2026-09-04-basket-ai-assistant-design.md`
- Для продакшна нужна таблица вида `user_baskets` (корзина на пользователя,
  персистентная между сессиями/устройствами)

### Дополнительные типы наград (мост FR-011a готов)
- Coupon-сущность (id, code, discount_value, expires_at, used_at) как второй `task.reward_type`
- Points/апельсинки как третий `task.reward_type` (требует таблицы транзакций баллов из «Апельсинки»-раздела)

### Langfuse интеграция
- Экспортировать записи `challenge_generation_log` как traces + tool-calls в Langfuse для внешнего аудита LLM
- Сейчас — только Postgres-таблица

### Unit-тесты Celery-задач с live Postgres
- test_generation_and_receipt.py, test_process_receipt_progress.py, test_expiration.py — требуют pytest-фикстуры на реальную БД
- Логика частично покрыта unit-тестами task_completion/challenge_service

### Adapter unit-tests
- `web/tests/webx5/services/test_challenge_adapter.py` — детально проверить `build_profile` (margin из config), `_lookup_product` (ILIKE + ordering), `persist_challenge` для всех известных `SCRIPT_FIELD_TO_CRITERION_KIND`

### Defensive null-check в BasketService.checkout()
- `store_repo.get_by_id(session, receipts[0].store_id)` используется без проверки на `None`
- Сейчас недостижимо: `Receipt.store_id` — `ForeignKey("stores.id", ondelete="RESTRICT")`, БД не даст удалить
  магазин, на который ссылается существующий чек
- Стоит добавить `if store is None: raise HTTPException(422, ...)` как страховку на случай, если политика FK
  изменится (например, на `SET NULL`/`CASCADE`)

### ~~Списание баллов лояльности при оформлении заказа из корзины~~
- Реализовано: `POST /basket/checkout` принимает `points_to_spend` (только `"all"` через тумблер
  «Списать баллы» в UI, точное количество не поддерживается — см. новую запись ниже)

### Выбор магазина пользователем вручную при оформлении заказа
- Сейчас магазин для `/basket/checkout` выбирается автоматически: последний магазин из истории
  чеков пользователя, либо первый магазин в БД, если истории нет
- Пользователь не может указать другой магазин (например, ближайший или тот, где планирует быть)
- Нужен явный `store_id` (опциональный) в `CheckoutRequest` с фолбэком на текущую эвристику

### Рефактор terminal-эндпоинта create_receipt на build_receipt_response()
- `web/src/webx5/routes/receipts.py::create_receipt` (строки ~140-184) собирает `ReceiptResponse`
  вручную, дублируя логику, которую `ReceiptService.build_receipt_response()` уже инкапсулирует
  для нового `/basket/checkout`
- Свести оба места к одному вызову `receipt_service.build_receipt_response()`

### Хардненинг checkout-эндпоинта (basket)
- Нет идемпотентности у `POST /basket/checkout` — `receipt_id` генерируется как `uuid4()` на
  каждый вызов, в отличие от терминального `/receipts`, который требует `X-Idempotency-Key`;
  таймаут на мобильной сети может привести к повторному чеку при ретрае пользователя
- `BasketItemIn.quantity` / `CheckoutRequest.items` не имеют верхней границы —
  `quantity=999999999` технически проходит валидацию

### Человекочитаемые ошибки на фронтенде корзины
- `apiFetch` бросает `Error("422 {...}")`, и `useBasket.ts` показывает это как есть через
  `setMessage(e.message)` — пользователь видит код статуса и сырой JSON вместо текста
- Стоит парсить `detail` из тела ошибки перед показом пользователю

### Точный ввод количества баллов для списания
- Тумблер «Списать баллы» в корзине сейчас — только вкл/выкл, списывает максимум
  (`points_to_spend: "all"`)
- Точный ввод числа баллов (как у терминального `/receipts/calculate`, которое принимает
  произвольный `int`) — вне объёма, добавить как отдельное поле ввода при необходимости

### Общий хелпер ценообразования корзины (preview + terminal)
- `BasketService.preview()` (`web/src/webx5/services/basket_assistant.py`) — почти дословная копия
  `routes/receipts.py::calculate_discounts` (~45 строк): тот же маппинг в `CalculatedItemOut`,
  та же сборка `total_base`/`total_paid`/`total_saved`/`CashbackBlock`
- Стоит вынести в общий сервисный метод, который вызывают оба места — заодно уберёт SQL
  (`session.get(Store, ...)`, `select(Product.id)`), который сейчас лежит прямо в
  `calculate_discounts`, нарушая RSI (роут не должен делать SQL напрямую)
- Не сделано в рамках текущего плана — узкий скоуп, оставлено как есть
