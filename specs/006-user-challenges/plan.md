# Implementation Plan: Персональные челленджи (задания) для пользователей

**Branch**: `006-user-challenges` | **Date**: 2026-09-04 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/006-user-challenges/spec.md`

## Summary

Интегрировать существующий скрипт `synth/challenges.py` в веб-сервис `webx5` так, чтобы каждый пользователь после первой покупки получал батч из 3 персональных заданий (mix `llm` + `spend_threshold` + `category_expansion`), прогресс заданий обновлялся фоновой задачей при каждом новом чеке, выполнение атомарно создавало персональную скидку, а истечение по дедлайну 7 дней автозаменялось новым заданием.

Подход:

- **Разделение обработки чека:** API-хендлер продолжает синхронно писать `Receipt`/`ReceiptItem` (существующая логика), после успешного `INSERT` ставит Celery-задачу `process_receipt(receipt_id)`; ответ клиенту не блокируется.
- **Celery worker + Redis broker** — новая инфраструктура (уже намечена в `ARCHITECTURE.md` как to-be). Задачи: `process_receipt`, `generate_challenges(user_id, count)`, `expire_tasks` (Beat каждые 60 сек).
- **Скрипт `synth/challenges.py` не модифицируется** — весь impedance mismatch концентрируется в `services/challenge_adapter.py`: ORM → dict-профиль на входе, dict-результат → Task+TaskCriterion на выходе.
- **Новые сущности БД:** `task`, `task_status`, `task_criterion` (EAV), `task_receipt_increment` (idempotency), `challenge_generation_log` (audit).
- **Мост для будущих типов наград:** `task.reward_type` + `task.reward_id` без FK-constraint; в MVP всегда `'discount'` + указатель на `discounts.id`.
- **Concurrency:** pessimistic per-user lock через `SELECT users.id FOR UPDATE` в начале транзакции воркера.
- **`synth`-пакет** попадает в web-образ через path-dependency в `web/pyproject.toml` (`{path = "../synth", develop = false}`) + копирование `config/synth_schema.yaml` в контейнер — избегает дублирования кода при сохранении раздельных ответственностей.

## Technical Context

**Language/Version**: Python 3.12 (существующий стек `web/`, ср. `pyproject.toml`)

**Primary Dependencies**:
- Существующие: FastAPI, SQLAlchemy 2.x (sync), Alembic, Pydantic 2, structlog, psycopg2-binary, phonenumbers, fastapi-pagination
- Новые: **celery[redis]>=5.4** (worker + beat), **redis>=5.0** (клиент), **pyyaml>=6.0** (для загрузки `config/synth_schema.yaml` через `synth.config.load_config`), **requests>=2.32** (уже требуется `synth/challenges.py`)
- Path-dep: `synth = { path = "../synth", develop = false }` в `[tool.poetry.dependencies]` — переиспользование скрипта без копирования файлов в web/

**Storage**: PostgreSQL 16 (существующий), новые таблицы: `task`, `task_status`, `task_criterion`, `task_receipt_increment`, `challenge_generation_log`. Redis 7 — только Celery broker + result backend (не persistent storage бизнес-данных).

**Testing**: pytest 8 (существующий), httpx для интеграционных тестов API, `CELERY_TASK_ALWAYS_EAGER=True` для in-process тестов Celery-задач. Тесты живут в `web/tests/webx5/` (зеркалируют `src/`, как требует конституция).

**Target Platform**: Linux server (Docker Compose стек, тот же образ для API/worker/beat — точка входа переключается через command).

**Project Type**: web-service (монолит FastAPI + фоновые задачи). См. существующий `web/src/webx5/`.

**Performance Goals**:
- POST /receipts p95 ≤ 2 сек (SC-005) — от синхронной записи ждать не приходится, LLM в фон.
- GET /challenges/current p95 ≤ 500 мс (SC-007) — простой JOIN task + task_criterion.
- Латентность появления 3 заданий после первого чека ≤ 30 сек (SC-001) — включает enqueue + 1 LLM call (~2–10 сек) + 2 детерминированных + запись.
- Латентность истечения ≤ 5 мин (SC-004) — Beat каждые 60 сек с запасом.

**Constraints**:
- Скрипт `synth/challenges.py` не переименовывать и не изменять (единственное разрешённое изменение — уже запланированное расширение LLM JSON-схемы другим разработчиком; наш адаптер ловит новое поле автоматически через EAV `task_criterion`).
- Названия существующих ORM-полей (`Receipt.purchase_date`, `Product.current_price`, `Category.name` и т.д.) не переименовывать под нужды скрипта.
- БД — source of truth: недостающие поля добавляются миграцией.
- Reward в MVP — только `discount`; мост FR-011a оставляет место для Coupon/Points.
- Хранение секретов: `OPENROUTER_API_KEY` — только через env, никогда не логируется вместе с prompt.
- Пул одновременных LLM-вызовов из воркеров ограничен: `worker --concurrency=2` для очереди `challenges` (осторожность с OpenRouter rate-limit 429 — скрипт уже ретраит).

**Scale/Scope**:
- ~10 000 пользователей в PoC (соответствует объёму синтетики).
- ~30 чеков/сут/пользователь в пик (грубо ~300 rps теоретически, реально POC ≤ 5 rps).
- 3 активных задания × 10к = ~30к активных Task-строк в любой момент.
- ~100 LLM-вызовов/час на пик (первые чеки + expirations). Расход OpenRouter — контролируемый.
- Аудит-лог: ~1 строка на каждый вызов скрипта (успех/фолбэк/no_challenge); ~1–10к строк в сутки при активной генерации.

## Constitution Check

*GATE: Проверка соответствия `.specify/memory/constitution.md` v1.2.0.*

### Core Principles

| Принцип | Проверка | Статус |
|---|---|---|
| **I. Экономия как единая видимая метрика** | Task.reward_rub (в рублях) отображается пользователю; Reward = Discount, вычисленная от margin (via `estimate_max_reward_rub`); задание = «сколько сэкономишь». Никаких абстрактных баллов. | ✅ Pass |
| **II. Минимальный когнитивный барьер (NON-NEGOTIABLE)** | Один эндпоинт `GET /challenges/current` возвращает готовый список — 1 действие от главного экрана мобилки. Никакой «настройки», выбора челленджей, комбинаторики механик. Только 3 карточки. | ✅ Pass |
| **III. ИИ-персонализация с верифицируемым hit rate** | Персональный челлендж генерируется через существующий `synth/challenges.py` (LLM или детерминированные пути). Шаблонные задания используются только как fallback. Reasoning логируется в `challenge_generation_log`. Hit rate ≥70% на 30–50 профилях уже подтверждён (spec `2026-09-03-synthetic-data-schema-design.md` + CONTEXT_PACK §6 H2 status). | ✅ Pass |
| **IV. Экономическая обоснованность** | `reward_rub` clamp через `estimate_max_reward_rub` (4× mean gross margin пользователя) — скрипт уже гарантирует, что награда ≤ ожидаемого приращения маржи. `spend_threshold` использует `discount_pct=15%` от цены товара, ограниченное margin ceiling. `category_expansion` — 5% (заведомо ниже минимального margin_pct 8.47% eligible-категорий). Юнит-экономика уже прошита в скрипт. | ✅ Pass |
| **V. Privacy by Design** | Задания не показывают ФИО/адреса. LLM prompt содержит только `chain, segment, family_size, habitual_categories, top_categories, weekend_share, promo_share, mean_receipt_total_rub` — агрегаты, без чеков и адресов. Reward не связывается с рейтингом. | ✅ Pass |

### Технические ограничения (PoC/Хакатон)

| Ограничение | Проверка | Статус |
|---|---|---|
| Только синтетические данные | Скрипт работает с synth-data, реальные ПД не используются. | ✅ Pass |
| Стек: Python + LLM API | Не меняется. LLM через OpenRouter (уже настроено в скрипте). | ✅ Pass |
| Скоуп демо: 3 экрана + челлендж | `GET /challenges/current` покрывает экран «Задания». | ✅ Pass |
| Антифрод: опционально | Не в скоупе feature. | ✅ Pass |

### Backend Technical Standards

| Требование | План соответствия | Статус |
|---|---|---|
| **RSI (Repository/Service/Interface)** | `crud/task.py` (Repository), `services/challenge.py` + `services/challenge_adapter.py` + `services/task_completion.py` (Service), `routes/challenges.py` (Interface). Отдельно `tasks/` для Celery task-функций (Interface-слой для worker). | ✅ Pass |
| **DI (сервис получает репозиторий снаружи)** | Все репозитории создаются в `core/challenges.py` и передаются в конструкторы сервисов; сервис никогда не делает `Repository()` внутри. | ✅ Pass |
| **Контролируемая инициализация** | Модули `crud/`, `services/`, `routes/`, `tasks/` — без side effects на импорте. Celery app и wiring — только в `core/celery_app.py` и `core/challenges.py`. | ✅ Pass |
| **Poetry, не pip** | `celery[redis]`, `redis`, `pyyaml`, `synth` (path-dep) — все добавляются через `web/pyproject.toml`. Dockerfile использует существующий `poetry install`. | ✅ Pass |
| **Скрипты: print; сервисы: structlog** | `synth/challenges.py` — скрипт (использует print — не трогаем). Всё в `webx5/` — structlog. Celery worker log настраивается через тот же `configure_logging()`. | ✅ Pass |
| **Tests зеркалируют src** | `web/tests/webx5/services/test_challenge_adapter.py`, `web/tests/webx5/services/test_challenge_service.py`, `web/tests/webx5/routes/test_challenges.py`, `web/tests/webx5/tasks/test_process_receipt.py` и т.д. | ✅ Pass |
| **entities/ ≠ schemas/** | ORM в `entities/task.py`; Pydantic-схемы в `schemas/challenge.py`. Одна не наследуется от другой. | ✅ Pass |

**Gate result**: ✅ ALL GATES PASS. Никаких нарушений, `Complexity Tracking` не заполняется.

## Project Structure

### Documentation (this feature)

```text
specs/006-user-challenges/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output — deferred decisions from clarify
├── data-model.md        # Phase 1 output — SQL schema + ORM structure
├── quickstart.md        # Phase 1 output — валидация end-to-end flow
├── contracts/           # Phase 1 output
│   ├── challenges-api.yaml     # OpenAPI для GET /challenges/current
│   └── celery-tasks.md         # Внутренние контракты Celery tasks
├── checklists/
│   └── requirements.md  # Из specify+clarify
└── tasks.md             # Phase 2 output (/speckit-tasks — НЕ создаётся этой командой)
```

### Source Code (repository root)

Существующая монолит-структура `web/src/webx5/` расширяется. Новые файлы **выделены жирным**:

```text
web/
├── Dockerfile                                  # добавляется stage/command для celery worker & beat
├── pyproject.toml                              # +celery[redis], +redis, +pyyaml, +synth (path-dep)
├── poetry.lock                                 # регенерация
├── alembic/
│   └── versions/
│       └── f4a5b6c7d8e9_add_task_tables.py    # NEW: task, task_status, task_criterion, task_receipt_increment, challenge_generation_log
├── scripts/
│   └── seed_task_status.py                    # NEW: сид словаря task_status (открыто/выполнено/провалено/истекло)
└── src/webx5/
    ├── main.py                                  # без изменений
    ├── core/
    │   ├── celery_app.py                       # NEW: Celery(app_name), брокер/бэкенд из env, beat_schedule
    │   ├── challenges.py                       # NEW: DI-wiring TaskRepository, ChallengeService, ChallengeAdapter, TaskCompletionService
    │   ├── db.py                                # без изменений
    │   ├── purchases.py                         # +enqueue process_receipt в receipt_service (см. services/receipt.py)
    │   ├── logging_config.py                   # без изменений
    │   └── server.py                            # +include challenges_router
    ├── entities/
    │   ├── task.py                             # NEW: Task, TaskStatus, TaskCriterion, TaskReceiptIncrement
    │   └── challenge_log.py                    # NEW: ChallengeGenerationLog
    ├── crud/
    │   └── task.py                             # NEW: TaskRepository (get_active_for_user, create_batch, replace, mark_completed, expire_overdue, get_task_criteria, record_increment)
    ├── services/
    │   ├── challenge_adapter.py                # NEW: ORM ↔ dict-profile mapping (для synth.challenges.generate_challenge_for_user); dict-result → Task+TaskCriterion
    │   ├── challenge.py                        # NEW: ChallengeService — high-level (get_current, generate_batch, generate_single_replacement)
    │   ├── task_completion.py                  # NEW: completion-checker с polymorphic kind-роутером; reward creation
    │   └── receipt.py                          # МОДИФИЦИРОВАН: create_receipt в конце enqueue-ит process_receipt(receipt.id) (только если is_new=True + loyalty_card_id)
    ├── routes/
    │   └── challenges.py                       # NEW: GET /challenges/current
    ├── schemas/
    │   └── challenge.py                        # NEW: ChallengeResponse, ChallengeListResponse, EmptyStateReason enum
    ├── dependencies/                           # без изменений
    ├── tasks/                                   # NEW package (Celery task-functions — Interface-слой для worker)
    │   ├── __init__.py
    │   ├── receipt.py                          # process_receipt(receipt_id) — pessimistic lock, увеличить прогресс, mark_completed, enqueue replace
    │   ├── generation.py                       # generate_challenges(user_id, count=3) — mix llm+spend_threshold+category_expansion
    │   └── expiration.py                       # expire_tasks() — Celery Beat, каждые 60 сек
    └── utils/
        └── forbidden_categories.py             # NEW: чтение config/synth_schema.yaml (или FastAPI startup — синглтон)
