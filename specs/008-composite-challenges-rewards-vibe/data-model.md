# Data Model: Составные задания, типы наград и вайб

## Новые таблицы

### `vibe_type`

Управляемый кассовым аппаратом каталог типов вайба.

| Колонка | Тип | Nullable | Описание |
|---------|-----|----------|----------|
| id | UUID PK | NO | |
| name | VARCHAR(100) UNIQUE | NO | Отображаемое название |
| description | TEXT | NO | Описание для пользователя |
| llm_context | TEXT | NO | Текст, передаваемый LLM при генерации |
| created_at | TIMESTAMPTZ | NO | server_default=now() |
| updated_at | TIMESTAMPTZ | NO | server_default=now() |

Constraints: `uq_vibe_type_name`

---

### `task_item`

Один независимый пункт составного задания. Задание может иметь N≥1 пунктов.

| Колонка | Тип | Nullable | Описание |
|---------|-----|----------|----------|
| id | UUID PK | NO | |
| task_id | UUID FK task.id CASCADE | NO | |
| criterion_type | VARCHAR(20) | NO | CHECK IN ('product', 'category', 'brand') |
| criterion_entity_id | UUID | NO | ID продукта или категории |
| quantity_target | INTEGER | NO | CHECK >= 1 |
| quantity_current | INTEGER | NO | CHECK >= 0; DEFAULT 0 |
| label | VARCHAR(200) | YES | Человекочитаемое название пункта |

Index: `ix_task_item_task_id`

**Инвариант**: task считается выполненным, когда `quantity_current >= quantity_target` для ВСЕХ его `task_item`.

---

### `gift_reward`

Активная награда-подарок пользователя — результат выполнения задания с `reward_type='gift'`.

| Колонка | Тип | Nullable | Описание |
|---------|-----|----------|----------|
| id | UUID PK | NO | |
| task_id | UUID FK task.id SET NULL | YES | Источник (задание) |
| loyalty_card_id | UUID FK users.id CASCADE | NO | |
| criterion_type | VARCHAR(20) | NO | CHECK IN ('product', 'category') |
| criterion_entity_id | UUID | NO | ID продукта или категории |
| quantity | INTEGER | NO | CHECK >= 1; сколько единиц бесплатно |
| status | VARCHAR(20) | NO | CHECK IN ('active', 'used', 'expired') DEFAULT 'active' |
| valid_to | TIMESTAMPTZ | NO | Срок действия |
| created_at | TIMESTAMPTZ | NO | server_default=now() |

Index: `ix_gift_reward_user_status` (loyalty_card_id, status) — для быстрого поиска активных наград.

---

## Изменения существующих таблиц

### `task`

| Изменение | Детали |
|-----------|--------|
| CHECK `reward_type` | `IN ('discount', 'cashback', 'gift')` ← было `IN ('discount')` |

Поля `criterion_type`, `criterion_entity_id`, `quantity_target`, `quantity_current` **остаются** на таблице — используются для backward compatibility с синтетикой, историей и клиентами, которые смотрят только на Task-уровень. Прогресс по составным заданиям отслеживается в `task_item.quantity_current`.

### `users`

| Изменение | Детали |
|-----------|--------|
| ADD `vibe_type_id` | UUID FK vibe_type.id ON DELETE SET NULL, nullable |
| DROP `vibe_category` | Заменяется FK (после миграции данных) |
| DROP `vibe_month` | Больше не нужен; вайб не ротируется детерминированно |

---

## Миграции (порядок)

### M1: `create_vibe_type`
```
CREATE TABLE vibe_type (id, name UNIQUE, description, llm_context, created_at, updated_at)
```
Seed: вставить 6 записей из `VIBE_CATEGORIES` в `synth/challenges.py:101`.
`llm_context` для каждого вайба — список категорий из словаря (JSON или comma-separated).

### M2: `add_user_vibe_type_fk`
```
ALTER TABLE users ADD COLUMN vibe_type_id UUID REFERENCES vibe_type(id) ON DELETE SET NULL;
UPDATE users SET vibe_type_id = (
    SELECT id FROM vibe_type WHERE name = users.vibe_category
) WHERE users.vibe_category IS NOT NULL;
ALTER TABLE users DROP COLUMN vibe_category;
ALTER TABLE users DROP COLUMN vibe_month;
```

### M3: `create_task_item`
```
CREATE TABLE task_item (id, task_id FK, criterion_type, criterion_entity_id,
                        quantity_target, quantity_current DEFAULT 0, label)
-- Backfill: один пункт для каждого существующего task
INSERT INTO task_item (id, task_id, criterion_type, criterion_entity_id,
                       quantity_target, quantity_current)
SELECT gen_random_uuid(), id, criterion_type, criterion_entity_id,
       quantity_target, quantity_current FROM task;
```

### M4: `extend_task_reward_type_check`
```
ALTER TABLE task DROP CONSTRAINT ck_task_reward_type;
ALTER TABLE task ADD CONSTRAINT ck_task_reward_type
    CHECK (reward_type IN ('discount', 'cashback', 'gift'));
```

### M5: `create_gift_reward`
```
CREATE TABLE gift_reward (id, task_id FK SET NULL, loyalty_card_id FK CASCADE,
                          criterion_type, criterion_entity_id,
                          quantity, status DEFAULT 'active', valid_to, created_at)
```

---

## Диаграмма связей (ключевые)

```
vibe_type (1) ──── (0..N) users
task (1) ──────── (1..N) task_item        ← новые пункты задания
task (1) ──────── (0..1) gift_reward      ← подарочная награда
task (1) ──────── (0..N) task_criterion   ← метадата (без изменений)
users (1) ─────── (0..N) gift_reward
```

---

## Состояния gift_reward

```
active → used      (применён при расчёте чека)
active → expired   (valid_to < now(), обнаруживается при запросе)
```
