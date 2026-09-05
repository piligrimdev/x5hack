# Задачи: Инфраструктура Наблюдаемости и Мониторинга

**Исходные Данные**: Документы дизайна из `/specs/001-add-observability-infrastructure/`

**Предусловия**: plan.md (требуется), spec.md (требуется для пользовательских сценариев), research.md, data-model.md, contracts/

**Организация**: Задачи сгруппированы по пользовательскому сценарию для независимой реализации и тестирования каждого сценария.

## Формат: `[ID] [P?] [Story] Описание`

- **[P]**: Может выполняться параллельно (разные файлы, нет зависимостей)
- **[Story]**: Какому пользовательскому сценарию принадлежит задача (US1, US2, US3, US4)
- Включайте точные пути к файлам в описаниях

---

## Phase 1: Setup (Инициализация Проекта)

**Цель**: Подготовка инфраструктуры и конфигурации для всех компонентов observability

- [x] T001 Добавить зависимости в `web/pyproject.toml`: prometheus-client, langfuse, flower
- [x] T002 [P] Создать директорию `monitoring/` с подпапками: prometheus, loki, promtail, grafana, langfuse
- [x] T003 [P] Создать `monitoring/prometheus/prometheus.yml` с конфигурацией scrape targets
- [x] T004 [P] Создать `monitoring/loki/loki-config.yml` с конфигурацией хранилища
- [x] T005 [P] Создать `monitoring/promtail/promtail-config.yml` для сбора логов из контейнеров
- [x] T006 [P] Создать `monitoring/grafana/datasources.yml` для регистрации Prometheus и Loki
- [x] T007 [P] Создать `monitoring/langfuse/docker-compose-override.yml` для self-hosted Langfuse
- [x] T008 Обновить `docker-compose.yml`: добавить сервисы prometheus, loki, promtail, grafana, flower, langfuse с ports и healthchecks
- [x] T009 [P] Создать `.env.example` с новыми переменными окружения: LANGFUSE_API_KEY, PROMETHEUS_MULTIPROC_DIR
- [x] T010 Обновить `.gitignore`: добавить `monitoring/*/data`, `monitoring/*/logs`, `langfuse_db/`

---

## Phase 2: Foundational (Критические Предусловия)

**Цель**: Базовая инфраструктура observability, необходимая для всех сценариев

**⚠️ КРИТИЧНО**: Работа со сценариями не может начаться, пока эта фаза не завершена

- [x] T011 Обновить `web/src/webx5/core/logging_config.py`: добавить 5 обязательных labels (service_name, user_id, request_id, procedure_name, procedure_state) в structlog контекст
- [x] T012 Создать `web/src/webx5/utils/contextvars_utils.py` для управления контекстными переменными: user_id_context, request_id_context
- [x] T013 Создать `web/src/webx5/utils/metrics.py` с Prometheus метриками: REQUEST_COUNT, REQUEST_LATENCY, ERROR_COUNT, CELERY_TASKS_PROCESSED, CELERY_TASK_DURATION, LLM_GENERATION_SUCCESS, LLM_GENERATION_FAILED, BASKET_CALCULATION_DURATION, ACTIVE_CELERY_WORKERS
- [x] T014 Обновить `web/src/webx5/main.py`: инициализировать Langfuse SDK с graceful degradation (try/except для отсутствующего API key)
- [x] T015 Обновить `web/src/webx5/core/server.py`: добавить PrometheusMiddleware для автоматического сбора HTTP метрик; expose `/metrics` endpoint
- [x] T016 Создать `web/src/webx5/middleware/request_context.py` для установки user_id в контекст из Authorization header при каждом запросе
- [x] T017 Обновить `web/src/webx5/dependencies/auth.py`: вызывать contextvars.set для user_id_context при успешной аутентификации
- [x] T018 Проверить что docker-compose.yml поднимает все сервисы (web, worker, db, redis, prometheus, loki, promtail, grafana, flower, langfuse) без ошибок: `docker-compose up -d && docker-compose ps`

**Checkpoint**: Foundation готовой - работа над сценариями может начаться параллельно

---

## Phase 3: User Story 1 - DevOps Мониторит Здоровье Системы (Priority: P1) 🎯 MVP

