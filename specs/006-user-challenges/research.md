# Phase 0 Research — Персональные челленджи

Resolutions по всем deferred-пунктам из `plan.md` Phase 0 (R1–R11).

---

## R1. Правило конвертации `reward_rub` → `discounts.value`

**Decision:** Расширить `discounts` полем `value_type ∈ {'percent', 'fixed_rub'}` (миграция + обновление `discount_calculator.py`). Награды за задания создаются с `value_type='fixed_rub', value=reward_rub`. Персональные скидки остаются на существующем механизме best-price-wins.

**Rationale:**
- Скрипт возвращает награду в рублях (`reward_rub`), не в процентах. Обратная конвертация «руб → процент от известной цены» требует хардкода product-price mapping (для generic-пула — вообще недоступно).
- `value_type='fixed_rub'` уже помечен в `BACKLOG.md` как ожидаемое расширение схемы («Уценка как фиксированная сумма — value_type на скидке (percent / fixed_rub) для корректного моделирования уценки»). Мы просто активируем backlog-пункт раньше.
- Изменения в `discount_calculator.py` — 1 функция: `apply_discount(base_price, discount)` — сейчас всегда считает процент, добавить ветку `if discount.value_type == 'fixed_rub': paid = max(0, base - value) else: paid = base * (1 - value/100)`. Оценка ~15 LOC.
- ORM Discount получает новое поле, Pydantic-схемы кассы (`DiscountResponse`) — тоже. Cascading, но локально.

**Alternatives considered:**
- Хранить reward на самом Task (только `reward_rub`), не создавать Discount — теряется автоматическое применение на кассе; пользователю пришлось бы вручную вводить код купона.
- Конвертация в процент от цены — хрупко для generic-пула, где нет привязки к конкретному продукту.

**Implementation notes:**
- Миграция: `ALTER TABLE discounts ADD COLUMN value_type VARCHAR NOT NULL DEFAULT 'percent'`. Старые записи автоматически получают `'percent'` (совместимо с текущей логикой).
- В `DiscountService.calculate` (см. `services/discount_calculator.py:apply_discount`) — ветка по value_type.
- Reward Discount создаётся с: `discount_type_id = <persistent id для 'персональная'>, value=reward_rub, value_type='fixed_rub', link_type=criterion_type, entity_id=criterion_entity_id, scope='all', valid_from=now, valid_to=now + N days (см. R3), loyalty_card_id=user_id`.

---

## R2. Sequential vs parallel запуск 3 генераций в батче

**Decision:** Sequential в порядке дёшёвое → дорогое: `spend_threshold` → `category_expansion` → `llm`. Всё в одной Celery-задаче `generate_challenges(user_id, count=3)`.

**Rationale:**
- Latency budget SC-001 = 30 сек. Реальная стоимость: `spend_threshold` ≈ 50 мс (SQL + арифметика), `category_expansion` ≈ 50 мс, `llm` ≈ 2–10 сек. Итого ≤ 10.1 сек — с запасом.
- «Дёшёвое сначала»: если LLM-вызов упадёт по таймауту, у пользователя уже создано 2 из 3 задания (детерминированные пути завершились); LLM-slot заполняется generic fallback (уже реализовано в `synth/challenges.py`).
- Параллелизация через 3 Celery-задачи усложнит orchestration: FR-005 требует «не создавать 3 задания с одинаковым criterion_entity_id» — при параллельном запуске нужен явный lock или post-hoc dedupe.
- Одна задача = один pessimistic user-lock = проще для FR-014.

**Alternatives considered:**
- 3 параллельные `.apply_async` — усложнение orchestration ради ~5 сек экономии.
- Модификация `synth/challenges.py` для батч-режима — запрещено правилом «скрипт не трогаем».

**Implementation notes:**
- `generate_challenges(user_id, count=3)`:
  1. Lock user.
  2. Прочитать активные task-типы для пользователя (по mechanic или свежему полю `path`).
  3. Определить missing_types = {'llm', 'spend_threshold', 'category_expansion'} - active_types (для полного батча — все три).
  4. Для каждого missing_type в порядке [spend_threshold, category_expansion, llm]: вызвать `synth.challenges.generate_challenge_for_user(profile, config, model, challenge_type=t)`, смаппить, вставить.
  5. Commit lock.

---

## R3. TTL `discounts.valid_to` для reward

**Decision:** `valid_to = completed_at + 7 days`. Симметрично сроку самого задания (7 дней на выполнение), у пользователя ещё 7 дней на использование награды.

**Rationale:**
- Симметрия — легко объяснить пользователю: «неделя на выполнение → неделя на использование».
- Не слишком короткий (1 день = может не успеть в магазин), не слишком долгий (30 дней = скидочный «хвост» тянется).
- Совпадает с ритмом покупок: в среднем 10 покупок/месяц ≈ 2–3 покупки в неделю — вероятность попасть на награду высокая.

