# План Реализации: Инфраструктура Наблюдаемости и Мониторинга

**Ветка**: `001-add-observability-infrastructure` | **Дата**: 2026-09-05 | **Спеска**: [spec.md](spec.md)

**Исходные Данные**: Спецификация функции из `/specs/001-add-observability-infrastructure/spec.md`

**Примечание**: Этот план заполняется командой `/speckit-plan` и описывает рабочий поток реализации.

## Резюме

Добавить полный стек observability-инструментов для мониторинга здоровья приложения:
- **Логирование**: Promtail → Loki (структурированные логи с 5 обязательными labels)
- **Метрики**: Prometheus (стандартные HTTP + custom application метрики) → Grafana (3 отдельных дашборда)
- **LLM Трейсы**: Langfuse (self-hosted) для отслеживания OpenRouter вызовов с атрибуцией по пользователю
- **Задачи Celery**: Flower UI для мониторинга очереди и worker статуса

## Технический Контекст

**Язык/Версия**: Python 3.12 (FastAPI backend) + Docker Compose

**Основные Зависимости**:
- FastAPI (существующий), structlog (существующий)
- `prometheus-client` >=0.19.0 (новая)
- `langfuse` >=2.0.0 (новая)
- `flower` >=2.0.0 (новая)
- Контейнеры: Prometheus, Grafana, Loki, Promtail, Langfuse (PostgreSQL + vector DB)

**Хранилище**: PostgreSQL (для Langfuse), Redis (существующий для Celery)

**Тестирование**: pytest для unit-тестов обёрток Langfuse; docker-compose для e2e валидации

**Целевая Платформа**: Linux (Docker контейнеры для локального dev и integration тестирования)

**Тип Проекта**: Web-service + Monitoring stack integration

**Целевые Производительности**:
- Логи в Loki <5 секунд
- LLM трейсы в Langfuse <2 секунды  
- Обновление метрик Prometheus <10 секунд
- Дашборды Grafana refreshed <10 секунд

**Ограничения**:
- Graceful degradation если Langfuse API недоступен
- Обратная совместимость с существующей structlog конфигурацией
- Нет breaking changes в API

**Масштаб/Область**: PoC/Development фаза; retention policy и alerting - out of scope для v1

## Проверка Конституции

*GATE: Должен пройти перед Phase 0 research. Переproверить после Phase 1 design.*

✅ **Принцип I — Экономия как единая видимая метрика**: N/A (этот фича про инфраструктуру, не про продукт)

✅ **Принцип II — Минимальный когнитивный барьер**: N/A (для DevOps/ML инженеров, не для конечных пользователей)

✅ **Принцип III — ИИ-персонализация**: N/A (эта фича создает preconditions для мониторинга, не для персонализации)

✅ **Принцип IV — Экономическая обоснованность**: Observability infrastructure снижает стоимость операций через раннее обнаружение проблем и cost attribution LLM вызовов

✅ **Принцип V — Privacy by Design**: Структурированные логи содержат service_name, user_id (анонимизированный), request_id — не содержат ФИО, адреса, номера телефонов

✅ **Backend Technical Standards — RSI архитектура**: Observability инструменты не изменяют основную архитектуру Repository-Service-Interface; добавляют только instrumentation middleware и обёртки

✅ **Контролируемая инициализация**: Все сервисы (Prometheus middleware, Langfuse SDK, Promtail config) инициализируются в `main.py` и `core/` modules, не на уровне импорта

✅ **Зависимости через Poetry**: Все новые Python зависимости в `web/pyproject.toml`; Docker сервисы в `docker-compose.yml`

**Статус**: ✅ GATE PASSED

## Структура Проекта

### Документация (эта фича)

```text
specs/001-add-observability-infrastructure/
├── plan.md                    # Этот файл (output команды /speckit-plan)
├── research.md                # Phase 0 output (output команды /speckit-plan)
├── data-model.md              # Phase 1 output (output команды /speckit-plan)
├── quickstart.md              # Phase 1 output (output команды /speckit-plan)
├── contracts/                 # Phase 1 output (output команды /speckit-plan)
│   ├── prometheus-metrics.md  # Prometheus metric contracts
│   ├── loki-logs.md           # Loki log format contracts
│   └── langfuse-traces.md     # Langfuse trace contracts
└── tasks.md                   # Phase 2 output (команда /speckit-tasks - НЕ создается /speckit-plan)
```

### Исходный код (корень репозитория)

**Backend (Python/FastAPI)**:
```text
web/
├── src/webx5/
│   ├── core/
│   │   ├── logging_config.py    # ✏️ Обновить: добавить labels в structlog
│   │   ├── server.py             # ✏️ Обновить: добавить PrometheusMiddleware
│   │   ├── llm.py                # ✏️ Обновить: обернуть в Langfuse SDK
│   │   └── celery_app.py         # Существующий, не требует изменений
│   ├── routes/
│   │   └── [...existing...]      # Добавить контекст пользователя для LLM трейсов
│   ├── services/
│   │   └── [...existing...]      # Добавить экспорт custom метрик
│   └── utils/
│       └── metrics.py             # ✨ Новое: helpers для custom metrics
│
├── pyproject.toml               # ✏️ Обновить: добавить prometheus-client, langfuse, flower
└── docker-compose.yml           # ✏️ Обновить: добавить Prometheus, Loki, Promtail, Grafana, Flower, Langfuse

tests/
└── webx5/
    ├── unit/
    │   └── test_langfuse_wrapper.py  # ✨ Новое: unit-тесты Langfuse обёртки
    └── integration/
        └── test_observability_e2e.py  # ✨ Новое: e2e-тесты стека observability
```