web/tests/webx5/
├── services/
│   ├── test_challenge_adapter.py               # NEW: маппинг ORM → dict; dict → Task
│   ├── test_challenge_service.py               # NEW: batch mix, no_challenge, existing tasks
│   ├── test_task_completion.py                 # NEW: item_quantity, spend_threshold_rub, unknown kind
│   └── test_receipt.py                          # НОВЫЙ ТЕСТ: enqueue после create_receipt
├── tasks/
│   ├── test_process_receipt.py                 # NEW: eager mode
│   ├── test_generation.py                      # NEW: eager mode
│   └── test_expiration.py                       # NEW: eager mode
├── routes/
│   └── test_challenges.py                      # NEW: 200 (3 tasks), 200 (empty for new user), 200 (saturated), 401
└── crud/
    └── test_task.py                            # NEW: repository CRUD
docker-compose.yml                              # +redis, +worker (celery ... worker), +beat (celery ... beat)
.env.example                                    # +REDIS_URL, +OPENROUTER_API_KEY, +CHALLENGE_LLM_MODEL, +CHALLENGE_TYPE_DEFAULT
```

**Structure Decision**: Монолитная web-service структура (существующая) с path-dep на `synth/`. Не выделяем `worker/` в отдельный образ — тот же Docker image, разная команда запуска (`celery worker` vs `celery beat` vs `uvicorn`); всё в одном `web/` дереве. Обосновано: (1) `synth/challenges.py` уже написан как pure function без state — его импорт в web-процесс безопасен; (2) shared модели/схемы/логирование переиспользуются между API и worker; (3) для PoC 3 контейнера (`db`, `redis`, `worker+api+beat`) проще держать в один compose, чем 5.

## Complexity Tracking

> Constitution Check прошёл без violations — таблица не заполняется.

---

## Phase 0: Outline & Research

Ниже — deferred-решения из clarify и открытые технические вопросы, требующие research перед data-model. Каждое решение будет зафиксировано в `research.md`.

### R1. Правило конвертации `reward_rub` → `discounts.value` (FR-011 deferred)

**Задача:** `synth/challenges.py` возвращает `reward_rub` (руб). Существующая `discounts.value` — процент. Как атомарно создавать Discount на completion?

**Кандидаты:**
- (a) Расширить `discounts` полем `value_type ∈ {'percent', 'fixed_rub'}` (уже в BACKLOG) + миграция + правка `discount_calculator.py` на кассе. Задача: чистое расширение схемы, инвазия только в один сервис (discount_calculator).
- (b) Хранить `Reward` не в `discounts`, а на самом Task (`reward_rub` уже есть), API отдаёт как «купон N ₽». Не задействует кассовую discount-логику; при следующем чеке пользователь не получает автоматическую скидку.
- (c) Всегда конвертировать `reward_rub` в процент от известной цены товара (для `spend_threshold`/`category_expansion` есть конкретный product; для generic — цена товара из криеerion category = среднее по категории). Хрупко для generic.

**Research direction:** проверить, насколько инвазивна миграция `discounts.value_type` в `web/src/webx5/services/discount_calculator.py` — если < 30 LOC изменений, идти на (a); иначе fallback (b).

### R2. Sequential vs parallel запуск 3 генераций в батче (FR-005a deferred)

**Задача:** батч из 3 challenge_type — как запускать в фоновой задаче?

**Кандидаты:**
- (a) Последовательно в одной Celery-задаче: `spend_threshold` (нет сети) → `category_expansion` (нет сети) → `llm` (~2–10 сек). Латентность батча = latency LLM. Порядок «дёшёвое сначала» — при таймауте LLM пользователь уже получил 2 задания.
- (b) 3 параллельные Celery-задачи (`.apply_async` × 3, разные challenge_type). Латентность батча = max(3) ≈ latency LLM. Проще откатывать при частичном сбое (независимые задачи), но требует orchestration для FR-005 «не дублировать criterion».
- (c) Скрипт вызывается 3 раза в цикле в одном воркере с `worker --concurrency=2` — Celery сам разведёт.

**Research direction:** для PoC достаточно (a). Замерить: 1 LLM call ~5 сек, 2 детерминированных ~50 мс — суммарно ~5 сек, что укладывается в SC-001 (30 сек). Параллельность не нужна.

### R3. Точный TTL `discounts.valid_to` для reward (FR-011 deferred)

**Задача:** Discount, созданный при completion, должен когда-то истечь.

**Кандидаты:**
- (a) `valid_to = completed_at + 7 days` (столько же, сколько task deadline).
- (b) `valid_to = task.deadline` (пользователь должен использовать награду до конца изначального срока task — жёстче).
- (c) `valid_to = completed_at + 30 days` (месяц на использование скидки — щадяще).

**Research direction:** (a) — симметрично task deadline; (c) — щадяще для пользователя. Рекомендация (a) для PoC, зафиксировать в research.md.

### R4. Конкретная реализация locking (FR-014 deferred)

**Задача:** SQLAlchemy 2.x sync API для `SELECT ... FOR UPDATE`.

**Известно:** SQLAlchemy предоставляет `session.query(User).filter_by(id=user_id).with_for_update().one()` или `session.execute(select(User).where(User.id == user_id).with_for_update()).scalar_one()`. Нужна в открытой транзакции. Постгрес освобождает lock при commit/rollback.

**Research direction:** зафиксировать pattern в research.md. Проверить, что `Database.get_sync_session()` открывает транзакцию (сейчас нет explicit `session.begin()` — SQLAlchemy 2.x автокоммитит, нужно завернуть в `with session.begin():`).

### R5. Размещение `synth/` в web-образе

**Задача:** `synth/challenges.py` + `synth/config.py` + `config/synth_schema.yaml` должны быть доступны в контейнере worker/api.

**Кандидаты:**
- (a) **path-dep в Poetry**: `synth = { path = "../synth", develop = false }` в `web/pyproject.toml`. Poetry копирует пакет в venv контейнера при `poetry install`. Стандартный подход.
- (b) `PYTHONPATH=/app/synth` через Dockerfile + `COPY synth /app/synth`. Проще, но обходит зависимости.
- (c) Публиковать `synth` как отдельный wheel — overhead для хакатона.

**Research direction:** (a). Также: `config/synth_schema.yaml` должен монтироваться volume в compose (`./config:/config:ro`) или копироваться в образ через `COPY config /config`. Скрипт ищет config path из аргумента — сервис задаёт через env `SYNTH_CONFIG_PATH=/config/synth_schema.yaml`.

### R6. Периодичность Celery Beat expiration sweep

**Задача:** FR-004 требует ≤5 мин задержки на истечение; частая проверка = лишний scan.

**Кандидаты:**
- (a) Каждые 60 сек — 60 scan/час, каждый ≤ 100 мс. Даёт запас по SC-004.
- (b) Каждые 5 мин — минимум запаса.
- (c) Динамика: следующая проверка в `min(deadline)` — сложнее.

**Research direction:** (a). Индексировать `task(status_id, deadline)` для быстрого фильтра.

### R7. LLM call timeout в фоновой задаче

**Задача:** Скрипт использует `timeout=60` и `max_retries=3`. В worst-case задача может висеть 60 × 3 = 180 сек.

**Research direction:**
- Установить Celery `task_time_limit=120` для очереди `challenges` — задача убивается на 2-й минуте.
- В скрипте `call_openrouter(..., timeout=30, max_retries=2)` — переопределить через параметры при вызове из `services/challenge_adapter.py`. Это НЕ модификация скрипта — это параметры, которые уже принимаются.

### R8. Хранение `forbidden_categories`

**Задача:** FR-008 требует не двигать прогресс на позициях из forbidden_categories. Список сейчас — в `config/synth_schema.yaml` (используется скриптом).

**Research direction:** Читать тот же yaml на startup FastAPI + worker, кэшировать в модуле `utils/forbidden_categories.py` как `set[str]`. Единый source of truth со скриптом.

### R9. Определение «первого чека» пользователя (FR-002)

**Задача:** Как быстро проверить «это первый чек пользователя» в `process_receipt`?

**Кандидаты:**
- (a) `session.query(exists().where(Task.loyalty_card_id == user_id)).scalar()` — если задач нет, значит первый чек.
- (b) `session.query(func.count(Receipt.id).where(Receipt.loyalty_card_id == user_id)).scalar() == 1` — новых чеков ровно 1.

**Research direction:** (a) быстрее и логически прозрачнее для нашего инварианта: «нет открытых задач + это не saturated пользователь → генерировать 3». Учитывает и «существующий seed-пользователь без задач».

### R10. Product lookup по имени (FR-021)

**Задача:** Скрипт возвращает `favorite_item` / `novel_item` как строку («молоко», «яблоки»). В БД `products.name` — полное имя SKU («Молоко Простоквашино 3.2% 1л»).

**Research direction:**
- В `synth` каталоге items = короткие имена категорий («молоко»). В БД products — реальные SKU.
- Стратегия lookup в адаптере: `session.query(Product).filter(Product.name.ilike(f'%{item}%'), Product.category_id == cat_id).first()`. Если None — fallback на criterion_type=category.
- Индекс `products USING gin(name gin_trgm_ops)` — оверинженерия для PoC; hardcoded `ilike` подойдёт.

### R11. Расширение JSON-схемы LLM другим разработчиком

**Задача:** Коллега добавит поле в JSON-схему LLM. Как адаптер узнает про новое поле?

**Research direction:** адаптер имеет explicit map `SCRIPT_FIELD_TO_CRITERION_KIND = {'spend_threshold_rub': 'spend_threshold_rub', ...}`. Коллега (или мы) добавляет строку в map — новый `kind` начинает писаться в `task_criterion`. Completion-checker для нового kind — отдельный PR (иначе задание не может быть выполнено — защита FR-024). Задокументировать в `research.md` как «contract с другим разработчиком».

**Deliverable Phase 0:** `specs/006-user-challenges/research.md` — все R1..R11 с решениями и rationale.

---

## Phase 1: Design & Contracts

### Data Model (`data-model.md`)

Формальная схема с типами Postgres, констрейнтами, индексами. Основные моменты:

- **`task_status`** — словарь: `id UUID PK, name VARCHAR UNIQUE`. Сид: `открыто, выполнено, провалено, истекло`. Скрипт сида — `scripts/seed_task_status.py`.
- **`task`** — расширение `context/schema.md` с новыми полями (title, description, mechanic, reward_rub NUMERIC(10,2), reasoning TEXT, path VARCHAR, model VARCHAR, reward_type VARCHAR NOT NULL DEFAULT 'discount', reward_id UUID NULL). FK: `loyalty_card_id → users.id`, `task_status_id → task_status.id`. Индексы: `(loyalty_card_id, task_status_id)`, `(task_status_id, deadline)`.
- **`task_criterion`** — EAV: `id UUID PK, task_id UUID FK, kind VARCHAR, key VARCHAR NULL, value_num NUMERIC NULL, value_text VARCHAR NULL, created_at`. Индекс: `(task_id)`. Constraint: `CHECK (value_num IS NOT NULL OR value_text IS NOT NULL)`.
- **`task_receipt_increment`** — dedupe: `task_id UUID FK, receipt_id UUID FK, applied_at`, PK`(task_id, receipt_id)`. Индекс: `(receipt_id)` для reverse-lookup.
- **`challenge_generation_log`** — audit: `id UUID PK, user_id UUID NOT NULL, task_id UUID NULL, model VARCHAR NULL, prompt TEXT NULL, response TEXT NULL, path VARCHAR NOT NULL, reasoning TEXT NULL, error TEXT NULL, created_at`. Индекс: `(user_id, created_at DESC)`.
- **`discounts`** — расширение (согласно R1): добавить `value_type VARCHAR NOT NULL DEFAULT 'percent'`, `link_task_id UUID NULL` (nullable, без FK, обратная ссылка на task для аудита).
- **State transitions** для `task`: `открыто → выполнено` (при completion), `открыто → истекло` (по expire sweep). `выполнено`/`истекло` — terminal.

### Contracts (`contracts/`)

- **`contracts/challenges-api.yaml`** — OpenAPI 3.0:
  - `GET /challenges/current` — Bearer JWT; response `ChallengeListResponse` (items: max 3, каждый — `ChallengeItem` с полями id, title, description, mechanic, reward_rub, criterion_type, criterion_entity_id, quantity_target, quantity_current, deadline, status, empty_reason ∈ {none, no_history, saturated}).
  - Errors: 401.
- **`contracts/celery-tasks.md`** — внутренние контракты Celery task-функций:
  - `process_receipt(receipt_id: str)` — единственный аргумент, всё остальное подтягивается из БД по FK. Идемпотентно. Возможные исходы: `no_op` (loyalty_card_id=NULL или чек не найден), `progressed` (обновили N tasks), `completed_and_replaced` (закрыли K + enqueued generate).
  - `generate_challenges(user_id: str, count: int, exclude_types: list[str] = None)` — генерирует `count` заданий mix'ом типов, исключая типы из активных. Идемпотентно на уровне «не создавать 4-е задание, если уже 3 открыто» (проверка активных перед insertom).
  - `expire_tasks()` — Beat every 60s. Сканирует `WHERE status='открыто' AND deadline < now() FOR UPDATE SKIP LOCKED LIMIT 100`, переводит в 'истекло', enqueues `generate_challenges(user_id, count=N_expired_for_user)`.

### Quickstart (`quickstart.md`)

Runnable end-to-end валидация после `docker compose up`:

1. Seed: `docker compose run --rm web python scripts/seed_task_status.py` + существующие seed'ы каталога/магазинов/скидок.
2. Регистрация: `curl POST /register {"phone": "+79000000001"}` → сохранить access_token.
3. Отправка чека от кассы: `curl POST /receipts -H "X-Terminal-Token: ..." -H "X-Idempotency-Key: <uuid>" {"loyalty_card_id": "<uuid>", "store_id": "<uuid>", "items": [...]}` → 201.
4. Ожидание ≤30 сек (SC-001).
5. `curl GET /challenges/current -H "Authorization: Bearer <token>"` → массив из 3 заданий.
6. Отправить второй чек с product, попадающим в criterion одного из заданий → ожидание ≤10 сек → GET /challenges/current показывает 1 задание с обновлённым `quantity_current` (или новое задание, если старое закрылось + generate уже отработал).
7. Проверка `challenge_generation_log`: `psql -c 'SELECT path, count(*) FROM challenge_generation_log GROUP BY path'` — минимум одна запись на каждый вызов.
8. Экспиреjн-сценарий: `psql -c "UPDATE task SET deadline = now() - interval '1 day' WHERE id = '<uuid>'"` → ожидание ≤2 мин → `psql SELECT status FROM task WHERE id = '<uuid>'` → 'истекло'; новое задание существует.

### Re-evaluate Constitution Check (post-design)

**Design артефакты Phase 1 не создают новых нарушений:**

- Data model добавляет 5 новых таблиц — все под контролем RSI (crud/task.py, crud/challenge_log.py если понадобится). ✅
- Contracts (OpenAPI + celery-tasks.md) не меняют пользовательский UX — экран остаётся один. ✅
- Quickstart проходит без ручной настройки — < 2 действий пользователя мобилки (login → open Challenges). ✅
- Reward = Discount с `value_type='fixed_rub'` (или процент по R1 resolution) — экономика по-прежнему прошита в скрипт. ✅
- Privacy: OpenAPI response не содержит ФИО/адресов; log содержит только user_id UUID. ✅

**Constitution Check post-design: PASS.** Проект готов к `/speckit-tasks`.

**Deliverables Phase 1:**
- `specs/006-user-challenges/data-model.md`
- `specs/006-user-challenges/contracts/challenges-api.yaml`
- `specs/006-user-challenges/contracts/celery-tasks.md`
- `specs/006-user-challenges/quickstart.md`
