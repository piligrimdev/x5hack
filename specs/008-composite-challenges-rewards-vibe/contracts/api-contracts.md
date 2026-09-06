# API Contracts: Составные задания, типы наград и вайб

Все эндпоинты в рамках существующего FastAPI-сервиса `web/`.
Базовый URL: `http://localhost:8000`
Auth пользователя: `Authorization: Bearer <access_token>`
Auth кассового аппарата: `X-Terminal-Token: <TERMINAL_TOKEN>`

---

## Вайб (Vibe)

### GET /vibes — список всех типов вайба

Публичный (без auth). Используется пользователем для выбора.

**Response 200**
```json
[
  {
    "id": "uuid",
    "name": "Здоровье и лёгкость",
    "description": "Фрукты, овощи, злаки — питание без лишнего",
    "llm_context": "молочные продукты и яйца, овощи, фрукты"
  }
]
```

---

### POST /vibes — создать тип вайба

Auth: `X-Terminal-Token`

**Request body**
```json
{
  "name": "Здоровье и лёгкость",
  "description": "Фрукты, овощи, злаки — питание без лишнего",
  "llm_context": "Categories: Фрукты, Овощи, Злаки, Молочные продукты. Focus on healthy, light eating."
}
```

**Response 201** — VibeOut (с полем `id`)
**Response 409** — name уже занято

---

### PUT /vibes/{vibe_id} — обновить тип вайба

Auth: `X-Terminal-Token`

**Request body** (все поля опциональны)
```json
{
  "name": "...",
  "description": "...",
  "llm_context": "..."
}
```

**Response 200** — обновлённый VibeOut
**Response 404** — vibe_id не найден
**Response 409** — name конфликт

---

### DELETE /vibes/{vibe_id} — удалить тип вайба

Auth: `X-Terminal-Token`

Каскадно сбрасывает `users.vibe_type_id` (ON DELETE SET NULL).

**Response 204**
**Response 404** — vibe_id не найден

---

### GET /users/me/vibe — получить текущий вайб пользователя

Auth: `Bearer`

**Response 200**
```json
{ "vibe_id": "uuid | null" }
```

`vibe_id = null`, если пользователь ещё не выбрал направление.

**Response 404** — пользователь не найден

---

### PUT /users/me/vibe — выбрать / сменить / сбросить вайб

Auth: `Bearer`

**Request body**
```json
{ "vibe_id": "uuid" }    // установить
{ "vibe_id": null }      // сбросить вайб
```

**Response 200**
```json
{ "vibe_id": "uuid | null" }
```

**Response 404** — vibe_id не найден

---

## Составные задания (Task Items)

### GET /challenges — список активных заданий (обновлённый ответ)

Auth: `Bearer` (существующий эндпоинт)

Поле `items` добавляется к каждому заданию:

```json
{
  "id": "uuid",
  "title": "Собери всё для салата Цезарь",
  "status": "открыто",
  "reward_type": "gift",
  "reward_rub": "0.00",
  "deadline": "2026-09-13T12:00:00Z",
  "quantity_target": 2,
  "quantity_current": 1,
  "items": [
    {
      "id": "uuid",
      "label": "Куриное филе",
      "criterion_type": "product",
      "criterion_entity_id": "uuid",
      "quantity_target": 2,
      "quantity_current": 1
    },
    {
      "id": "uuid",
      "label": "Яйца",
      "criterion_type": "product",
      "criterion_entity_id": "uuid",
      "quantity_target": 1,
      "quantity_current": 0
    }
  ]
}
```

Для заданий без составных пунктов (legacy / одиночный критерий): `items` содержит 1 элемент, совпадающий с task-уровневыми полями.

---

## Награды (Rewards)

### GET /rewards — список активных наград пользователя

Auth: `Bearer`

**Response 200**
```json
[
  {
    "id": "uuid",
    "reward_type": "gift",
    "description": "1 шоколадка Milka бесплатно",
    "criterion_type": "product",
    "criterion_entity_id": "uuid",
    "quantity": 1,
    "status": "active",
    "valid_to": "2026-09-20T00:00:00Z",
    "applicable": true
  }
]
```

`applicable: bool` — true если в последней запрошенной корзине есть подходящий товар. При запросе без корзины — всегда false (клиент проверяет при просмотре корзины).

---

## Корзина и чек (изменения в существующих эндпоинтах)

### POST /basket/preview — предпросмотр с учётом подарков

Существующий эндпоинт. Response расширяется:

```json
{
  "items": [...],
  "subtotal": "650.00",
  "gift_discounts": [
    {
      "gift_reward_id": "uuid",
      "description": "1 шоколадка бесплатно",
      "applied_to_item_id": "uuid",
      "discount_rub": "89.90"
    }
  ],
  "total": "560.10"
}
```

### POST /basket/checkout (POST /receipts) — создание чека с подарками

Auth: `Bearer` + `X-Terminal-Token`

При создании чека: gift_reward помечается как `used`. Строка чека с бесплатным товаром: `paid_price = 0`.

---

## Примечания по security

- CRUD вайбов: только `X-Terminal-Token`. Отсутствие / невалидный токен → 401.
- Выбор вайба пользователем: только `Bearer`. 401 без токена.
- GET /vibes: публичный (без auth).
- GET /rewards: только `Bearer`.