**Alternatives considered:**
- `valid_to = task.deadline` — жёстче, но если пользователь выполнил задание в последний день deadline, награда истекает сразу же. Плохой UX.
- `valid_to = completed_at + 30 days` — расточительно для юнит-экономики (принцип IV).

---

## R4. Реализация locking через SQLAlchemy 2.x

**Decision:** Использовать `session.execute(select(User).where(User.id == user_id).with_for_update()).scalar_one()` внутри `with session.begin():` контекста.

**Rationale:**
- SQLAlchemy 2.x поддерживает `with_for_update()` на `select()` — генерирует `SELECT ... FOR UPDATE`.
- `session.begin()` явно открывает транзакцию — необходимо, потому что `sessionmaker(autocommit=False, autoflush=False)` в `webx5/database/database.py` уже настроен так, но каждая операция без `begin_nested` может уйти в отдельный транзакционный блок.
- Postgres освобождает row-lock при `COMMIT`/`ROLLBACK`. Nested-транзакции (savepoints) не нужны.

**Pattern (для документации разработчика):**

```python
from sqlalchemy import select
from webx5.entities.user import User

def process_receipt(receipt_id: str):
    with db.get_sync_session() as session:
        with session.begin():
            user = session.execute(
                select(User).where(User.id == user_id).with_for_update()
            ).scalar_one()
            # ... increment tasks, mark completed, insert task_receipt_increment
            # commit at end of `with session.begin()`
```

**Alternatives considered:**
- `pg_advisory_xact_lock(hash(user_id))` — работает без row-lock, но не отражается в pg_locks с понятным именем таблицы; хуже для отладки.
- Redis distributed lock — лишний failure mode; и так есть Redis для брокера, но добавляет вероятность потери lock при race conditions между Redis restart и Postgres.

---

## R5. Размещение `synth/` в web-образе

**Decision:** Path-dependency в Poetry: `synth = { path = "../synth", develop = false }` в `web/pyproject.toml`. Volume-монтирование `config/`:

```yaml
# docker-compose.yml (web + worker + beat)
volumes:
  - ./config:/config:ro
environment:
  SYNTH_CONFIG_PATH: /config/synth_schema.yaml
```

**Rationale:**
- Poetry path-dep стандартный подход для монорепо; `synth/` — уже полноценный package с `__init__.py`, `pyproject.toml` в его директории — не обязателен (Poetry поддерживает directory-installs без setup.py начиная с 1.2, но для чистоты добавим минимальный `synth/pyproject.toml`).
- Copy vs volume: config не меняется во время работы, но при разработке удобно менять без rebuild.
- Web/worker/beat используют один и тот же образ и один и тот же volume — единый source of truth.

**Alternatives considered:**
- `PYTHONPATH` через ENV: работает, но обходит зависимости `synth` (requests, pyyaml). Poetry их подцепит через `synth/pyproject.toml`.
- Publish `synth` as wheel: overhead для хакатона.

**Implementation notes:**
- Создать минимальный `synth/pyproject.toml`:
  ```toml
  [tool.poetry]
  name = "synth"
  version = "0.1.0"
  description = "Synthetic data + challenge generator"
  packages = [{include = "synth"}]

  [tool.poetry.dependencies]
  python = ">=3.11"
  pyyaml = ">=6.0"
  requests = ">=2.32"
  ```
- В `web/pyproject.toml` добавить `synth = { path = "../synth", develop = false }`.
- В `web/Dockerfile` `COPY ../synth /tmp/synth && cd /tmp/synth && ...` — либо build context на репо-корень (не web/) и `COPY synth ./synth`.

---

## R6. Периодичность Celery Beat expiration sweep

**Decision:** Каждые 60 секунд. Индекс `task(status_id, deadline)`.

**Rationale:**
- FR-004 требует ≤ 5 мин задержки. 60 сек = 5× запас.
- 60 scan/час × ~10 мс/scan (индексированная выборка) = 600 мс/час нагрузки на БД. Незначимо.
- 60 сек — стандартная гранулярность Celery Beat, легко debug'ить в логах.

**Beat schedule (`webx5/core/celery_app.py`):**
```python
beat_schedule = {
    "expire-tasks-every-minute": {
        "task": "webx5.tasks.expiration.expire_tasks",
        "schedule": 60.0,
    },
}
```

**Alternatives considered:**
- 5 минут — на грани SC-004.
- Динамическое расписание по next-deadline — сложнее, выигрыш минимальный.

---

## R7. LLM call timeout в фоновой задаче

**Decision:**
- Скрипт вызывается с параметрами `timeout=30, max_retries=2` (переопределение defaults). Worst-case = 30 + 30 = 60 сек. НЕ модификация скрипта — параметры уже принимаются функцией `call_openrouter`.
- Celery task_time_limit для очереди `challenges` = 120 сек. Задача убивается на 2-й минуте.

