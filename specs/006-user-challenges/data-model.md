# Data Model — Персональные челленджи

Схема PostgreSQL 16 + SQLAlchemy 2.x. Единая миграция Alembic `f4a5b6c7d8e9_add_task_tables.py`.

## Диаграмма связей

```
users (existing)
  └── loyalty_card_id (used as user_id)
        │
        ├─── task (1..N)
        │      │
        │      ├─── task_criterion (1..N) [EAV]
        │      ├─── task_receipt_increment (0..N) [dedupe]
        │      └─── reward_id → discounts.id (nullable, no FK, MVP='discount')
        │
        └─── challenge_generation_log (0..N) [audit]

receipts (existing) ──── task_receipt_increment (via receipt_id)

discounts (existing, extended with value_type + link_task_id)
```

## Существующие таблицы, изменяемые миграцией

### `discounts` — расширение

Добавляемые колонки:

| Колонка | Тип | Констрейнт | Дефолт | Назначение |
|---|---|---|---|---|
| `value_type` | VARCHAR(20) | `CHECK (value_type IN ('percent', 'fixed_rub'))` | `'percent'` | Тип значения `value`. Существующие скидки — процент; награды заданий — `fixed_rub`. |
| `link_task_id` | UUID | NULL, без FK | NULL | Обратная ссылка на задание, чьё выполнение создало эту скидку (для аудита). Без FK — задание может быть удалено без каскада. |

Затрагиваемый код: `web/src/webx5/services/discount_calculator.py::DiscountCalculatorService.apply_discount` — новая ветка для `value_type='fixed_rub'`.

## Новые таблицы

### `task_status` — словарь статусов

| Колонка | Тип | Констрейнт | Назначение |
|---|---|---|---|
| `id` | UUID | PK, `default uuid_generate_v4()` | |
| `name` | VARCHAR(50) | UNIQUE, NOT NULL | Значения: `открыто`, `выполнено`, `провалено`, `истекло` |

Сидируется скриптом `web/scripts/seed_task_status.py`.

### `task` — задание

| Колонка | Тип | Констрейнт | Дефолт | Назначение |
|---|---|---|---|---|
| `id` | UUID | PK | `uuid_generate_v4()` | |
| `loyalty_card_id` | UUID | FK → `users.id ON DELETE CASCADE`, NOT NULL, INDEX | | Владелец задания (в текущей схеме `users.id` = loyalty card id). |
| `task_status_id` | UUID | FK → `task_status.id ON DELETE RESTRICT`, NOT NULL, INDEX | | Статус. |
| `issued_at` | TIMESTAMPTZ | NOT NULL | `now()` | Момент выдачи задания. |
| `deadline` | TIMESTAMPTZ | NOT NULL | `now() + interval '7 days'` | Дедлайн 7 дней (FR-003). Дублируется на уровне приложения (может быть переопределён). |
| `criterion_type` | VARCHAR(20) | `CHECK (criterion_type IN ('product', 'category', 'brand'))`, NOT NULL | | Тип основного критерия (совместимо с `context/schema.md`). |
| `criterion_entity_id` | UUID | NOT NULL | | ID сущности критерия (полиморфная ссылка). |
| `quantity_target` | INTEGER | `CHECK (quantity_target >= 1)`, NOT NULL | `1` | Целевое количество (для основного kind, обычно 1). |
| `quantity_current` | INTEGER | `CHECK (quantity_current >= 0)`, NOT NULL | `0` | Текущий прогресс. |
| `title` | VARCHAR(200) | NOT NULL | | Заголовок из скрипта (`challenge_title`). |
| `description` | TEXT | NOT NULL | | Описание из скрипта (`description`). |
| `mechanic` | VARCHAR(200) | NOT NULL | | Механика (текст, из `mechanic` скрипта — displayable, не машинно-читаемый). |
| `reward_rub` | NUMERIC(10, 2) | `CHECK (reward_rub >= 0)`, NOT NULL | | Сумма награды в рублях (из скрипта; хранится отдельно от Discount.value для аудита). |
| `reasoning` | TEXT | NULL | | Reasoning из скрипта (LLM или детерминированный). Дублируется в `challenge_generation_log`, но здесь — для быстрого чтения в API. |
| `path` | VARCHAR(30) | `CHECK (path IN ('personal', 'generic', 'generic_fallback', 'no_challenge', 'personal_dry_run'))`, NOT NULL | | Из скрипта: какой путь генерации был использован. |
| `model` | VARCHAR(100) | NULL | | Название LLM-модели (для path='personal'/'generic_fallback'); NULL для деterministic путей. |
| `reward_type` | VARCHAR(20) | `CHECK (reward_type IN ('discount'))`, NOT NULL | `'discount'` | Мост FR-011a: тип связанной награды. В MVP только 'discount'. |
| `reward_id` | UUID | NULL, без FK | NULL | Мост FR-011a: указатель на строку в таблице reward (`discounts.id` для 'discount'). |
| `completed_at` | TIMESTAMPTZ | NULL | | Момент перевода в 'выполнено'. |

