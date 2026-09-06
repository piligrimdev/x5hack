# Research: Составные задания, типы наград и вайб

## R1 — Auth: POS/кассовый аппарат

**Decision**: Переиспользовать существующий `TerminalTokenDep` (`X-Terminal-Token` header vs env `TERMINAL_TOKEN`).

**Rationale**: Уже реализован в `web/src/webx5/dependencies/auth.py:30`. Используется на `POST /receipts` и `POST /receipts/calculate`. Vibe CRUD подключается к тому же Depends.

**Alternatives considered**: отдельный JWT-секрет для POS — избыточно для PoC.

---

## R2 — Составные задания: новая таблица vs repurpose TaskCriterion

**Decision**: Новая таблица `task_item`; существующая `task_criterion` не трогается.

**Rationale**: `task_criterion` хранит метаданные одного критерия (`kind`/`value_num`/`value_text` — например, `spend_threshold_rub`). Её схема и семантика не совместимы с понятием «независимый пункт с собственным quantity_current». Новая таблица избегает breaking change и конфликта семантики.

**Alternatives considered**: расширить `task_criterion` — потребовало бы добавления `criterion_type`, `criterion_entity_id`, `quantity_current` и логики разграничения «метадата» vs «субкритерий».

---

## R3 — Прогресс по task_item: per-item quantity_current

**Decision**: `task_item.quantity_current` обновляется непосредственно при обработке чека. `Task.quantity_current` сохраняется как агрегат (сумма заполненности пунктов) для обратной совместимости с клиентами.

**Rationale**: Прогресс по каждому пункту должен быть возвращаем через API независимо (FR-004). Агрегат на Task нужен коду, который смотрит только на Task-уровень (синтетика, история).

**Migration**: Для каждого существующего Task → создать 1 `task_item` с теми же полями; `task_item.quantity_current` = `task.quantity_current`.

---

## R4 — Параллельный зачёт пунктов задания

**Decision**: При обработке чека каждый `task_item` проверяется независимо. Один купленный товар может засчитаться в несколько пунктов одновременно (нет конкуренции между пунктами).

**Rationale**: Уточнено в /speckit-clarify (Q5, ответ A). Упрощает код: нет need в ordering и priority logic.

---

## R5 — Награда-подарок: отдельная таблица `gift_reward`

**Decision**: Новая таблица `gift_reward` (id, task_id, loyalty_card_id, criterion_type, criterion_entity_id, quantity, status, valid_to).

**Rationale**: Подарок — это независимый объект, живущий после выполнения задания и применяемый при расчёте чека/корзины. Его нельзя хранить только в Task, потому что после выполнения Task может попасть в историю; reward должен оставаться активным до применения или истечения.

**Alternatives considered**: Расширить существующую таблицу `discount` — её схема ориентирована на скидки с `value_type`/`value`; gift — это «бесплатный товар», не процентная/рублёвая скидка. Отдельная таблица даёт типобезопасность.

---

## R6 — Применение подарка: скидка на существующую позицию

**Decision**: При расчёте корзины и при создании чека система ищет `gift_reward` со status='active' для пользователя. Если в корзине/чеке есть подходящий товар — у него `paid_price` = 0 (одна единица). Если reward привязан к категории — выбирается самый дешёвый matching товар.

**Rationale**: Уточнено в /speckit-clarify (Q2, ответ B; Q4, ответ A). Товар должен быть добавлен пользователем самостоятельно — система не добавляет позиции.

**Implementation touch points**:
- `DiscountCalculatorService.calculate()` — уже применяет скидки к строкам; gift_reward встраивается сюда как дополнительный источник скидок.
- `ReceiptService` — после создания чека помечает использованные gift_reward как 'used'.

---

## R7 — Vibe: новая таблица `vibe_type`, FK на users

**Decision**: Новая таблица `vibe_type` (id, name unique, description, llm_context, created_at, updated_at). `users` получает `vibe_type_id` (FK nullable, SET NULL on delete).

**Rationale**: Хранить вайб как строку-имя в users больше нельзя — нужно хранить description и llm_context. SET NULL при удалении VibeType автоматически реализует FR-017 (сброс у пользователей).

**Migration**:
1. CREATE `vibe_type` + seed из `VIBE_CATEGORIES` (`synth/challenges.py:101`)
2. ADD `users.vibe_type_id` FK
3. UPDATE users SET vibe_type_id = (SELECT id FROM vibe_type WHERE name = users.vibe_category)
4. DROP `users.vibe_category`, `users.vibe_month`

---

## R8 — ChallengeAdapter: замена pick_vibe_category

**Decision**: `_resolve_vibe_category()` в `ChallengeAdapter` заменяется прямым чтением `user.vibe_type` → `VibeType.llm_context`. Если `vibe_type_id` is NULL — вайб не передаётся в промпт, обычная персонализация.

**Rationale**: FR-018 (без вайба — обычная персонализация). `pick_vibe_category` в `synth/challenges.py` остаётся для тестов и seed-скриптов, но не вызывается в production flow.

---

## R9 — Task.reward_type: расширение CHECK constraint

**Decision**: CHECK constraint на `Task.reward_type` расширяется до `IN ('discount', 'cashback', 'gift')`. Alembic-миграция.

**Rationale**: Текущий constraint `IN ('discount')` блокирует новые типы. `'cashback'` фактически уже используется через points, но в constraint его нет — это техдолг, который попутно закрывается.

---

## R10 — task_item: отдельный label для отображения

**Decision**: `task_item` содержит поле `label` (str nullable). Заполняется при создании составного задания (например, «Куриное филе», «Яйца»).

**Rationale**: API должен возвращать прогресс по каждому пункту с понятным названием (FR-004). Без label клиент не знает, что означает пункт с criterion_entity_id=UUID.
