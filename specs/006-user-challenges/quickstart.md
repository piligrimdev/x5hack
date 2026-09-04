# Quickstart — Валидация Персональных Челленджей

End-to-end сценарий, доказывающий работу feature после implementation.

## Prerequisites

- Docker Desktop установлен и запущен.
- В репозитории есть `.env` со значениями:
  ```env
  DATABASE_URL=postgresql+psycopg2://postgres:password@db:5432/x5hack
  REDIS_URL=redis://redis:6379/0
  OPENROUTER_API_KEY=<получить у команды или подставить sk-or-... из синтетики>
  CHALLENGE_LLM_MODEL=anthropic/claude-haiku-4.5
  CHALLENGE_TYPE_DEFAULT=llm
  SYNTH_CONFIG_PATH=/config/synth_schema.yaml
  TERMINAL_TOKEN=<любой>
  JWT_SECRET=<любой>
  ```

## Setup

### 1. Поднять стек (включая redis + worker + beat)

```bash
docker compose up --build -d
```

Ожидаемо: 5 контейнеров запущены — `db`, `redis`, `web` (uvicorn), `worker` (celery worker), `beat` (celery beat).

Проверка:
```bash
docker compose ps
curl http://localhost:8000/health
# → {"status":"ok"}
```

### 2. Применить миграции (автоматически, при старте `web`)

Миграция `f4a5b6c7d8e9_add_task_tables.py` создаёт 5 новых таблиц + расширяет `discounts`.

Проверка:
```bash
docker compose exec db psql -U postgres -d x5hack -c "\dt task*"
# → task, task_status, task_criterion, task_receipt_increment, challenge_generation_log
```

### 3. Сид словаря `task_status`

```bash
docker compose run --rm --entrypoint python web scripts/seed_task_status.py
# → Seeded 4 task statuses: открыто, выполнено, провалено, истекло
```

### 4. Сид каталога и магазинов (существующие скрипты)

```bash
docker compose run --rm --entrypoint python \
  -v "$(pwd)/unique_products.json:/tmp/products_data.json" \
  -e SEED_FILE_PATH=/tmp/products_data.json \
  web scripts/seed_products.py

docker compose exec web python scripts/generate_stores.py
docker compose exec web python scripts/generate_discounts.py
```

## End-to-End сценарий

### Сценарий A — Новый пользователь, первый чек, 3 задания появляются

**Ожидаемый результат по SC-001, SC-005, SC-006, FR-002, FR-005a.**

#### A.1. Регистрация пользователя

```bash
curl -X POST http://localhost:8000/register \
  -H "Content-Type: application/json" \
  -d '{"phone": "+79000000001"}'
# → { "access_token": "eyJ...", "refresh_token": "eyJ..." }
```

Сохрани `access_token` в `ACCESS_TOKEN` для дальнейших запросов.

Получи `user_id` (=`loyalty_card_id`):
```bash
curl http://localhost:8000/me -H "Authorization: Bearer $ACCESS_TOKEN"
# → { "id": "<user_uuid>", "phone": "+79000000001", "loyalty_level": 1, ... }
```

Сохрани в `USER_ID`.

#### A.2. Проверить пустое состояние заданий

```bash
curl http://localhost:8000/challenges/current -H "Authorization: Bearer $ACCESS_TOKEN"
# → { "items": [], "empty_reason": "no_history" }
```

#### A.3. Касса создаёт первый чек

Получи `store_id` (первый доступный):
```bash
STORE_ID=$(curl -s http://localhost:8000/stores | jq -r '.[0].id')
PRODUCT_ID=$(curl -s http://localhost:8000/catalog/products?size=1 | jq -r '.items[0].id')
```

Отправка чека:
```bash
curl -X POST http://localhost:8000/receipts \
  -H "X-Terminal-Token: $TERMINAL_TOKEN" \
  -H "X-Idempotency-Key: $(uuidgen)" \
  -H "Content-Type: application/json" \
  -d "{
    \"loyalty_card_id\": \"$USER_ID\",
    \"store_id\": \"$STORE_ID\",
    \"channel\": \"offline\",
    \"items\": [
      {\"product_id\": \"$PRODUCT_ID\", \"quantity\": 1}
    ]
  }"
# → 201 Created (без ожидания генерации задач — SC-005: ответ < 2 сек)
```