**Rationale:**
- Default в скрипте (60 сек × 3 попытки = 180 сек worst-case) слишком долго — SC-001 = 30 сек, а мы должны иметь 3 задания за это время.
- Аварийный fallback: скрипт сам ловит exception и возвращает generic_fallback — то есть даже timeout не убивает задание.
- task_time_limit защищает от «зависших» воркеров.

**Alternatives considered:**
- Использовать defaults — не укладываемся в SC-001.

---

## R8. Хранение `forbidden_categories`

**Decision:** Читать `config/synth_schema.yaml` один раз при startup FastAPI/worker через `synth.config.load_config(path)`, кэшировать список в модуле `webx5/utils/forbidden_categories.py` как `frozenset[str]`. Единый source of truth со скриптом.

**Rationale:**
- Дублирование в env переменных — риск рассинхрона.
- `synth.config.load_config` уже парсит нужный yaml.
- Startup-время → уже загружен к моменту первого запроса.

**Implementation notes:**
- В `webx5/main.py` или `core/challenges.py` при инициализации: `FORBIDDEN_CATEGORIES: frozenset[str] = frozenset(load_config(SYNTH_CONFIG_PATH).forbidden_categories)`.
- Используется в `services/task_completion.py::_line_matches_criterion(line, criterion)` — early return False если категория товара в FORBIDDEN.

---

## R9. Определение «первого чека» пользователя

**Decision:** «Первый чек триггерит генерацию 3 заданий» = «в момент обработки чека у пользователя 0 активных задач И пользователь не в состоянии saturated». Условие проверяется через `TaskRepository.count_active_for_user(user_id) == 0`.

**Rationale:**
- Обобщённое условие: работает как для новых пользователей (нет истории → это буквально первый чек), так и для seeded-пользователей (есть история, но задач нет → генерируем на первом же новом чеке).
- Проверка `saturated` внутри `generate_challenges` — вызов скрипта покажет `path='no_challenge'`, задание не создаётся (FR-022).

**Alternatives considered:**
- Считать `Receipt.count` = 1 — сложнее для seeded users; создаёт race с существующими данными.

---

## R10. Product lookup по имени

**Decision:** В адаптере `services/challenge_adapter.py::_lookup_product`:

```python
def _lookup_product(session, item_name: str, category_id: uuid.UUID) -> Product | None:
    return session.execute(
        select(Product)
        .where(Product.category_id == category_id, Product.name.ilike(f'%{item_name}%'))
        .order_by(func.char_length(Product.name).asc())  # предпочесть более короткие имена
        .limit(1)
    ).scalar_one_or_none()
```

**Rationale:**
- `synth`-словарь категорий содержит короткие имена («молоко»), а `products.name` содержит SKU («Молоко Простоквашино 3.2% 1л»). Substring match через `ILIKE '%молоко%'`.
- Ordering по длине имени — предпочтёт «Молоко» перед «Молочный коктейль Milkis».
- Fallback: если None — criterion_type=category (FR-021).

**Alternatives considered:**
- pg_trgm + gin index — избыточно для PoC.
- Точное matching — не работает из-за SKU-формата.

---

## R11. Расширение JSON-схемы LLM другим разработчиком

**Decision:** Contract с другим разработчиком:
1. В `services/challenge_adapter.py` есть explicit map:
   ```python
   SCRIPT_FIELD_TO_CRITERION_KIND: dict[str, str] = {
       'spend_threshold_rub': 'spend_threshold_rub',
       # <здесь коллега добавит новую строку, когда расширит LLM-схему>
   }
   ```
2. Адаптер для каждого ключа map'а проверяет `if key in script_result:` и пишет `TaskCriterion(kind=SCRIPT_FIELD_TO_CRITERION_KIND[key], value_num=...)`.
3. Completion-checker `services/task_completion.py::CHECKERS_BY_KIND` — параллельный map функций. Если новый kind добавлен в SCRIPT_FIELD_TO_CRITERION_KIND, но не в CHECKERS_BY_KIND → задание не может быть закрыто (FR-024 защита).

**Rationale:**
- Расширение = 2 строки кода (map + checker), без миграции.
- Защита FR-024 предотвращает «выдать награду по неполной проверке».
- Explicit map лучше, чем dynamic reflection — код очевидно читается.

**Implementation notes:**
- Задокументировать contract в `CONTRIBUTING` или README modernization ветки — коллега знает, куда смотреть.
- Log warning при startup если в SCRIPT_FIELD_TO_CRITERION_KIND есть kind, отсутствующий в CHECKERS_BY_KIND.

---

## Все NEEDS CLARIFICATION resolved

Phase 0 закрывает все deferred-решения. Phase 1 (data-model, contracts, quickstart) можно писать без блокеров.
