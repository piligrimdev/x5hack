# Data Model: Лидерборд экономии магазина

Новых таблиц нет. Рейтинг — вычисляемый снимок поверх существующих `receipts`, `receipt_items`, `stores`, `store_formats`, `users`.

Идентификаторы — UUID. Даты чеков — `TIMESTAMPTZ`. Календарный месяц — `Europe/Moscow`.  
`loyalty_card_id` на чеке = `users.id`.

---

## Существующие сущности (чтение)

### `receipts`

Нужные поля: `id`, `loyalty_card_id` (nullable), `store_id` (NOT NULL в схеме; для голосования всё равно фильтруем), `purchase_date`, `cashback_applied_rub`.

Индексы уже есть: `loyalty_card_id`, `store_id`, `purchase_date`.

### `receipt_items`

Нужные поля: `receipt_id`, `quantity`, `base_price_at_purchase`, `discounted_amount`.

Экономия скидок по чеку: `SUM(discounted_amount × quantity)`.  
База: `SUM(base_price_at_purchase × quantity)`.

### `stores` + `store_formats`

`stores.id`, `stores.geo_cluster`, `store_formats.name`.  
`stores.address` **не** входит в снимок рейтинга.

Публичное имя магазина (не колонка): `"{format.name}, {geo_cluster}"`.

---

## Вычисляемые сущности

### HomeStoreVote

Один магазин в окне последних покупок пользователя.

| Поле | Тип | Смысл |
|------|-----|--------|
| loyalty_card_id | UUID | владелец чеков |
| store_id | UUID | магазин |
| vote_count | INT | сколько раз store_id в окне 20 |
| last_purchase_at | TIMESTAMPTZ | самая поздняя покупка этого магазина в окне |

Окно: до 20 чеков с непустым `store_id`, порядок `purchase_date DESC, id DESC`.

### HomeStore

Результат правила FR-004–FR-006.

| Поле | Тип | Смысл |
|------|-----|--------|
| loyalty_card_id | UUID | |
| store_id | UUID | победитель |
| store_name | str | `"{format_name}, {geo_cluster}"` |

**Правила**: max(`vote_count`); ничья → max(`last_purchase_at`); ничья → min(`store_id`).  
Нет ни одного голоса → сущности нет (`status = no_home_store`).

### MonthlySavingsRate

| Поле | Тип | Смысл |
|------|-----|--------|
| loyalty_card_id | UUID | |
| period_start | TIMESTAMPTZ | 1-е 00:00 Europe/Moscow |
| period_end | TIMESTAMPTZ | 1-е следующего месяца |
| total_saved | Decimal | скидки + кешбек за месяц, все магазины |
| total_base | Decimal | сумма полочных цен за месяц |
| savings_percent | INT | `round(total_saved / total_base * 100)`, clamp 0…100 |

**Валидация**: строка существует только если `total_base > 0`. Иначе пользователь не участник месяца.

### LeaderboardEntry

| Поле | Тип | Смысл |
|------|-----|--------|
| rank | INT | competition rank ≥ 1 |
| label | str | `"Покупатель NNN"` или логический «Вы» на клиенте |
| savings_percent | INT | 0…100 |
| is_me | bool | строка зрителя |

`label` для чужих: `"Покупатель {100..999}"` из стабильного хеша `loyalty_card_id` (research R8). UUID в контракт не попадает.

### LeaderboardSnapshot

Персональный ответ `GET /leaderboard`.

| Поле | Тип | Смысл |
|------|-----|--------|
| status | enum | `no_home_store` \| `ready` |
| period.year / period.month | INT | месяц снимка |
| period.timezone | str | всегда `Europe/Moscow` |
| store | HomeStore public \| null | |
| participant_count | INT | M — число участников месяца в этом магазине |
| me | {rank, savings_percent, beats_percent, in_top} \| null | |
| entries | LeaderboardEntry[0..10] | топ по проценту |
| solo | bool | `participant_count == 1` и зритель в таблице |

**Инварианты**:
- `status = no_home_store` ⇒ `store is null`, `me is null`, `entries = []`, `participant_count = 0`, `solo = false`.
- Все `entries` и `me` принадлежат одному `store_id`.
- В `entries` нет двух разных `rank` при одинаковом `savings_percent` (одно место на процент).
- `len(entries) ≤ 10`.
- Если `me.in_top == true`, ровно одна строка `entries` с `is_me == true`.
- Если `me.in_top == false`, в `entries` нет `is_me`.
- `beats_percent = floor(count(percent < me.percent) / participant_count * 100)`.
- Рубли не являются ключом сортировки.

Нет state-машины на диске: снимок живёт только в ответе запроса.

---

## Связи

```text
User (users.id)
  └── Receipt[] (loyalty_card_id)
        ├── store → Store → StoreFormat
        └── ReceiptItem[]  → total_base, discount_saved

HomeStore        = f(last 20 Receipt.store_id)
MonthlySavings   = f(Receipt + ReceiptItem за месяц, все магазины)
Leaderboard      = users with same HomeStore ∧ MonthlySavings exists
```

---

## Что не моделируем

- Снэпшоты истории мест, лиги, награды за место.
- `user_home_store` / rating table.
- Геокластер как единица когорты (бэклог районного рейтинга).
- ПД пользователя в строке рейтинга.
