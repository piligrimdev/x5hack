# API Contracts: Колесо фортуны и купоны

Все эндпоинты в существующем FastAPI-сервисе `web/`.  
Базовый URL: `http://localhost:8000`  
Auth: `Authorization: Bearer <access_token>` (`CurrentUserUUID` = `users.id` = карта лояльности).

Без токена — **401** на все пути ниже.

---

## GET /wheel — состояние колеса

Лениво начисляет еженедельный пакет, если его ещё не было на этой календарной неделе (пн 00:00, Europe/Moscow).

**Response 200**

```json
{
  "coupons": 3,
  "can_spin": true,
  "weekly_coupons": 3,
  "week_start": "2026-09-01",
  "sectors": [
    {
      "code": "small_cashback",
      "label": "Небольшой кешбэк",
      "description": "10 ₽ на счёт баллов",
      "prize_type": "cashback",
      "probability_percent": 40,
      "cashback_rub": 10,
      "gift": null
    },
    {
      "code": "medium_cashback",
      "label": "Средний кешбэк",
      "description": "30 ₽ на счёт баллов",
      "prize_type": "cashback",
      "probability_percent": 30,
      "cashback_rub": 30,
      "gift": null
    },
    {
      "code": "gift_chocolate",
      "label": "Подарок: 1 шоколадка бесплатно",
      "description": "1 бесплатная единица товара категории «кондитерка»",
      "prize_type": "gift",
      "probability_percent": 20,
      "cashback_rub": null,
      "gift": {
        "criterion_type": "category",
        "criterion_entity_id": "uuid",
        "quantity": 1
      }
    },
    {
      "code": "large_cashback",
      "label": "Крупный кешбэк",
      "description": "100 ₽ на счёт баллов",
      "prize_type": "cashback",
      "probability_percent": 10,
      "cashback_rub": 100,
      "gift": null
    }
  ]
}
```

Инварианты ответа:
- `sectors.length >= 2`
- сумма `probability_percent` = 100
- `can_spin == (coupons > 0)`
- `weekly_coupons` = текущее значение env (N), не «сколько уже выдали за жизнь»
- на текущем этапе списки двух пользователей совпадают; контракт при этом персональный (привязан к токену)

---

## POST /wheel/spin — кручение

Тело: пустой JSON `{}` или отсутствие body. Клиент **не** передаёт сектор. Поля вроде `sector_code` / `prize_id` не являются контрактом и не влияют на исход.

Перед списанием выполняется тот же weekly grant, что в GET.

**Response 200**

```json
{
  "spin_id": "uuid",
  "sector_code": "medium_cashback",
  "prize_type": "cashback",
  "prize_label": "Средний кешбэк",
  "cashback_rub": 30,
  "points_awarded": 300,
  "gift_reward_id": null,
  "coupons_after": 2,
  "created_at": "2026-09-06T12:00:00+03:00"
}
```

Пример подарка:

```json
{
  "spin_id": "uuid",
  "sector_code": "gift_chocolate",
  "prize_type": "gift",
  "prize_label": "Подарок: 1 шоколадка бесплатно",
  "cashback_rub": null,
  "points_awarded": null,
  "gift_reward_id": "uuid",
  "coupons_after": 2,
  "created_at": "2026-09-06T12:00:00+03:00"
}
```

`points_awarded` — фактически начисленные баллы по формуле `award_for_task` (рубли × курс, округление как в `PointsService`). При курсе 10 и призе 30 ₽ → 300 баллов.

**Response 409** — нет купонов после weekly grant

```json
{ "detail": "INSUFFICIENT_COUPONS" }
```

Баланс и призы не меняются.

**Response 503** — подарочный сектор не резолвится (нет категории `кондитерка` в каталоге). Транзакция спина откатывается.

---

## GET /wheel/spins — история кручений

Пагинация как у `GET /points/transactions`.

**Query**: `limit` (default 20, 1–100), `offset` (default 0)

**Response 200**

```json
{
  "items": [
    {
      "id": "uuid",
      "sector_code": "gift_chocolate",
      "prize_type": "gift",
      "prize_label": "Подарок: 1 шоколадка бесплатно",
      "cashback_rub": null,
      "gift_reward_id": "uuid",
      "gift_status": "active",
      "coupons_spent": 1,
      "created_at": "2026-09-06T12:00:00+03:00"
    }
  ],
  "limit": 20,
  "offset": 0,
  "total": 1
}
```

`gift_status`: `active` | `used` | `expired` | `null` (для кешбэка). Сортировка: `created_at DESC`. Пустая история — `items: []`, не 404.

---

## GET /coupons/transactions — леджер купонов

**Query**: `limit`, `offset` — те же правила.

**Response 200**

```json
{
  "items": [
    {
      "id": "uuid",
      "type": "weekly_grant",
      "amount": 3,
      "related_task_id": null,
      "related_spin_id": null,
      "week_start": "2026-09-01",
      "created_at": "2026-09-06T12:00:00+03:00"
    },
    {
      "id": "uuid",
      "type": "spin",
      "amount": -1,
      "related_task_id": null,
      "related_spin_id": "uuid",
      "week_start": null,
      "created_at": "2026-09-06T12:05:00+03:00"
    },
    {
      "id": "uuid",
      "type": "task_complete",
      "amount": 1,
      "related_task_id": "uuid",
      "related_spin_id": null,
      "week_start": null,
      "created_at": "2026-09-06T13:00:00+03:00"
    }
  ],
  "limit": 20,
  "offset": 0,
  "total": 3
}
```

`type ∈ {weekly_grant, task_complete, spin}`.

---

## Совместимость существующих эндпоинтов

### GET /points/transactions

В каждый элемент добавляется nullable `related_spin_id`. Старые записи — `null`. Клиенты, игнорирующие неизвестные поля, не ломаются.

### GET /rewards

Подарок с колеса уже в списке: тот же `GiftRewardOut`. Источник (задание / колесо) клиенту не обязателен; при необходимости можно позже добавить `source`.

### POST /basket/preview, POST /receipts

Без изменений контракта. Активный подарок с колеса применяется теми же правилами, что подарок за задание.

---

## Security

| Путь | Auth | Иначе |
|------|------|-------|
| GET /wheel | Bearer | 401 |
| POST /wheel/spin | Bearer | 401 |
| GET /wheel/spins | Bearer | 401 |
| GET /coupons/transactions | Bearer | 401 |

Пользователь видит только свои сектора, спины и купоны. Кассовый токен для этих путей не используется.
