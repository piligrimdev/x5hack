# Внутренние контракты — Celery задачи

Три задачи в двух очередях. Все задачи идемпотентны на уровне payload (`receipt_id`, `user_id`) — Celery-ретрай не приводит к побочным эффектам.

## Очереди

| Queue | Concurrency | Задачи | Обоснование |
|---|---|---|---|
| `receipts` | 4 | `process_receipt` | Быстрые операции (SQL). Concurrency 4 = разумный параллелизм по разным пользователям (по-пользовательский lock сериализует одного user'а). |
| `challenges` | 2 | `generate_challenges` | Медленные из-за LLM. Concurrency 2 = не выжигать OpenRouter rate-limit; при 3 пар. вызовах вероятность 429 растёт. |
| `beat` | 1 | `expire_tasks` | Периодическая. |

Broker: Redis (`REDIS_URL` из env). Result backend: Redis (тот же). Serializer: `json`.

Celery global config (`webx5/core/celery_app.py`):
- `task_time_limit=120` (soft), `task_time_hard_limit=180` — защита от зависших LLM.
- `task_acks_late=True` — задача перепрочтётся при падении воркера.
- `worker_prefetch_multiplier=1` — избегаем «жадного» захвата задач воркерами с LLM.

## `webx5.tasks.receipt.process_receipt`

**Signature:** `process_receipt(receipt_id: str) -> dict`

**Trigger:** `receipt_service.create_receipt` в конце — если `is_new=True` и `receipt.loyalty_card_id is not None`.

**Payload:** `{"receipt_id": "<uuid>"}`

**Body:**

```
with db.get_sync_session() as session:
    with session.begin():
        receipt = session.get(Receipt, receipt_id)
        if not receipt or not receipt.loyalty_card_id:
            return {"status": "no_op", "reason": "no receipt or anonymous"}

        user_id = receipt.loyalty_card_id
        # Pessimistic lock (FR-014)
        session.execute(select(User).where(User.id == user_id).with_for_update()).scalar_one()

        active_tasks = task_repo.get_active_for_user(session, user_id)

        # Первый чек условие (R9): нет активных задач → это trigger'ит generate.
        if not active_tasks:
            # Проверить, что уже не запускается generate (idempotency)
            # (проверка через task_receipt_increment невозможна — записей нет).
            # Enqueue из FR-002.
            generate_challenges.apply_async(args=[user_id, 3], queue="challenges")
            return {"status": "first_receipt_generation_enqueued"}

        # Иначе — считать прогресс активных задач.
        completed_ids = []
        for task in active_tasks:
            if task_completion_service.apply_receipt(session, task, receipt):
                # apply_receipt: возвращает True если задание закрыто.
                completed_ids.append(task.id)

        # Enqueue replacements — по одному на каждое закрытое.
        for _ in completed_ids:
            generate_challenges.apply_async(args=[user_id, 1], queue="challenges")

        return {"status": "processed", "progressed_count": len(active_tasks), "completed_count": len(completed_ids)}
```

**Идемпотентность:** повторный запуск с тем же `receipt_id` — `TaskReceiptIncrement` PK гарантирует, что прогресс не удвоится (INSERT конфликтует → в `apply_receipt` early return); enqueue дубликата `generate_challenges` не критичен (сам `generate_challenges` проверяет активные перед вставкой).

**Возможные ошибки:**
- `Receipt not found` — no_op, тихо.
- `User not found` (тоже reachable через FK broken) — no_op.
- LLM/Postgres error — bubble up, Celery ретраит (max_retries=3, exponential backoff).

## `webx5.tasks.generation.generate_challenges`

**Signature:** `generate_challenges(user_id: str, count: int) -> dict`

**Trigger:** enqueue из `process_receipt` (первый чек / replacement) или из `expire_tasks` (после экспирации).

**Payload:** `{"user_id": "<uuid>", "count": 3 | 1}`

**Body:**

```
with db.get_sync_session() as session:
    with session.begin():
        session.execute(select(User).where(User.id == user_id).with_for_update()).scalar_one()

        active = task_repo.get_active_for_user(session, user_id)
        if len(active) >= 3:
            return {"status": "no_op", "reason": "user already has 3 active tasks"}

        active_paths = {t.path for t in active}
        active_types = _paths_to_types(active_paths)  # {'llm', 'spend_threshold', 'category_expansion'}

        # Определить, какие типы генерировать.
        all_types = ["spend_threshold", "category_expansion", "llm"]  # порядок дёшёвое → дорогое (R2)
        available_types = [t for t in all_types if t not in active_types]

        # Сколько создать
        to_generate_types = available_types[:count]

        profile = challenge_adapter.build_profile(session, user_id)  # ORM → dict
        config = load_synth_config()  # синглтон

        created_task_ids = []
        for challenge_type in to_generate_types:
            script_result = synth.challenges.generate_challenge_for_user(
                profile=profile,
                config=config,
                model=env.CHALLENGE_LLM_MODEL,
                api_key=env.OPENROUTER_API_KEY,
                dry_run=False,
                challenge_type=challenge_type,
            )
            # Логируем ВСЕГДА (FR-018), включая no_challenge
            log_id = challenge_log_repo.record(session, user_id, script_result, challenge_type)

            if script_result["path"] == "no_challenge":
                continue  # slot остаётся пустым (FR-022)

            task_id = challenge_adapter.persist_challenge(session, user_id, script_result)
            challenge_log_repo.attach_task(session, log_id, task_id)
            created_task_ids.append(task_id)

        return {"status": "generated", "task_ids": created_task_ids, "requested": count, "created": len(created_task_ids)}
```

**Идемпотентность:** проверка `len(active) >= 3` в начале — повторный запуск не создаст 4-е задание. Если между двумя дублирующими вызовами кто-то что-то создал — второй увидит и вернёт no_op.

**Возможные ошибки:**
- LLM timeout / 500 — скрипт сам возвращает `path='generic_fallback'`, задание всё равно создаётся.
- Postgres error — bubble up, Celery ретраит.

## `webx5.tasks.expiration.expire_tasks`

**Signature:** `expire_tasks() -> dict`

**Trigger:** Celery Beat, каждые 60 сек.

**Payload:** пусто.

**Body:**

```
with db.get_sync_session() as session:
    with session.begin():
        # SKIP LOCKED — если ещё один beat запустился (redundancy), не ждём.
        expired = session.execute(
            select(Task)
              .where(Task.task_status_id == OPEN_STATUS_ID, Task.deadline < func.now())
              .with_for_update(skip_locked=True)
              .limit(100)
        ).scalars().all()

        by_user: dict[UUID, int] = defaultdict(int)
        for task in expired:
            task.task_status_id = EXPIRED_STATUS_ID
            by_user[task.loyalty_card_id] += 1

        # Enqueue replacement generation per user (FR-002)
        for user_id, count in by_user.items():
            generate_challenges.apply_async(args=[str(user_id), count], queue="challenges")

        return {"status": "expired", "count": len(expired), "users": len(by_user)}
```

**Идемпотентность:** SELECT FOR UPDATE + status filter — если другой beat уже провёл экспирацию, задачи уже не имеют статуса 'открыто'.

**Возможные ошибки:**
- Никаких сетевых зависимостей — только Postgres. Beat next tick через 60 сек.

## Общие тестовые ожидания

- `CELERY_TASK_ALWAYS_EAGER=True` в тестах — задачи выполняются in-process при `apply_async`.
- Тестовая база — тот же Postgres, отдельная schema (тест-фикстура через `alembic upgrade head`).
- Тестовый Redis не требуется (`ALWAYS_EAGER` обходит брокер).
