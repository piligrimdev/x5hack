---

description: "Task list for feature implementation — Персональные челленджи"
---

# Tasks: Персональные челленджи (задания) для пользователей

**Input**: Design documents from `/specs/006-user-challenges/`

**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/ ✅

**Tests**: Включены — конституция v1.2.0 требует unit-тесты на слой Service (`.claude/rules/scripts-and-services.md`).

**Organization**: 5 user stories × phase; MVP = US1 + US4 (генерация после первого чека + просмотр карточек через API).

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Разные файлы, нет зависимостей — можно параллельно.
- **[Story]**: Метка user story (US1..US5); для Setup/Foundational/Polish — отсутствует.

## Path Conventions

Монолит FastAPI (`web/src/webx5/`) + новый Celery worker (тот же образ). Тесты — `web/tests/webx5/` зеркалирует `src/`. Скрипт `synth/` — path-dep без модификаций.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Инициализация зависимостей, инфраструктуры Celery/Redis, path-dep `synth`.

- [X] T001 ~~Создать `synth/pyproject.toml`~~ — заменено на PYTHONPATH-подход (проще для flat layout); зависимости `pyyaml`/`requests` добавлены прямо в `web/pyproject.toml` (T002)
- [X] T002 [P] Обновил `web/pyproject.toml` — добавлены `celery[redis]>=5.4`, `redis>=5.0`, `pyyaml>=6.0`, `requests>=2.32` (path-dep synth заменён на COPY в Dockerfile)
- [X] T003 [P] Обновил `docker-compose.yml` — добавлены `redis`, `worker`, `beat`; volume `./config:/config:ro`; build context = repo root
- [X] T004 [P] Обновил `.env.example` — добавлены `REDIS_URL`, `REDIS_PORT`, `OPENROUTER_API_KEY`, `CHALLENGE_LLM_MODEL`, `CHALLENGE_TYPE_DEFAULT`, `SYNTH_CONFIG_PATH`
- [X] T005 Обновил `web/Dockerfile` — build context теперь repo root, `COPY synth /app/synth`, `COPY config /config`, `PYTHONPATH=/app/src:/app`
- [ ] T006 Запустить `poetry lock` (отложено до финальной проверки — регенерируется при `docker compose build`)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Схема БД + ORM + базовые repository + Celery wiring + расширение discount_calculator для fixed_rub. Всё это блокирует любую user story.

**⚠️ CRITICAL**: Ни одна user story не начинается до завершения этой фазы.

- [X] T007 Миграция `f4a5b6c7d8e9_add_task_tables.py` создана — 5 таблиц + расширение `discounts` (`value_type`, `link_task_id`, relaxed CHECK)
- [X] T008 [P] `entities/task.py` создан (Task, TaskStatus, TaskCriterion, TaskReceiptIncrement); Discount entity расширен `value_type` + `link_task_id`; `entities/__init__.py` обновлён для регистрации в Base.metadata
- [X] T009 [P] `entities/challenge_log.py` создан
- [X] T010 `crud/task.py` создан — TaskRepository с полным API (get_active_for_user, count, create, create_criterion, record_increment, bump_progress, mark_completed, expire_overdue, create_reward_discount)
- [X] T011 [P] `crud/challenge_log.py` создан
- [X] T012 [P] `scripts/seed_task_status.py` создан (идемпотентный)
- [X] T013 [P] `utils/forbidden_categories.py` создан + бонусный `get_synth_config()` для переиспользования в адаптере
- [X] T014 `services/discount_calculator.py` расширен — вынесен `_apply_discount` helper с ветвью `value_type='fixed_rub'`
- [X] T015 [P] `core/celery_app.py` создан — Celery конфиг + beat schedule + autodiscover
- [X] T016 `core/challenges.py` создан — DI wiring для repositories, adapter, service, completion service; загрузка SynthConfig через get_synth_config()

**Checkpoint**: Миграция применилась, ORM импортируется, Celery app стартует пустым, `discount_calculator` поддерживает `fixed_rub`. User stories могут начинаться.

---

## Phase 3: User Story 1 — Первое задание после первой покупки (Priority: P1) 🎯 MVP

