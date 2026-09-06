# Data Model: Реферальная программа

Все таблицы — PostgreSQL. Идентификаторы — UUID. Даты — `TIMESTAMPTZ`.  
`inviter_id` / `invitee_id` / `loyalty_card_id` = `users.id`.

Часовой пояс продукта: `Europe/Moscow`.  
Окно скидки и окно покупки: `activated_at + 7 days` (168 часов).  
Порог реактивации: нет строк `receipts` с `purchase_date >= now - 180 days`.

## Новые таблицы

### `referral_code`

Выданный приглашающим одноразовый код. Связка появляется отдельной строкой только после активации.

| Колонка | Тип | Nullable | Default | Ограничение |
|---------|-----|----------|---------|-------------|
| id | UUID | NO | `gen_random_uuid()` | PK |
| code | VARCHAR(6) | NO | — | UNIQUE; `CHECK (code ~ '^[A-Za-z0-9]{6}$')` |
| inviter_id | UUID | NO | — | FK → `users.id` ON DELETE CASCADE |
| created_at | TIMESTAMPTZ | NO | `now()` | |

**Индексы**: PK; UNIQUE `code` (регистр значим, collation default); `(inviter_id, created_at DESC)` для `GET /referrals`.

**Инварианты**:
- Каждый insert — новый код, отличный от всех существующих.
- Неиспользованный код: нет строки `referral_link` с этим `referral_code_id`.
- После активации код не удаляется и не переиспользуется.

---

### `referral_link`

Факт активации. Снимки настроек замораживаются здесь, не перечитываются из env при награде.

| Колонка | Тип | Nullable | Default | Ограничение |
|---------|-----|----------|---------|-------------|
| id | UUID | NO | `gen_random_uuid()` | PK |
| referral_code_id | UUID | NO | — | FK → `referral_code.id` ON DELETE RESTRICT, **UNIQUE** |
| inviter_id | UUID | NO | — | FK → `users.id` ON DELETE CASCADE |
| invitee_id | UUID | NO | — | FK → `users.id` ON DELETE CASCADE |
| activated_at | TIMESTAMPTZ | NO | `now()` | |
| discount_percent | NUMERIC(5,2) | NO | — | `CHECK (0 <= discount_percent AND discount_percent <= 100)` |
| inviter_coupons | INT | NO | — | `CHECK (inviter_coupons >= 0)` |
| inviter_cashback_rub | INT | NO | — | `CHECK (inviter_cashback_rub >= 0)` |
| discount_valid_to | TIMESTAMPTZ | NO | — | `= activated_at + 7 days` |
| purchase_window_until | TIMESTAMPTZ | NO | — | `= activated_at + 7 days` (то же окно) |
| discount_id | UUID | YES | — | FK → `discounts.id` ON DELETE SET NULL |
| reward_status | VARCHAR(24) | NO | `'awaiting_purchase'` | `CHECK IN ('awaiting_purchase', 'rewarded')` |
| qualifying_receipt_id | UUID | YES | — | FK → `receipts.id` ON DELETE SET NULL; UNIQUE если NOT NULL |
| rewarded_at | TIMESTAMPTZ | YES | — | NOT NULL ⇔ `reward_status = 'rewarded'` |

**Индексы**:
- UNIQUE `referral_code_id` — один код → одна активация (гонка двух invitee).
- `(invitee_id, activated_at DESC)` — поиск активной связки invitee.
- `(inviter_id, activated_at DESC)`.
- UNIQUE `qualifying_receipt_id` WHERE NOT NULL.

**Инварианты (сервис + БД)**:
- `inviter_id ≠ invitee_id`.
- `inviter_id` совпадает с `referral_code.inviter_id`.
- `reward_status = 'rewarded'` ⇒ `qualifying_receipt_id IS NOT NULL`, `rewarded_at IS NOT NULL`.
- `reward_status = 'awaiting_purchase'` ⇒ оба NULL.
- Одновременно «активных» связок у invitee не больше одной: сервис проверяет `now < greatest(discount_valid_to, purchase_window_until)` у незакрытой связки. Частичный индекс не вводим — окно скользящее.

