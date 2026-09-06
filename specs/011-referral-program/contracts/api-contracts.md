# API Contracts: Реферальная программа

Все эндпоинты в существующем FastAPI-сервисе `web/`.  
Базовый URL: `http://localhost:8000`

Ошибки — `{"detail": "сообщение"}` (как 003).

Код: ровно 6 символов `[A-Za-z0-9]`, регистр значим.

---

## Дельта: POST /register

Как в 003, плюс опциональное поле.

**Request**

```json
{
  "phone": "+79161234567",
  "referral_code": "AbC12x"
}
```

| Поле | Тип | Обязательно |
|------|-----|-------------|
| phone | string | да, нормализуется в E.164 |
| referral_code | string \| omit | нет |

**Response 200** — как сейчас: `access_token`, `refresh_token`. При валидном коде в той же операции создаются `referral_link` и персональная скидка.

**Ошибки**

| HTTP | Когда |
|------|--------|
| 409 | телефон уже зарегистрирован (как 003); код не найден / использован / свой |
| 422 | телефон или формат кода |
| 409 | у invitee уже есть активная связка (для нового номера не применимо) |

Без `referral_code` поведение 003 не меняется.

---

## Дельта: POST /login

**Request** — тот же контракт, что `/register`.

**Response 200** — пара токенов. С валидным кодом и без покупок 180 дней: активация + скидка.

**Ошибки**

| HTTP | Когда |
|------|--------|
| 404 | пользователя нет (код аккаунт не создаёт) |
| 422 | формат телефона или кода |
| 409 | код не найден / использован / свой / уже есть активная связка |
| 409 | есть покупка за последние 180 дней — войти без кода |

Без `referral_code` — обычный вход 003, даже при недавних покупках.

Клиент **не** должен трактовать 409 как «номер не зарегистрирован» (это 404). 403 на этих путях реферал не использует.

---

## POST /referrals — выдать код

Auth: `Authorization: Bearer <access_token>` (`CurrentUserUUID`).

Тело: пустой JSON `{}` или отсутствие body.

**Response 201**

```json
{
  "id": "uuid",
  "code": "AbC12x",
  "status": "issued",
  "created_at": "2026-09-06T16:00:00+03:00",
  "activated_at": null,
  "discount_valid_to": null,
  "purchase_window_until": null,
  "reward_status": null
}
```

Каждый вызов — **новый** код. Предыдущие неиспользованные не инвалидируются.

**Ошибки**: 401 без токена.

---

## GET /referrals — мои приглашения

Auth: Bearer.

**Response 200**

```json
{
  "items": [
    {
      "id": "uuid",
      "code": "Xy9kL2",
      "status": "awaiting_purchase",
      "created_at": "2026-09-06T15:00:00+03:00",
      "activated_at": "2026-09-06T15:10:00+03:00",
      "discount_valid_to": "2026-09-13T15:10:00+03:00",
      "purchase_window_until": "2026-09-13T15:10:00+03:00",
      "reward_status": "awaiting_purchase"
    },
    {
      "id": "uuid",
      "code": "AbC12x",
      "status": "issued",
      "created_at": "2026-09-06T14:00:00+03:00",
      "activated_at": null,
      "discount_valid_to": null,
      "purchase_window_until": null,
      "reward_status": null
    }
  ]
}
```

Порядок: `created_at` по убыванию.  
`status`: `issued` | `awaiting_purchase` | `rewarded` | `expired` (см. data-model).  
Нет телефона, ФИО, UUID друга.

Пустой список: `{ "items": [] }`.

**Ошибки**: 401 без токена.

---

## Косвенные контракты (без смены путей)

### POST /receipts и POST /receipts/calculate

Тело не меняется. Если у `loyalty_card_id` жива персональная скидка `percent` / `all`, калькулятор применяет её по best-price-wins. Экономия попадает в `total_saved`.

Первый новый чек invitee внутри `purchase_window_until` начисляет приглашающему купоны и кешбек. Повтор того же `X-Idempotency-Key` награду не дублирует.

### GET /points/transactions и GET /coupons/transactions

Новые операции в существующих списках. В баллах — `related_referral_link_id` (nullable). В купонах — `type: "referral"`. Клиент может показать как «за приглашение», не обязан до этой фичи менять UI истории.

---

## Инварианты контракта

- Выданный `code` всегда длина 6, charset `[A-Za-z0-9]`.
- Клиент передаёт код **байт-в-байт**; сервер не приводит регистр.
- Регистрация с плохим кодом не создаёт user.
- Логин с кодом при недавних покупках не выдаёт токен.
- В ответах `/referrals` нет прямых идентификаторов приглашённого.