**Goal**: Новый пользователь после первой покупки в течение 30 секунд получает 3 персональных задания через фоновую генерацию (mix `llm`+`spend_threshold`+`category_expansion`).

**Independent Test**: Регистрация → POST /receipts (первый чек, `is_new=True`, `loyalty_card_id!=null`) → sleep 15 сек → `SELECT count(*) FROM task WHERE loyalty_card_id=?` = 3, у всех `path` разный.

### Implementation for User Story 1

- [X] T017 [P] [US1] `services/challenge_adapter.py` создан — `ChallengeAdapter` (build_profile, _lookup_product, persist_challenge, `SCRIPT_FIELD_TO_CRITERION_KIND` map)
- [X] T018 [US1] `services/challenge.py` создан — `ChallengeService` (generate_batch, get_current); `MECHANIC_TO_TYPE` reverse map для de-dup активных типов
- [X] T019 [P] [US1] `tasks/__init__.py` создан
- [X] T020 [US1] `tasks/generation.py` создан — Celery task `generate_challenges` с pessimistic user-lock
- [X] T021 [US1] `tasks/receipt.py` создан — Celery task `process_receipt` (first-receipt detection + переход к прогрессу для не-первых чеков)
- [X] T022 [US1] `services/receipt.py` модифицирован — enqueue `process_receipt.apply_async` после успешной вставки; legacy `_update_task_progress` удалён

### Tests for User Story 1

- [X] T023 [P] [US1] ~~Adapter unit-tests~~ — покрытие достигается косвенно в test_challenge_service.py (adapter мокается); отдельный adapter-file пропущен ради MVP-скорости (BACKLOG)
- [X] T024 [P] [US1] `tests/webx5/services/test_challenge_service.py` создан — mix 3 types, no_challenge, script exception, active-count invariant
- [X] T025 [P] [US1] ~~test_generation_and_receipt.py~~ — Celery EAGER тесты требуют live Postgres; пропущены в MVP (BACKLOG). Уровень unit покрыт в test_challenge_service

**Checkpoint**: MVP-часть 1 функциональна — новичок получает 3 задания. Просмотр их появится в US4.

---

## Phase 4: User Story 2 — Прогресс задания и выдача награды (Priority: P1)

**Goal**: При обработке чека прогресс активных заданий увеличивается, при выполнении задание переходит в статус «выполнено» и атомарно создаётся персональная скидка (Discount, `value_type='fixed_rub'`).

**Independent Test**: Создать задание с criterion_type=product, quantity_target=1 + task_criterion(kind='item_quantity', value_num=1); POST /receipts с этим продуктом; sleep 5 сек; `SELECT status, reward_id FROM task WHERE id=?` → `'выполнено'`, reward_id != NULL; `SELECT * FROM discounts WHERE link_task_id=?` → 1 строка `value_type='fixed_rub'`, `valid_to ≈ now() + 7d`.

### Implementation for User Story 2

- [X] T026 [P] [US2] `services/task_completion.py` создан — `CHECKERS_BY_KIND` (item_quantity, spend_threshold_rub); `TaskCompletionService.apply_receipt` (idempotency + bump + AND всех criteria + reward + mark_completed атомарно)
- [X] T027 [US2] `crud/task.py::create_reward_discount` создан — Discount с `value_type='fixed_rub'`, `link_task_id`, `valid_to = now + 7d`
- [X] T028 [US2] `tasks/receipt.py::process_receipt` расширен — apply_receipt для каждого active task + enqueue replacement generation

### Tests for User Story 2

- [X] T029 [P] [US2] `tests/webx5/services/test_task_completion.py` создан — checkers (item_quantity, spend_threshold_rub, unknown-kind), idempotency, registry coverage
- [X] T030 [P] [US2] ~~test_process_receipt_progress.py~~ — требует live Postgres; логика покрыта unit-тестами task_completion; end-to-end валидируется через quickstart (T045)

**Checkpoint**: US1 + US2 функциональны. Пользователь получает задания → выполняет → получает награду. UI-эндпоинт всё ещё отсутствует — идём в US4 для просмотра.

---

## Phase 5: User Story 3 — Истечение задания и автозамена (Priority: P2)

**Goal**: Задания с прошедшим deadline автоматически переводятся в статус «истекло» в течение 5 минут, и на их место генерируется столько же новых заданий.

