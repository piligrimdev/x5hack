# Quickstart: Валидация фичи

## Предусловия

```bash
cd web
docker compose up -d postgres
poetry run alembic upgrade head   # применяет новые миграции M1–M5
```

Нужны env vars: `TERMINAL_TOKEN=test-token`, `JWT_SECRET=...`.

---

## Сценарий 1: Вайб — создание, выбор, сброс

```bash
# POS создаёт вайб
curl -X POST http://localhost:8000/vibes \
  -H "X-Terminal-Token: test-token" \
  -H "Content-Type: application/json" \
  -d '{"name":"Тест-вайб","description":"desc","llm_context":"context"}'
# Ожидание: 201, тело содержит id

VIBE_ID="<id из ответа>"

# Пользователь получает список
curl http://localhost:8000/vibes
# Ожидание: массив, содержит Тест-вайб

# Пользователь выбирает вайб
curl -X PUT http://localhost:8000/users/me/vibe \
  -H "Authorization: Bearer $USER_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"vibe_id\": \"$VIBE_ID\"}"
# Ожидание: 200, vibe_id совпадает

# Удаление вайба кассовым аппаратом
curl -X DELETE http://localhost:8000/vibes/$VIBE_ID \
  -H "X-Terminal-Token: test-token"
# Ожидание: 204

# Проверка, что вайб сброшен у пользователя
curl http://localhost:8000/users/me \
  -H "Authorization: Bearer $USER_TOKEN"
# Ожидание: vibe_id = null
```

**Проверяемые требования**: FR-014, FR-015, FR-016, SC-003, SC-004, SC-006.

---

## Сценарий 2: Составное задание — прогресс по пунктам

```bash
# Создать задание с 2 пунктами (через synth или seed-скрипт)
# task_item 1: Куриное филе, qty_target=2
# task_item 2: Яйца, qty_target=1

# Получить задания
curl http://localhost:8000/challenges \
  -H "Authorization: Bearer $USER_TOKEN"
# Ожидание: в поле items — 2 пункта, quantity_current=0 у обоих

# Создать чек с куриным филе 2 шт (без яиц)
curl -X POST http://localhost:8000/receipts \
  -H "Authorization: Bearer $USER_TOKEN" \
  -H "X-Terminal-Token: test-token" \
  -H "Content-Type: application/json" \
  -d '{"store_id":"...","items":[{"product_id":"<filé_id>","quantity":2}]}'

# Проверить прогресс задания
curl http://localhost:8000/challenges \
  -H "Authorization: Bearer $USER_TOKEN"
# Ожидание:
#   items[0] (Куриное филе): quantity_current=2, quantity_target=2
#   items[1] (Яйца): quantity_current=0, quantity_target=1
#   task.status = "открыто" (НЕ выполнено!)

# Создать чек с яйцами 1 шт
curl -X POST http://localhost:8000/receipts \
  -H "Authorization: Bearer $USER_TOKEN" \
  -H "X-Terminal-Token: test-token" \
  -H "Content-Type: application/json" \
  -d '{"store_id":"...","items":[{"product_id":"<egg_id>","quantity":1}]}'

# Проверить задание
curl http://localhost:8000/challenges/history \
  -H "Authorization: Bearer $USER_TOKEN"
# Ожидание: задание в статусе "выполнено"
```

**Проверяемые требования**: FR-001, FR-002, FR-003, FR-004, SC-001.

---

## Сценарий 3: Награда-подарок — применение при расчёте

```bash
# Предусловие: выполнено задание с reward_type='gift'
# (создать gift_reward вручную через seed или выполнить такое задание)

# Список наград
curl http://localhost:8000/rewards \
  -H "Authorization: Bearer $USER_TOKEN"
# Ожидание: массив с 1 записью, status='active', criterion_type='product'

PRODUCT_ID="<id товара из награды>"

# Предпросмотр корзины с подходящим товаром
curl -X POST http://localhost:8000/basket/preview \
  -H "Authorization: Bearer $USER_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"items\":[{\"product_id\":\"$PRODUCT_ID\",\"quantity\":1}]}"
# Ожидание: gift_discounts содержит запись, total < subtotal

# Оформить чек
curl -X POST http://localhost:8000/receipts \
  -H "Authorization: Bearer $USER_TOKEN" \
  -H "X-Terminal-Token: test-token" \
  -H "Content-Type: application/json" \
  -d "{\"store_id\":\"...\",\"items\":[{\"product_id\":\"$PRODUCT_ID\",\"quantity\":1}]}"
# Ожидание: paid_price=0 для товара в составе чека

# Проверить статус награды
curl http://localhost:8000/rewards \
  -H "Authorization: Bearer $USER_TOKEN"
# Ожидание: status='used' или награда отсутствует в активных
```

**Проверяемые требования**: FR-007–FR-012, SC-002.

---

## Сценарий 4: Вайб влияет на генерацию заданий

```bash
# Установить вайб "Здоровье и лёгкость"
curl -X PUT http://localhost:8000/users/me/vibe \
  -H "Authorization: Bearer $USER_TOKEN" \
  -d '{"vibe_id":"<health_vibe_id>"}'

# Запустить генерацию заданий (через celery task или dev-эндпоинт)
curl -X POST http://localhost:8000/challenges/generate \
  -H "Authorization: Bearer $USER_TOKEN"

# Проверить задания
curl http://localhost:8000/challenges \
  -H "Authorization: Bearer $USER_TOKEN"
# Ожидание: хотя бы одно задание относится к категориям вайба
# (Фрукты, Овощи, Злаки, Молочные продукты)
```

**Проверяемые требования**: FR-016, FR-018, SC-005.

---

## Проверка безопасности

```bash
# CRUD вайбов без токена — должно вернуть 401
curl -X POST http://localhost:8000/vibes \
  -H "Content-Type: application/json" \
  -d '{"name":"X","description":"Y","llm_context":"Z"}'
# Ожидание: 401

# Неверный токен
curl -X DELETE http://localhost:8000/vibes/$VIBE_ID \
  -H "X-Terminal-Token: wrong-token"
# Ожидание: 401
```

**Проверяемые требования**: SC-006.