Проверка времени ответа:
```bash
time curl -X POST ... # должен быть < 2 сек
```

#### A.4. Дождаться фоновой генерации (≤ 30 сек, SC-001)

```bash
sleep 15  # LLM call ~5-10 сек + 2 detereministic ~100мс
curl http://localhost:8000/challenges/current -H "Authorization: Bearer $ACCESS_TOKEN"
```

Ожидаемо:
```json
{
  "items": [
    { "id": "...", "title": "...", "mechanic": "порог трат + скидка...", "reward_rub": 45.00, ... },
    { "id": "...", "title": "Попробуйте: 5% на...", "mechanic": "скидка на новую категорию", ... },
    { "id": "...", "title": "<LLM-generated>", "mechanic": "<LLM-generated>", ... }
  ],
  "empty_reason": "none"
}
```

**Валидация:** `len(items) == 3`, все `status == "открыто"`, `deadline` — примерно через 7 суток от `now()`.

#### A.5. Аудит — записи в `challenge_generation_log`

```bash
docker compose exec db psql -U postgres -d x5hack -c "
  SELECT path, challenge_type, model, LEFT(reasoning, 60) as reasoning_preview
  FROM challenge_generation_log
  WHERE user_id = '$USER_ID'
  ORDER BY created_at DESC LIMIT 3;
"
```

Ожидаемо: 3 строки — по одной на каждый challenge_type. У 'personal' — заполнены `prompt`, `response`, `reasoning`, `model`. У detereministic — только `reasoning` из скрипта.

**SC-006 pass:** каждый вызов имеет запись.

### Сценарий B — Прогресс задания и выдача награды

**Ожидаемый результат по SC-002, SC-003, FR-006, FR-007, FR-010, FR-014.**

#### B.1. Найти задание с criterion_type='product'

```bash
TASK_ID=$(docker compose exec -T db psql -U postgres -d x5hack -tAc "
  SELECT t.id FROM task t
  WHERE t.loyalty_card_id = '$USER_ID' AND t.criterion_type = 'product'
  LIMIT 1;
")
TARGET_PRODUCT_ID=$(docker compose exec -T db psql -U postgres -d x5hack -tAc "
  SELECT criterion_entity_id FROM task WHERE id = '$TASK_ID';
")
```

Если такого задания нет (все — category), — можно взять любое из активных и купить любой товар из его категории.

#### B.2. Кассовый чек с этим продуктом

```bash
curl -X POST http://localhost:8000/receipts \
  -H "X-Terminal-Token: $TERMINAL_TOKEN" \
  -H "X-Idempotency-Key: $(uuidgen)" \
  -H "Content-Type: application/json" \
  -d "{
    \"loyalty_card_id\": \"$USER_ID\",
    \"store_id\": \"$STORE_ID\",
    \"items\": [
      {\"product_id\": \"$TARGET_PRODUCT_ID\", \"quantity\": 1}
    ]
  }"
```

#### B.3. Дождаться фоновой обработки (≤ 10 сек)

```bash
sleep 8
```

#### B.4. Проверить статус задания

```bash
docker compose exec db psql -U postgres -d x5hack -c "
  SELECT t.id, ts.name as status, t.quantity_current, t.completed_at, t.reward_id
  FROM task t JOIN task_status ts ON t.task_status_id = ts.id
  WHERE t.id = '$TASK_ID';
"
```

Ожидаемо:
- `status = 'выполнено'`
- `completed_at` — заполнено
- `reward_id` — заполнено (UUID)

#### B.5. Проверить, что награда создана

```bash
docker compose exec db psql -U postgres -d x5hack -c "
  SELECT d.id, d.value, d.value_type, d.valid_to, d.loyalty_card_id, d.link_task_id
  FROM discounts d
  WHERE d.link_task_id = '$TASK_ID';
"
```

Ожидаемо: 1 строка. `value = <reward_rub задания>`, `value_type = 'fixed_rub'`, `loyalty_card_id = $USER_ID`, `valid_to ≈ now() + 7 days`.

**SC-003 pass:** награда есть, задание выполнено — атомарно.