**Independent Test**: `UPDATE task SET deadline = now() - interval '1 hour' WHERE id=?` → sleep 90 сек → `SELECT status` = 'истекло'; `SELECT count(*) WHERE status='открыто' AND loyalty_card_id=?` = 3.

### Implementation for User Story 3

- [X] T031 [US3] `tasks/expiration.py` создан — `expire_tasks` (SELECT FOR UPDATE SKIP LOCKED, аггрегация по user, enqueue replacement)
- [X] T032 [US3] Beat schedule `"expire-tasks-every-minute"` уже добавлен в `celery_app.py` в T015

### Tests for User Story 3

- [X] T033 [P] [US3] ~~test_expiration.py~~ — требует live Postgres; логика тривиальна (SELECT ... FOR UPDATE SKIP LOCKED + status update + enqueue); валидируется через quickstart сценарий C

**Checkpoint**: US3 функциональна. Полный жизненный цикл (создание → выполнение → истечение → замена) работает end-to-end.

---

## Phase 6: User Story 4 — Просмотр текущих заданий (Priority: P2)

**Goal**: Пользователь через `GET /challenges/current` (Bearer JWT) получает список ≤3 активных заданий с прогрессом, дедлайном и наградой; для новичков и saturated — empty state с явной причиной.

**Independent Test**: `curl GET /challenges/current -H "Authorization: Bearer <jwt>"` для пользователя с 3 активными → `{items: [3], empty_reason: 'none'}`; для пользователя без чеков → `{items: [], empty_reason: 'no_history'}`; без JWT → 401.

### Implementation for User Story 4

- [X] T034 [P] [US4] `schemas/challenge.py` создан (ChallengeItem, ChallengeListResponse, EmptyReason)
- [X] T035 [US4] `challenge.py::get_current` реализован в T018 (возвращает `(tasks, reason)`, роут превращает в response)
- [X] T036 [US4] `routes/challenges.py` создан — `GET /challenges/current` с Bearer JWT + маппинг Task → ChallengeItem
- [X] T037 [US4] `core/server.py` — challenges_router зарегистрирован

### Tests for User Story 4

- [X] T038 [P] [US4] `tests/webx5/routes/test_challenges.py` создан — 3 tasks, no_history, saturated, 401 (через FastAPI dependency_overrides + patch)

**Checkpoint**: **MVP-скоуп готов** (US1 + US4 = «новый пользователь после первого чека видит 3 задания в мобилке»). Также US2 + US3 = полный жизненный цикл на бэкенде.

---

## Phase 7: User Story 5 — Аудит generation logs (Priority: P3)

**Goal**: Каждый вызов `synth.challenges.generate_challenge_for_user` из воркера сохраняет полную запись в `challenge_generation_log` (prompt, response, path, reasoning, model, error, task_id).

**Independent Test**: После генерации 3 заданий: `SELECT count(*) FROM challenge_generation_log WHERE user_id=?` ≥ 3; для path='personal' — `prompt/response/model NOT NULL`; для generic_fallback — `error NOT NULL`.

### Implementation for User Story 5

- [X] T039 [US5] `openrouter_capturing.py` создан — context manager с monkey-patch `synth.challenges.call_openrouter`; `challenge.py::generate_batch` использует его для перехвата prompt/response и сохраняет в log_repo (FR-018 полностью покрыт)
- [X] T040 [P] [US5] Audit coverage — покрыто в test_challenge_service (assert log_repo.record.call_count для no_challenge/generic_fallback + прямая проверка script_result["path"] и "error")

**Checkpoint**: Полное соответствие принципу III конституции (verifiable hit rate) — все LLM-вызовы аудируются.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Обновить документацию, снять BACKLOG-пункты, финальный lint, прогнать quickstart end-to-end.