Индексы:
- `idx_task_user_status` на `(loyalty_card_id, task_status_id)` — для запроса активных заданий пользователя.
- `idx_task_status_deadline` на `(task_status_id, deadline)` — для expire sweep (только 'открыто' + `deadline < now()`).

State transitions:
- `открыто → выполнено`: когда все `task_criterion` выполнены (FR-007). Устанавливает `completed_at`, `reward_id`.
- `открыто → истекло`: когда `expire_tasks` находит `deadline < now()` (FR-004).
- `открыто → провалено`: не используется в MVP (зарезервировано для будущего антифрода).
- `выполнено`/`истекло`/`провалено`: terminal.

### `task_criterion` — EAV критерии

| Колонка | Тип | Констрейнт | Назначение |
|---|---|---|---|
| `id` | UUID | PK, `default uuid_generate_v4()` | |
| `task_id` | UUID | FK → `task.id ON DELETE CASCADE`, NOT NULL, INDEX | Родитель. |
| `kind` | VARCHAR(50) | NOT NULL | Тип критерия. Известные: `item_quantity`, `spend_threshold_rub`. Новые добавляются без миграции. |
| `key` | VARCHAR(100) | NULL | Опциональный ключ (для kind, требующих доп. параметра). В MVP не используется, зарезервирован. |
| `value_num` | NUMERIC(12, 2) | NULL | Числовое значение (для `spend_threshold_rub` — сумма; для `item_quantity` — quantity_target). |
| `value_text` | VARCHAR(500) | NULL | Строковое значение (для будущих текстовых kind). |
| `created_at` | TIMESTAMPTZ | NOT NULL, DEFAULT `now()` | |

Констрейнты:
- `CHECK (value_num IS NOT NULL OR value_text IS NOT NULL)` — хотя бы одно значение.

Индексы:
- `idx_task_criterion_task` на `(task_id)` — джойн с task.

Пример строк для задания `spend_threshold` («потрать 1500₽ за один поход и получи 15% на молоко»):
- `(kind='item_quantity', value_num=1)` — купить 1 позицию молока (совпадает с task.quantity_target).
- `(kind='spend_threshold_rub', value_num=1500)` — чек должен содержать `total_rub ≥ 1500`.

### `task_receipt_increment` — dedupe применения чека

| Колонка | Тип | Констрейнт | Назначение |
|---|---|---|---|
| `task_id` | UUID | FK → `task.id ON DELETE CASCADE`, NOT NULL | |
| `receipt_id` | UUID | FK → `receipts.id ON DELETE CASCADE`, NOT NULL | |
| `applied_at` | TIMESTAMPTZ | NOT NULL, DEFAULT `now()` | |

PK: `(task_id, receipt_id)` — гарантирует «этот чек применён к этому заданию не более одного раза».

Индексы:
- Обратный: `idx_tri_receipt` на `(receipt_id)` — для case «этот чек уже обработан».

### `challenge_generation_log` — audit