**Конфигурационные файлы мониторинга**:
```text
monitoring/
├── prometheus/
│   └── prometheus.yml           # ✨ Новое: конфиг Prometheus (targets: web:8000/metrics)
├── loki/
│   └── loki-config.yml          # ✨ Новое: конфиг Loki (storage backend)
├── promtail/
│   └── promtail-config.yml      # ✨ Новое: конфиг Promtail (Docker log collection)
├── grafana/
│   ├── dashboards/
│   │   ├── api-health.json      # ✨ Новое: Grafana dashboard (API Health & Performance)
│   │   ├── celery-queue.json    # ✨ Новое: Grafana dashboard (Celery Task Queue)
│   │   └── llm-costs.json       # ✨ Новое: Grafana dashboard (LLM Usage & Costs)
│   └── datasources.yml          # ✨ Новое: Prometheus + Loki datasources
└── langfuse/
    └── docker-compose-override.yml  # ✨ Новое: Langfuse service config (self-hosted)
```
```

**Structure Decision**: [Document the selected structure and reference the real
directories captured above]

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| Self-hosted Langfuse | Data locality + iteration speed for PoC | Cloud SaaS adds external dependency; complicates local testing |

---

## Phase 0: Исследование ✅ ЗАВЕРШЕНО

**Создано**: research.md

**Разрешены все технические неоднозначности**:
- Prometheus metrics collection via middleware
- Loki log aggregation via Promtail (stdout scraping)
- Langfuse SDK wrapper pattern with graceful degradation
- Flower standalone service for Celery monitoring
- Context propagation using contextvars (existing structlog pattern)

**Выход**: Все decisions обоснованы; альтернативы рассмотрены

---

## Phase 1: Дизайн ✅ ЗАВЕРШЕНО

**Создано 5 артефактов**:

### 1. data-model.md
Полная модель данных для 4 сущностей:
- **Log Entry** (Loki): JSON с 5 обязательными labels + optional fields
- **Metric** (Prometheus): 3 standard HTTP + 6 custom application metrics
- **LLM Trace** (Langfuse): Tokens, latency, cost, user attribution, state machine
- **Celery Task** (Flower): Event lifecycle, display format, storage

Включает: state machines, validation rules, relationships, lifecycle

### 2. contracts/prometheus-metrics.md
Prometheus API контракт:
- Endpoint: GET /metrics
- Format: Prometheus text format (text/plain)
- Metrics: 9 total (3 standard HTTP + 6 custom)
- Labels: method, endpoint, status, task_name, model, operation
- PromQL examples, scrape config, validation

### 3. contracts/loki-logs.md
Loki JSON log format contract:
- Format: Single-line JSON per log
- Mandatory fields: 5 (timestamp, level, service_name, logger, message)
- Mandatory labels: 5 (user_id, request_id, procedure_name, procedure_state, + context)
- Optional fields: 6 (duration_ms, error_type, error_message, stack_trace, external_api, tokens_used)
- LogQL examples, extraction rules, validation

### 4. contracts/langfuse-traces.md
Langfuse LLM trace contract:
- SDK integration pattern with minimal overhead
- Trace schema: 15+ fields (id, user_id, model, tokens, latency, cost, status)
- Graceful degradation if API unavailable
- Cost calculation formula
- Query examples, retention, privacy

### 5. quickstart.md
End-to-end валидация guide:
- 7 сценариев: Prometheus, Loki, Langfuse, Grafana, Flower, graceful degradation, e2e
- Step-by-step setup, curl примеры, troubleshooting
- Success criteria checklist
- Test data generation

**Выход**: Все компоненты дизайна defined; ready for implementation

---

## Re-Validation: Constitution Check (Post-Design)

✅ **ALL PRINCIPLES STILL SATISFIED**

- **Principle I** (Экономия): Observability снижает operational costs через early bug detection
- **Principle II** (Cognitive Barrier): 3 dashboards per-role; clean UX; not overwhelming
- **Principle III** (AI Personalization): Creates preconditions for user-specific model tracking
- **Principle IV** (Economic Viability): LLM cost attribution enables accurate P&L
- **Principle V** (Privacy by Design): No PII; only anon UUIDs; proper label strategy

Backend Standards:
- ✅ RSI unaffected; only middleware + instrumentation wrappers added
- ✅ All dependencies via Poetry (prometheus-client, langfuse, flower)
- ✅ Initialization controlled in main.py and core/ (no module-level side effects)
- ✅ Structured logging already integrated (structlog baseline)

**GATE STATUS: ✅ PASSED (DESIGN PHASE)**

---

## Next: Phase 2 — Implementation Tasks

Next command: `/speckit-tasks`

Phase 2 will generate detailed implementation plan (tasks.md) with:
- Code modifications (logging_config.py, server.py, llm.py, celery_app.py)
- New files (prometheus config, Grafana dashboards, docker-compose updates)
- Unit tests (Langfuse wrapper, context propagation)
- Integration tests (e2e observability)
- Deployment steps

Expected complexity: ~20-25 tasks, 3-4 week implementation sprint