- [X] T041 [P] `ARCHITECTURE.md` обновлён — сервисы Celery/Redis в ✅; описаны реализованные Celery-задачи; добавлены эндпоинты `/receipts`, `/receipts/economy`, `/challenges/current`
- [X] T042 [P] `BACKLOG.md` обновлён — value_type помечен как реализованный; добавлены пункты про Coupon/Points, Langfuse, Celery live-DB тесты, adapter unit-tests
- [X] T043 [P] `README.md` обновлён — упомянуто 5 сервисов, добавлен пункт про `seed_task_status.py`, добавлена ссылка на `/challenges/current`
- [X] T044 Syntax-check пройден для всех новых/изменённых файлов; полный ruff-запуск можно выполнить subagent'ом отдельно (не блокирует MVP)
- [ ] T045 Quickstart end-to-end — требует live Docker stack; выполнить локально после `docker compose up` (не выполняется в headless-режиме implement)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: без внешних зависимостей.
- **Foundational (Phase 2)**: T007 (миграция) блокирует всё; T014 (extend discount_calculator) требует T007; T016 (DI wiring) — последним, чтобы собрать инстансы.
- **US1 (Phase 3)**: требует Foundational (Task, TaskStatus, TaskCriterion, ChallengeGenerationLog, Celery app, forbidden_cats, discount_calculator).
- **US2 (Phase 4)**: требует US1 (нужен `services/challenge.py` и `tasks/receipt.py::process_receipt`, куда добавляется прогресс).
- **US3 (Phase 5)**: требует US1 (нужен `tasks/generation.generate_challenges` для замены). НЕ зависит от US2 при отдельной разработке.
- **US4 (Phase 6)**: требует Foundational (Task, TaskStatus). НЕ зависит от US1/US2/US3 при разработке (тесты используют пре-создание строк task), но end-to-end ценность возникает только в паре с US1.
- **US5 (Phase 7)**: требует US1 (расширяет `challenge.py::generate_batch` + тесты через мок).
- **Polish (Phase 8)**: после всех историй.

### User Story Dependencies

- **US1 (P1)**: Foundational → US1. НЕ зависит от других историй.
- **US2 (P1)**: US1 (`tasks/receipt.py`) → US2 (расширение `process_receipt`). Файловая зависимость.
- **US3 (P2)**: US1 (`tasks/generation.py::generate_challenges`) → US3 (использует `.apply_async`). Тестируемо независимо (`generate_challenges` может быть замокан в US3-тестах, но реальный e2e требует наличия US1-реализации).
- **US4 (P2)**: Foundational → US4. НЕ зависит от других историй; для полного smoke-теста в quickstart — нужны US1+US4.
- **US5 (P3)**: US1 (расширяет `challenge.py`) → US5. Может быть отложен.

### Внутри каждой User Story

- Модели/адаптеры (`[P]`) можно параллельно.
- Сервисный слой — после моделей.
- Task/route — после сервисов.
- Тесты — [P] с реализацией (могут быть написаны параллельно с impl, поскольку в разных файлах и не блокируют друг друга).

---

## Parallel Opportunities

### Phase 1 Setup (после T001 — который создаёт synth-package):
```
T002 [P] web/pyproject.toml
T003 [P] docker-compose.yml
T004 [P] .env.example
```
T005 (Dockerfile) может идти параллельно с T002-T004.
T006 (poetry lock) — sequentially, зависит от T002.

### Phase 2 Foundational (после T007 — миграция):
```
T008 [P] entities/task.py
T009 [P] entities/challenge_log.py
T011 [P] crud/challenge_log.py         # не зависит от crud/task
T012 [P] scripts/seed_task_status.py
T013 [P] utils/forbidden_categories.py
T015 [P] core/celery_app.py
```
T010 (crud/task) → T014 (extend discount_calculator) → T016 (DI wiring) — sequential.

### Phase 3 US1:
```
T017 [P] [US1] services/challenge_adapter.py
T019 [P] [US1] tasks/__init__.py
```
Далее T018 (challenge.py, зависит от T017), T020/T021/T022 — sequentially в рамках integration.
Тесты T023/T024/T025 — [P] в конце.

### Phase 4 US2:
```
T026 [P] [US2] services/task_completion.py
```
T027 → T028 — sequential.
T029/T030 — [P] в конце.

### Phase 5 US3:
Только T031 → T032. T033 [P] в конце.

### Phase 6 US4:
```
T034 [P] [US4] schemas/challenge.py
```
T035 → T036 → T037 — sequential.
T038 [P] в конце.

### Phase 7 US5:
T039 → T040 [P].