| Колонка | Тип | Констрейнт | Назначение |
|---|---|---|---|
| `id` | UUID | PK, `default uuid_generate_v4()` | |
| `user_id` | UUID | NOT NULL | Для кого генерировали (без FK — лог не должен блокировать удаление user'а). |
| `task_id` | UUID | NULL | Ссылка на созданное задание (NULL если path='no_challenge' или fallback без создания). Без FK. |
| `model` | VARCHAR(100) | NULL | LLM-модель (path='personal'). |
| `prompt` | TEXT | NULL | Системный + user prompt (только для 'personal'). |
| `response` | TEXT | NULL | Сырой ответ модели. |
| `path` | VARCHAR(30) | NOT NULL | Значение `path` из скрипта. |
| `reasoning` | TEXT | NULL | Reasoning из результата. |
| `error` | TEXT | NULL | Ошибка (для generic_fallback). |
| `challenge_type` | VARCHAR(30) | NOT NULL | `llm` / `spend_threshold` / `category_expansion` — какой тип адаптер запросил. |
| `created_at` | TIMESTAMPTZ | NOT NULL, DEFAULT `now()` | |

Индексы:
- `idx_cgl_user` на `(user_id, created_at DESC)` — просмотр истории генераций для пользователя.

## ORM (SQLAlchemy 2.x mapped classes)

Файлы:
- `web/src/webx5/entities/task.py`:
  - `class TaskStatus(Base): __tablename__ = "task_status"` — id, name.
  - `class Task(Base): __tablename__ = "task"` — все поля выше; `status: Mapped[TaskStatus] = relationship(lazy="joined")`.
  - `class TaskCriterion(Base): __tablename__ = "task_criterion"` — id, task_id, kind, key, value_num, value_text, created_at.
  - `class TaskReceiptIncrement(Base): __tablename__ = "task_receipt_increment"` — task_id (PK), receipt_id (PK), applied_at.
- `web/src/webx5/entities/challenge_log.py`:
  - `class ChallengeGenerationLog(Base): __tablename__ = "challenge_generation_log"` — все поля выше.

## Инварианты, проверяемые в приложении (не в БД)

1. **Только 3 активных задания** (FR-001, кроме saturated) — `TaskRepository.count_active_for_user(user_id) <= 3`. Гарантируется тем, что `generate_challenges` считает активные перед созданием и никогда не превышает 3.
2. **Task.criterion_entity_id ссылается на существующую сущность** соответствующего `criterion_type` — проверяется в адаптере при вставке (query существования Product/Category); при отсутствии — fallback на category (FR-021).
3. **`task.reward_id` соответствует `task.reward_type`** — в MVP всегда `discount` + существующий `discounts.id`. Проверяется в `TaskCompletionService` перед вставкой (SELECT существования Discount).
4. **`task.reasoning` дублируется с последней записью `challenge_generation_log.reasoning` для этого task_id** — обеспечивается транзакционно в `generate_challenges`.

## Миграция Alembic — план

Файл: `web/alembic/versions/f4a5b6c7d8e9_add_task_tables.py`.

```python
"""add task tables and extend discounts

Revision ID: f4a5b6c7d8e9
Revises: e3f4a5b6c7d8
Create Date: 2026-09-04 ...
"""
# --- upgrade ---
op.create_table("task_status", ...)
op.create_table("task", ...)
op.create_index("idx_task_user_status", ...)
op.create_index("idx_task_status_deadline", ...)
op.create_table("task_criterion", ...)
op.create_index("idx_task_criterion_task", ...)
op.create_table("task_receipt_increment", ...)
op.create_index("idx_tri_receipt", ...)
op.create_table("challenge_generation_log", ...)
op.create_index("idx_cgl_user", ...)
op.add_column("discounts", sa.Column("value_type", ..., default="percent"))
op.add_column("discounts", sa.Column("link_task_id", ..., nullable=True))
op.create_check_constraint("ck_discounts_value_type", "discounts", "value_type IN ('percent', 'fixed_rub')")

# --- downgrade ---
op.drop_constraint("ck_discounts_value_type", "discounts")
op.drop_column("discounts", "link_task_id")
op.drop_column("discounts", "value_type")
op.drop_index("idx_cgl_user")
op.drop_table("challenge_generation_log")
op.drop_index("idx_tri_receipt")
op.drop_table("task_receipt_increment")
op.drop_index("idx_task_criterion_task")
op.drop_table("task_criterion")
op.drop_index("idx_task_status_deadline")
op.drop_index("idx_task_user_status")
op.drop_table("task")
op.drop_table("task_status")
```

## Sample rows (для quickstart валидации)

`task_status`:
```sql
INSERT INTO task_status(id, name) VALUES
  (gen_random_uuid(), 'открыто'),
  (gen_random_uuid(), 'выполнено'),
  (gen_random_uuid(), 'провалено'),
  (gen_random_uuid(), 'истекло');
```

`task` (пример после `spend_threshold` для пользователя u_000001 с favorite_item = «Молоко Простоквашино 3.2%»):
```sql
INSERT INTO task(id, loyalty_card_id, task_status_id, criterion_type, criterion_entity_id,
                 quantity_target, quantity_current, title, description, mechanic,
                 reward_rub, reasoning, path, model, reward_type)
VALUES ('...', '<user>', '<open_status>', 'product', '<product_uuid>',
        1, 0,
        'Скидка 15% на Молоко Простоквашино 3.2%',
        'Потрать от 1500 ₽ за один поход в магазин и получи скидку 15% на Молоко Простоквашино 3.2%.',
        'порог трат + скидка на любимый товар',
        45.00,
        '«Молоко Простоквашино 3.2%» — самая часто покупаемая позиция пользователя (14 раз за train-период).',
        'personal', NULL, 'discount');
```

`task_criterion` (для того же task):
```sql
INSERT INTO task_criterion(id, task_id, kind, value_num) VALUES
  (gen_random_uuid(), '<task_id>', 'item_quantity', 1),
  (gen_random_uuid(), '<task_id>', 'spend_threshold_rub', 1500);
```