#### B.6. Замена: должно появиться новое задание

```bash
sleep 12  # replacement generation
curl http://localhost:8000/challenges/current -H "Authorization: Bearer $ACCESS_TOKEN"
# → 3 задания (одно новое взамен закрытого)
```

### Сценарий C — Истечение задания и автозамена

**Ожидаемый результат по SC-004, FR-004.**

#### C.1. Искусственно проставить прошедший deadline

```bash
OTHER_TASK_ID=$(docker compose exec -T db psql -U postgres -d x5hack -tAc "
  SELECT t.id FROM task t
  JOIN task_status ts ON t.task_status_id = ts.id
  WHERE t.loyalty_card_id = '$USER_ID' AND ts.name = 'открыто'
  LIMIT 1;
")

docker compose exec db psql -U postgres -d x5hack -c "
  UPDATE task SET deadline = now() - interval '1 hour' WHERE id = '$OTHER_TASK_ID';
"
```

#### C.2. Дождаться Beat sweep (≤ 60 сек + генерация ≤ 30 сек)

```bash
sleep 90
```

#### C.3. Проверить экспирацию

```bash
docker compose exec db psql -U postgres -d x5hack -c "
  SELECT ts.name FROM task t JOIN task_status ts ON t.task_status_id = ts.id
  WHERE t.id = '$OTHER_TASK_ID';
"
# → 'истекло'
```

#### C.4. Проверить замену

```bash
curl http://localhost:8000/challenges/current -H "Authorization: Bearer $ACCESS_TOKEN"
# → 3 задания (замена сгенерирована)
```

**SC-004 pass:** задание переведено в истекло + новое создано за < 5 мин.

### Сценарий D — Saturated пользователь

**Ожидаемый результат по FR-022, edge case.**

Труднее воспроизвести end-to-end (требует ≥85 чеков) — тестируется unit-тестом мокая `compute_frequency_saturation`. В quickstart проверим только API-контракт:

Создать искусственно (SQL): удалить все активные задания пользователя + вызвать `generate_challenges` вручную с фиксированным dry_run, где мокнут `no_challenge`.

```bash
# Программно через тест — не удобно из quickstart. Проверить UI-контракт:
# ожидаем { "items": [], "empty_reason": "saturated" } для saturated
```

## Success Criteria — трассировка

| SC | Сценарий | Как проверяется |
|---|---|---|
| SC-001 (3 задания за 30 сек) | A.4 | timer после A.3, GET показывает 3 задания |
| SC-002 (100% квалифицирующих позиций инкрементят) | B.4 | manual + tests/tasks/test_process_receipt.py::test_matching_line_increments |
| SC-003 (атомарность reward + completion) | B.5 | JOIN task ↔ discounts, нет висящих выполненных без reward |
| SC-004 (истечение ≤ 5 мин) | C.3-C.4 | timer после C.1 |
| SC-005 (POST /receipts ≤ 2 сек) | A.3 | `time curl` |
| SC-006 (100% вызовов залогированы) | A.5 | SELECT count(*) FROM challenge_generation_log |
| SC-007 (GET /challenges/current ≤ 500 мс) | A.4 | `time curl` |
| SC-008 (0/3 инвариант) | все сценарии | `SELECT count(*) ... WHERE status='открыто'` = 3 |
| SC-009 (LLM hit rate ≥70%) | оффлайн | `python -m synth.cli reference --count 40 --seed 42; python -m synth.challenges score-against-key ...` |

## Troubleshooting

- **`GET /challenges/current` возвращает пусто через минуту после первого чека** → проверь `docker compose logs worker`; вероятно, `OPENROUTER_API_KEY` не выставлен, `challenge_type=llm` упал, но `spend_threshold`/`category_expansion` тоже должны создать задания. Если не создались — смотри `challenge_generation_log`.
- **Все 3 задания одинаковые (нарушение FR-005)** → баг в `generation.py::_paths_to_types` mapping.
- **Reward не создан после completion** → проверь `discounts` insert log в `worker`; вероятно, миграция `discounts.value_type` не применена.
- **Дедупликация не работает — 2 инкремента на один чек** → проверь, что `UNIQUE(task_id, receipt_id)` на `task_receipt_increment` создан миграцией.