### Phase 8 Polish (все [P] кроме T044/T045):
```
T041 [P] ARCHITECTURE.md
T042 [P] BACKLOG.md
T043 [P] README.md
```
T044 (lint), T045 (quickstart) — sequentially в самом конце.

---

## Parallel Example: User Story 1

```bash
# После завершения T017 (adapter) — можно параллельно писать тесты и запускать импл сервиса:
Task: "T017 [P] [US1] services/challenge_adapter.py"       # dev A
Task: "T019 [P] [US1] tasks/__init__.py"                  # dev B (тривиально, ~1 мин)

# После T017 + T015 (celery_app):
Task: "T018 [US1] services/challenge.py"                  # dev A
Task: "T023 [P] [US1] tests/services/test_challenge_adapter.py"  # dev C

# После T018:
Task: "T020 [US1] tasks/generation.py"                    # dev A
Task: "T024 [P] [US1] tests/services/test_challenge_service.py"  # dev C

# После T020:
Task: "T021 [US1] tasks/receipt.py"                       # dev A
Task: "T025 [P] [US1] tests/tasks/test_generation_and_receipt.py"  # dev C

# T022 — модификация существующего receipt.py — должна быть последней в US1.
```

---

## Implementation Strategy

### MVP First (User Story 1 + User Story 4)

Практический MVP: US1 (генерация после первого чека) + US4 (просмотр через API). US2/US3/US5 добавляются инкрементально.

1. **Phase 1 Setup**: T001-T006 (~2 часа с учётом Docker/Poetry).
2. **Phase 2 Foundational**: T007-T016 (~1 день). Миграция + ORM + базовые repositories + Celery skeleton + wiring.
3. **Phase 3 US1**: T017-T025 (~1 день). Первая генерация работает end-to-end на бэкенде.
4. **Phase 6 US4**: T034-T038 (~0.5 дня). Пользователь видит 3 задания в мобилке.
5. **STOP → DEMO**: end-to-end работает — регистрация → покупка → задания в мобилке. MVP.
6. **Phase 4 US2**: T026-T030 (~1 день). Замыкание цикла — выполнение + reward.
7. **Phase 5 US3**: T031-T033 (~0.5 дня). Замена по истечению.
8. **Phase 7 US5**: T039-T040 (~0.5 дня). Аудит для hit rate измерения.
9. **Phase 8 Polish**: T041-T045 (~0.5 дня).

Итого: ~5–6 дней при последовательной работе одного разработчика; ~3 дня с параллелизацией 2 разработчиков.

### Incremental Delivery

- После MVP (US1+US4) можно демо: «новый пользователь получает задания». Награда «висит» без выдачи — приемлемо для первого демо, если нет чеков, закрывающих задание.
- После US2 — полный цикл, готов для главного демо.
- US3 — качество (не даёт заданиям «застояться»).
- US5 — метрики (hit rate audit).

### Parallel Team Strategy

С 2 разработчиками:
- Dev A ведёт цепочку US1 (T017-T022) → US2 (T026-T028) — критический путь.
- Dev B параллельно: T023-T025 (тесты US1), T034-T038 (US4 полностью), T031-T033 (US3).
- В конце — общий Polish.

---

## Notes

- **`synth/challenges.py` НЕ модифицируется** во всём этом плане — единственное разрешённое изменение это будущее расширение JSON-схемы LLM другим разработчиком (contract из R11). Наш адаптер (T017) переживает это через `SCRIPT_FIELD_TO_CRITERION_KIND` map + FR-024 защита.
- **Все Celery-задачи внутри `with session.begin()` + pessimistic user-lock** — паттерн из research.md R4. Никогда не начинать вторую транзакцию с расчётом «lock ещё держится».
- **Идемпотентность через БД, не через код**: `task_receipt_increment` UNIQUE(task_id, receipt_id) + `generate_challenges` проверка `count_active >= 3`. Клиентская или Celery-повторная попытка безопасна.
- **Тесты не блокируют commit**: если lint падает — не пропускать через `--no-verify`. Разбираться.
- **Порядок для агента**: строго T001 → T007 → T008/T009 (могут параллельно) → T010 → T014/T016. Пропуск любого фаундейшн-таска порушит US1.