**Вычисляемый статус для API** (не колонка):

| Условие | `status` |
|---------|----------|
| Нет `referral_link` | `issued` |
| Есть link, `reward_status = 'rewarded'` | `rewarded` |
| Есть link, `now <= purchase_window_until`, награда не выдана | `awaiting_purchase` |
| Есть link, `now > purchase_window_until`, награда не выдана | `expired` |

---

## Изменения существующих таблиц

### `discount_link_types`

| Изменение | Детали |
|-----------|--------|
| SEED `'all'` | `INSERT … name='all' ON CONFLICT DO NOTHING`. Калькулятор уже читает этот тип; сид 005 его не создаёт. |

### `discounts`

Новых колонок нет. Строка скидки приглашённого:

| Поле | Значение |
|------|----------|
| `discount_type` | `персональная` |
| `link_type` | `all` |
| `entity_id` | NULL |
| `value_type` | `percent` |
| `value` | снимок `discount_percent` |
| `loyalty_card_id` | `invitee_id` |
| `scope` | `all` |
| `valid_from` | `activated_at` |
| `valid_to` | `discount_valid_to` |

По истечении `valid_to` калькулятор сам отсекает скидку (действующий `date_filter`).

### `coupon_transaction`

| Изменение | Детали |
|-----------|--------|
| CHECK `type` | добавить `'referral'` |
| ADD `related_referral_link_id` | UUID NULL, FK → `referral_link.id` ON DELETE SET NULL |
| INDEX `ux_coupon_tx_referral` | UNIQUE `(related_referral_link_id)` WHERE `type = 'referral'` |

Инвариант: `type='referral'` ⇒ `amount = inviter_coupons` (> 0, иначе строки нет), `related_referral_link_id IS NOT NULL`, task/spin/week NULL.

### `coupon_account`

Без изменений схемы. Начисление идёт через существующий баланс + `FOR UPDATE`.

### `points_transaction`

| Изменение | Детали |
|-----------|--------|
| ADD `related_referral_link_id` | UUID NULL, FK → `referral_link.id` ON DELETE SET NULL |
| INDEX `ux_points_tx_earn_referral` | UNIQUE `(related_referral_link_id)` WHERE `type = 'earn' AND related_referral_link_id IS NOT NULL` |

Инвариант: earn за реферала ⇒ `related_task_id` и `related_spin_id` NULL, `related_referral_link_id` NOT NULL. Формула баллов — как `award_for_spin` / `award_for_task`.

### `receipts`

Без изменений схемы. Чтение: наличие чеков за 180 дней (реактивация); `id` нового чека → `qualifying_receipt_id`.

### `users`

Без изменений схемы.

---

## Связи

```text
users (inviter) 1 ── * referral_code
referral_code 1 ── 0..1 referral_link
users (invitee) 1 ── * referral_link
referral_link 0..1 ── 1 discounts
referral_link 0..1 ── 1 receipts          (квалифицирующий чек)
referral_link 0..1 ── 1 coupon_transaction (type=referral)
referral_link 0..1 ── 1 points_transaction (earn)
```

---

## Состояния и переходы

```text
[issue]     referral_code создан
               │
               │ activate (register | login+180d)
               ▼
         awaiting_purchase  (+ Discount живёт до discount_valid_to)
               │
               ├─ первый чек invitee при now ≤ purchase_window_until ──► rewarded
               │
               └─ now > purchase_window_until без чека ──► expired (только в API)
```

Обратных переходов нет. Повторная активация того же кода невозможна (UNIQUE `referral_code_id`).

---

## Валидация (сервис)

- Генерация: только `[A-Za-z0-9]{6}`, повтор при UNIQUE conflict ≤ 8 раз, иначе 503.
- Активация: код существует; нет link; `inviter ≠ invitee`; нет активной связки invitee; для существующего user — нет чеков за 180 дней.
- Награда: ровно один раз; 0 купонов / 0 ₽ не пишут леджер; оба ненуля — две операции в той же транзакции, что чек.
- Env при старте/активации: см. research R9.
