# Quickstart: Колесо фортуны и купоны

## Предусловия

```bash
cd web
docker compose up -d postgres
poetry run alembic upgrade head
```

В `.env` (или окружении процесса):

```bash
FORTUNE_WHEEL_WEEKLY_COUPONS=3   # дефолт и так 3
JWT_SECRET_KEY=...
```

Каталог должен содержать категорию с именем `кондитерка` (стандартный сид). Нужен `USER_TOKEN` авторизованного пользователя.

Базовый URL: `http://localhost:8000`.

---

## Сценарий 1: Состояние колеса и еженедельные купоны

```bash
curl http://localhost:8000/wheel \
  -H "Authorization: Bearer $USER_TOKEN"
```

Ожидание: 200, `sectors.length >= 2`, сумма `probability_percent` = 100, есть и `cashback`, и `gift`, `coupons == 3` (первый заход на неделе), `can_spin == true`, `week_start` — понедельник текущей недели.

Повтор того же запроса на той же неделе: `coupons` не вырос.

Без токена:

```bash
curl -i http://localhost:8000/wheel
```

Ожидание: 401.

**Требования**: FR-001, FR-002, FR-008, FR-013, FR-020, FR-022, SC-004, SC-007.

---

## Сценарий 2: Кручение — приз с сервера

```bash
curl -X POST http://localhost:8000/wheel/spin \
  -H "Authorization: Bearer $USER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{}'
```

Ожидание: 200, `sector_code` из списка GET /wheel, `coupons_after == 2`, заполнен либо `cashback_rub` + `points_awarded`, либо `gift_reward_id`.

Проверка начисления:

```bash
# кешбэк
curl http://localhost:8000/points/balance \
  -H "Authorization: Bearer $USER_TOKEN"
# баланс вырос на points_awarded

# подарок
curl http://localhost:8000/rewards \
  -H "Authorization: Bearer $USER_TOKEN"
# есть active gift с criterion_type=category
```

Клиентский «заказ» приза не действует (поле не в контракте; если передать — исход всё равно серверный):

```bash
curl -X POST http://localhost:8000/wheel/spin \
  -H "Authorization: Bearer $USER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"sector_code":"large_cashback"}'
```

Ожидание: 200 и любой сектор по вероятностям, не обязательно `large_cashback`.

**Требования**: FR-004, FR-005, FR-006, FR-014–FR-016, SC-001.

---

## Сценарий 3: Отказ без купонов

Потратить остаток (при N=3 — ещё два спина) или временно выставить `FORTUNE_WHEEL_WEEKLY_COUPONS=0` на **новой** учётке / после исчерпания.

```bash
curl -i -X POST http://localhost:8000/wheel/spin \
  -H "Authorization: Bearer $USER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{}'
```

Ожидание: 409, `detail=INSUFFICIENT_COUPONS`. Повторный GET /wheel: `coupons=0`, `can_spin=false`. История не выросла на неуспешный спин.

**Требования**: FR-006, FR-007, SC-002.

---

## Сценарий 4: Подарок с колеса в корзине

Если спин выдал `gift_reward_id` (повторять сценарий 2, пока не выпадет подарок, или подставить сектор в тесте сервиса):

```bash
# взять product_id из категории кондитерка
curl -X POST http://localhost:8000/basket/preview \
  -H "Authorization: Bearer $USER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"items":[{"product_id":"'"$PRODUCT_ID"'","quantity":1}]}'
```

Ожидание: `gift_discounts` не пустой, `total < subtotal` на стоимость одной единицы.

**Требования**: FR-017, SC-008.

---

## Сценарий 5: Купон за выполненное задание

Закрыть задание пользователя чеком (как в quickstart 008, сценарий 2). Затем:

```bash
curl http://localhost:8000/coupons/transactions \
  -H "Authorization: Bearer $USER_TOKEN"
```

Ожидание: есть запись `type=task_complete`, `amount=1`, `related_task_id` = id закрытого задания. Повторная обработка того же чека/задания вторую такую запись не создаёт.

Истёкшее задание (expiration sweep) записи `task_complete` не создаёт.

**Требования**: FR-010, FR-011, SC-005.

---

## Сценарий 6: История кручений

После ≥2 успешных спинов:

```bash
curl "http://localhost:8000/wheel/spins?limit=20&offset=0" \
  -H "Authorization: Bearer $USER_TOKEN"
```

Ожидание: `total >= 2`, `items` от новых к старым, у каждой записи `prize_type` и `prize_label`.

**Требования**: FR-021, US5.

---

## Замечание по гонке (SC-009)

Два параллельных `POST /wheel/spin` при одном купоне проверяются тестом сервиса с одной сессией-локом / двумя клиентами, не curl. Ожидание: один 200, один 409, итоговый баланс 0, ровно один `wheel_spin`.