**Цель**: Создать Grafana дашборды, которые агрегируют метрики Prometheus и показывают health приложения в реальном времени

**Независимый Тест**: Запустить docker-compose; открыть Grafana; проверить что три дашборда видны и отображают актуальные метрики; сделать несколько HTTP запросов; убедиться что метрики обновились на дашбордах в течение 10 секунд

### Реализация для User Story 1

- [x] T019 [P] [US1] Создать `monitoring/grafana/dashboards/api-health.json` дашборд: latency p50/p95/p99, error rate по endpoint, request count по method, status code distribution
- [x] T020 [P] [US1] Создать `monitoring/grafana/dashboards/celery-queue.json` дашборд: queue depth по queue name, active workers count, task execution time histogram, success vs failure rate, slow tasks (outliers)
- [x] T021 [P] [US1] Создать `monitoring/grafana/dashboards/llm-costs.json` дашборд: total tokens per user (line chart), total cost per user (table), model distribution (pie chart), cost per day (bar chart)
- [x] T022 [US1] Обновить `monitoring/grafana/datasources.yml`: убедить что Prometheus и Loki регистрируются как datasources с корректными URL (http://prometheus:9090, http://loki:3100)
- [x] T023 [US1] Обновить docker-compose.yml сервис Grafana: добавить volume мounts для provisioning dashboards и datasources: `./monitoring/grafana/dashboards:/etc/grafana/provisioning/dashboards` и `./monitoring/grafana/datasources.yml:/etc/grafana/provisioning/datasources/datasources.yml`
- [x] T024 [US1] Протестировать Prometheus metrics endpoint: `curl http://localhost:8000/metrics | head -20` возвращает метрики в Prometheus формате (text/plain)
- [x] T025 [US1] Протестировать что Grafana может queryить Prometheus: открыть Grafana UI (localhost:3000), добавить query `http_requests_total` в explore, убедить что results видны
- [x] T026 [US1] Протестировать что Grafana dashboards обновляются: открыть dashboard, сделать curl запрос к API, убедить что метрики обновились в течение 10 секунд

**Checkpoint**: User Story 1 полностью функциональна и независимо тестируема

---

## Phase 4: User Story 2 - Backend Разработчик Отлаживает Ошибки (Priority: P1)

**Цель**: Структурированные логи от FastAPI отправляются в Loki через Promtail с queryable labels; разработчик может поискать по user_id и увидеть все логи для этого пользователя

**Независимый Тест**: Запустить docker-compose; сделать аутентифицированный запрос; открыть Grafana Loki explore; query {user_id="<uuid>"}; убедить что все логи содержат 5 обязательных labels и stack trace для ошибок; убедить что логи появляются в течение 5 секунд

### Реализация для User Story 2

- [x] T027 [P] [US2] Убедить что `web/src/webx5/core/logging_config.py` добавляет 5 labels в structlog contextvars processor (из T011)
- [x] T028 [P] [US2] Убедить что Promtail конфиг (`monitoring/promtail/promtail-config.yml`) имеет pipeline_stages с json extraction для: timestamp, level, service_name, user_id, request_id, procedure_name, procedure_state
- [x] T029 [US2] Обновить FastAPI routes: добавить structlog.get_logger().info() в начале каждого route handler для логирования входящего запроса с procedure_name и procedure_state="started"
- [x] T030 [US2] Обновить FastAPI routes: добавить structlog.get_logger().info() в конце успешного обработки для логирования procedure_state="completed" с duration_ms
- [x] T031 [US2] Обновить FastAPI middleware или exception handlers: логировать исключения с procedure_state="failed", error_type (класс исключения), error_message и stack_trace
- [x] T032 [US2] Убедить что contextvars.set() вызывается для user_id в middleware (из T016) перед тем как ивидит request handlers
- [x] T033 [US2] Протестировать что Loki получает логи: сделать curl запрос; проверить `docker-compose logs promtail` что нет ошибок; открыть Loki в Grafana; query {service_name="webx5"} возвращает recent logs
- [x] T034 [US2] Протестировать queryability по labels: открыть Grafana Loki; query {user_id="<user-uuid>"} возвращает все логи для пользователя; query {procedure_state="failed"} возвращает только failed операции
- [x] T035 [US2] Протестировать latency: сделать curl запрос; убедить что логи появляются в Loki в течение 5 секунд (проверить timestamp разницу)

**Checkpoint**: User Story 2 полностью функциональна и независимо тестируема

---

## Phase 5: User Story 3 - ML Инженер Мониторит LLM Производительность (Priority: P1)

**Цель**: Все вызовы OpenRouter трейсируются в Langfuse с user_id (из контекста), token counts, latency и cost; ML инженер может видеть usage per user в Langfuse dashboard

**Независимый Тест**: Запустить docker-compose; сделать запрос, который вызывает OpenRouter LLM; открыть Langfuse UI (localhost:3000); убедить что трейс появился с user_id, model, input/output tokens, latency, cost; убедить что трейс появился в течение 2 секунд; провалить OpenRouter запрос (например, rate limit); убедить что приложение продолжает работать и логирует warning о недоступности Langfuse

### Реализация для User Story 3

- [x] T036 [P] [US3] Создать `web/src/webx5/core/langfuse_client.py`: инициализация Langfuse SDK с API key из .env, graceful degradation при отсутствии ключа (log warning вместо crash)
- [x] T037 [US3] Обновить `web/src/webx5/main.py` (из T014): вызвать инициализацию Langfuse клиента; убедить что обработка ошибок не блокирует startup
- [x] T038 [US3] Создать wrapper функцию `call_openrouter_tools_traced()` в `web/src/webx5/core/llm.py`: оборачивает существующую `call_openrouter_tools()` с Langfuse trace context; извлекает user_id из contextvars; логирует trace с model, input/output tokens, latency_ms, cost_usd; gracefully handles Langfuse API unavailability
- [x] T039 [US3] Обновить все вызовы `call_openrouter_tools()` в codebase на `call_openrouter_tools_traced()` (search in: `services/basket_assistant.py`)
- [x] T040 [P] [US3] Убедить что contextvars.set() для user_id вызывается перед LLM вызовом (в routes или middleware)
- [x] T041 [US3] Обновить `web/src/webx5/core/langfuse_client.py`: добавить try/except блоки вокруг Langfuse trace для graceful degradation (log warning если Langfuse недоступен, но continue execution)
- [ ] T042 [US3] Протестировать что Langfuse получает трейсы: сделать curl запрос который вызывает LLM; проверить `docker-compose logs langfuse` что нет ошибок; открыть Langfuse UI; убедить что трейс видна
- [ ] T043 [US3] Протестировать token counting: открыть Langfuse trace; убедить что input_tokens > 0, output_tokens > 0, cost_usd правильно вычислен (input_tokens * rate_in + output_tokens * rate_out) / 1000
- [x] T044 [US3] Протестировать graceful degradation: остановить Langfuse контейнер (`docker-compose stop langfuse`); сделать curl запрос который вызывает LLM; убедить что запрос успешен (200 OK, не 500); проверить `docker-compose logs web` что warning логирована о недоступности Langfuse

**Checkpoint**: User Story 3 полностью функциональна и независимо тестируема

---

## Phase 6: User Story 4 - DevOps Мониторит Очередь Celery (Priority: P2)

**Цель**: Flower UI показывает статус Celery workers, queue depth, task execution time, success/failure rates; DevOps может видеть очередь здоровье в реальном времени

**Независимый Тест**: Запустить docker-compose; открыть Flower UI (localhost:5555); убедить что Workers tab показывает active workers; enqueue Celery task; убедить что Tasks tab показывает task с правильным статусом (PENDING → STARTED → SUCCESS/FAILURE); убедить что Queue tab показывает queue depth

### Реализация для User Story 4

- [x] T045 [P] [US4] Убедить что docker-compose.yml имеет Flower service (из T008): image: mher/flower, environment: CELERY_BROKER_URL, CELERY_RESULT_BACKEND, port 5555 expose, depends_on redis
- [x] T046 [US4] Обновить `web/src/webx5/core/celery_app.py` (не требует изменений; проверить что config актуален): broker=REDIS_URL, backend=REDIS_URL, все task modules включены в include list
- [x] T047 [P] [US4] Добавить Celery event logging в services которые enqueue tasks: добавить structlog.get_logger().info() при enqueue задачи с task_name и task_id
- [x] T048 [P] [US4] Добавить Prometheus metrics для Celery в `web/src/webx5/utils/metrics.py` (из T013): CELERY_TASKS_PROCESSED (Counter с labels task_name, status), CELERY_TASK_DURATION (Histogram с label task_name), ACTIVE_CELERY_WORKERS (Gauge)
- [x] T049 [US4] Обновить Celery task decrators или task base class: добавить логирование и метрики incrementing при task start (procedure_state="started"), task success (procedure_state="completed", метрика status="success"), task failure (procedure_state="failed", метрика status="failed")
- [x] T050 [US4] Обновить `monitoring/grafana/dashboards/celery-queue.json` (из T020): убедить что все необходимые Prometheus queries добавлены для queue depth, worker status, execution time
- [x] T051 [US4] Протестировать Flower UI доступна: открыть http://localhost:5555; убедить что Workers tab видна с list active workers (count >= 1)
- [ ] T052 [US4] Протестировать task visibility: enqueue task через API или CLI; открыть Flower Tasks tab; убедить что task видна с статусом и execution time
- [x] T053 [US4] Протестировать metrics: запросить `curl http://localhost:8000/metrics | grep celery`; убедить что celery_tasks_processed и celery_task_duration metrics видны

**Checkpoint**: User Story 4 полностью функциональна и независимо тестируема

---

## Phase 7: Полировка & Кросс-функциональные Улучшения

**Цель**: Финальные улучшения, оптимизация и валидация всей инфраструктуры

- [ ] T054 [P] Обновить `web/README.md` или документацию: добавить инструкции как запустить observability стек, как открыть Grafana/Loki/Flower/Langfuse, какие дашборды доступны
- [x] T055 [P] Обновить `.env.example`: документировать все новые переменные окружения (LANGFUSE_API_KEY, LANGFUSE_SECRET_KEY, PROMETHEUS_MULTIPROC_DIR, etc.)
- [ ] T056 [P] Добавить unit tests для Langfuse wrapper в `web/tests/webx5/unit/test_langfuse_wrapper.py`: test что contextvars user_id правильно извлекается, test graceful degradation когда Langfuse SDK недоступен
- [ ] T057 [P] Добавить unit tests для metrics utils в `web/tests/webx5/unit/test_metrics.py`: test что все Counter, Histogram, Gauge инициализируются правильно, test что labels актуальны
- [ ] T058 Добавить integration test в `web/tests/webx5/integration/test_observability_e2e.py`: полный flow - сделать authenticated request → убедить что логи в Loki → убедить что метрики в Prometheus → убедить что traces в Langfuse (если LLM call)
- [ ] T059 Запустить `quickstart.md` валидацию: выполнить все 7 сценариев; записать результаты; убедить что нет failures
- [ ] T060 [P] Добавить pre-commit hook (если используется): lint/format для новых Python files (utils/metrics.py, utils/contextvars_utils.py, core/langfuse_client.py, middleware/request_context.py)
- [x] T061 Code cleanup: убедить что нет commented code, неиспользуемых imports, trailing whitespace в новых files
- [x] T062 Documentation: убедить что все новые классы/функции имеют docstrings (особенно Langfuse wrapper, metrics utilities, contextvars management)
- [x] T063 [P] Протестировать что все контейнеры Docker имеют healthchecks (prometheus, loki, grafana, flower, langfuse): `docker-compose ps` показывает (healthy) для всех
- [x] T064 Проверить что docker-compose.yml имеет correct depends_on и startup order: web и worker стартуют после db и redis; prometheus, loki scrape targets доступны; langfuse доступна для web если LANGFUSE_API_KEY set
- [x] T065 Final validation: запустить `docker-compose up -d`; проверить что все сервисы starten без ошибок; открыть все UIs (Grafana, Loki, Flower, Langfuse); убедить что все actuals work end-to-end

**Checkpoint**: Все пользовательские сценарии готовы; инфраструктура validation завершена

---

## Зависимости и Порядок Выполнения

### Зависимости Фаз

- **Setup (Phase 1)**: Нет зависимостей - может начаться немедленно
- **Foundational (Phase 2)**: Зависит от Setup completion - **БЛОКИРУЕТ** все пользовательские сценарии
- **User Stories (Phase 3-6)**: Все зависят от Foundational phase completion
  - US1, US2, US3 могут выполняться параллельно (если есть люди)
  - или последовательно в порядке приоритета (US1 → US2 → US3 → US4)
- **Polish (Phase 7)**: Зависит от завершения желаемых пользовательских сценариев

### Зависимости Пользовательских Сценариев

- **US1 (P1)**: Может начаться после Foundational - Нет зависимостей на другие сценарии
- **US2 (P1)**: Может начаться после Foundational - Может быть независим от US1, но могут интегрироваться
- **US3 (P1)**: Может начаться после Foundational - Может быть независим от US1/US2, но могут интегрироваться
- **US4 (P2)**: Может начаться после Foundational - Может быть независим от US1/US2/US3

### Параллельные Возможности

- Все Setup задачи помеченные [P] могут выполняться параллельно (разные files)
- Все Foundational задачи помеченные [P] могут выполняться параллельно
- После Foundational completion, все US1, US2, US3 могут стартовать параллельно (если team capacity позволяет)
- В каждом сценарии: models/configs помеченные [P] могут выполняться параллельно
- Разные пользовательские сценарии могут быть работаны разными разработчиками параллельно

### Параллельный Пример: US1

```bash
# Запустить все setup для US1 вместе (разные files):
T019: Создать api-health.json dashboard
T020: Создать celery-queue.json dashboard
T021: Создать llm-costs.json dashboard

# Эти могут паралеллизованы:
T023: Обновить datasources.yml
T024: Протестировать Prometheus endpoint
T025: Протестировать Grafana querying
```

---

## Стратегия Реализации

### MVP First (Только User Story 1)

1. Завершить Phase 1: Setup
2. Завершить Phase 2: Foundational (CRITICAL)
3. Завершить Phase 3: User Story 1
4. **STOP и ВАЛИДИРОВАТЬ**: Протестировать US1 независимо через quickstart.md сценарий 1
5. Deploy/demo если готово

**Timeline MVP**: ~3-4 дня (1 разработчик)

### Incremental Delivery

1. Setup + Foundational → Foundation ready (~2 дня)
2. Добавить US1 → Протестировать независимо → Deploy/Demo (MVP!) (~1 день)
3. Добавить US2 → Протестировать независимо → Deploy/Demo (~1 день)
4. Добавить US3 → Протестировать независимо → Deploy/Demo (~1 день)
5. Добавить US4 → Протестировать независимо → Deploy/Demo (~1 день)
6. Polish & validation (~1 день)

**Timeline Full**: ~7-8 дней (1 разработчик, sequential); ~4-5 дней (3 разработчика, parallel US1-3)

### Parallel Team Strategy

С несколькими разработчиками:

1. **День 1-2**: Все вместе завершают Setup + Foundational
2. **День 3-4** (Parallel):
   - Developer A: User Story 1 (Prometheus + Grafana dashboards)
   - Developer B: User Story 2 (Loki + structured logs)
   - Developer C: User Story 3 (Langfuse + LLM tracing)
3. **День 5**: Merge & integrate; US4 (Flower) - может быть одним из developers
4. **День 6**: Polish & validation; end-to-end testing

---

## Выход и Валидация

### Каждая Фаза
- [ ] All tasks в фазе отмечены как complete
- [ ] No git conflicts при merge
- [ ] `docker-compose up -d` успешно выполняется
- [ ] `docker-compose ps` показывает all services healthy

### Каждый Пользовательский Сценарий
- [ ] Independent test criteria passed (see Checkpoint для каждого US)
- [ ] Relevant quickstart.md scenarios passed (see scenario descriptions выше)
- [ ] No breaking changes to existing functionality
- [ ] Code review approved

### Final
- [ ] All 7 phases complete
- [ ] All tests passing (unit + integration)
- [ ] quickstart.md full validation suite passed
- [ ] Documentation updated
- [ ] Ready for production deployment

---

## Примечания

- [P] задачи = разные files, нет зависимостей на другие incomplete задачи
- [Story] label maps задача к specific пользовательскому сценарию
- Каждый пользовательский сценарий должен быть independently completable и testable
- Избегайте: vague задачи, conflicts на same файле, cross-story зависимости которые break independence
- Commit после каждой задачи или logical group
- Stop в любом Checkpoint для валидации story independently
