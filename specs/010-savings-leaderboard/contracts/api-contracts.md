# API Contracts: Лидерборд экономии магазина

Сервис: FastAPI `web/`, базовый URL `http://localhost:8000`.  
Auth: `Authorization: Bearer <access_token>` (`CurrentUserUUID` = `users.id`).

Без токена — **401** на путь ниже. Тело 401 без данных рейтинга.

Клиент не передаёт магазин, месяц и чужие id. Всё вычисляет сервер.

---

## GET /leaderboard — персональный рейтинг

**Response 200** — всегда для авторизованного пользователя.

### Нет «своего» магазина

```json
{
  "status": "no_home_store",
  "period": {
    "year": 2026,
    "month": 9,
    "timezone": "Europe/Moscow"
  },
  "store": null,
  "participant_count": 0,
  "me": null,
  "entries": [],
  "solo": false
}
```

Клиент: пустое состояние «совершите покупку, чтобы увидеть рейтинг магазина».

### Магазин есть, зритель в таблице месяца

```json
{
  "status": "ready",
  "period": {
    "year": 2026,
    "month": 9,
    "timezone": "Europe/Moscow"
  },
  "store": {
    "id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
    "name": "Пятёрочка, d_03"
  },
  "participant_count": 12,
  "me": {
    "rank": 3,
    "savings_percent": 12,
    "beats_percent": 75,
    "in_top": true
  },
  "entries": [
    {
      "rank": 1,
      "label": "Покупатель 247",
      "savings_percent": 18,
      "is_me": false
    },
    {
      "rank": 2,
      "label": "Покупатель 512",
      "savings_percent": 15,
      "is_me": false
    },
    {
      "rank": 3,
      "label": "Покупатель 108",
      "savings_percent": 12,
      "is_me": true
    }
  ],
  "solo": false
}
```

Инварианты:
- `entries.length ≤ 10`
- сумма мест competition-схемы: одинаковый `savings_percent` → одинаковый `rank`
- в JSON нет `user_id`, телефона, адреса, ФИО
- `store.name` = `"{format_name}, {geo_cluster}"`, без адреса
- `me.beats_percent` — целое 0…100
- если `me.in_top == false`, ни у одной строки `is_me != true`; клиент рисует «Вы» из `me`

### Магазин есть, зритель не покупал в этом месяце

`status: "ready"`, `store` заполнен, `me: null`, `entries` — топ участников месяца (может быть `[]`), `solo: false`.

Клиент: магазин и список соседей + текст «место появится после покупки в этом месяце», без «0%» и «N из M» для зрителя.

### Один участник — сам зритель

`participant_count: 1`, `me.rank: 1`, `me.beats_percent: 0`, `me.in_top: true`, `solo: true`, одна строка `entries` с `is_me: true`.

Клиент: пояснение, что рядом пока нет других покупателей.

### Ошибка сервера

5xx. Клиент: «не удалось загрузить» + повтор. Экран Аппи не уничтожается (см. план навигации).

---

## Поля, которых нет в контракте

- абсолютные рубли экономии / чека как ключ сортировки или замена `savings_percent`
- query `store_id`, `month`, `user_id`
- пагинация полного списка участников
- история мест

---

## Соответствие требованиям

| Требование | Как закрыто |
|------------|-------------|
| FR-002, FR-003 | один GET, JWT, клиент не считает места |
| FR-004–FR-008 | home store и когорта только на сервере |
| FR-009–FR-013 | в ответе только `savings_percent` и `rank` |
| FR-014–FR-018 | `store.name`, `me`, топ-10, `is_me`, анонимный `label` |
| FR-019 | `status` + `me is null` + `solo` |
