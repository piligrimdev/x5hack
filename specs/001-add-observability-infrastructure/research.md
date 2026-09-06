# Phase 0: Исследование и Разрешение Неоднозначностей

**Дата**: 2026-09-05  
**Статус**: Завершено

## Разрешённые Уточнения

Все критические неоднозначности разрешены в `/speckit-clarify`:

| # | Вопрос | Решение | Обоснование |
|----|--------|--------|-------------|
| 1 | Модель развертывания Langfuse? | Self-hosted в docker-compose | PoC фаза; local data; faster iteration |
| 2 | Обязательные labels логов? | service_name, user_id, request_id, procedure_name, procedure_state | Поддержка фильтрации, трейсинга, состояния процедур |
| 3 | Prometheus метрики? | Standard HTTP + custom application | Полная видимость (инфра + бизнес-логика) |
| 4 | Дизайн дашбордов? | 3 отдельных дашборда | Per-role focus; easier navigation; cleaner UX |
| 5 | User context для LLM? | Extract из request context via contextvars | Leverages existing structlog pattern; minimal overhead |

## Техники Интеграции: Лучшие Практики

### 1. Prometheus Metrics в FastAPI

**Выбранный Подход**: `prometheus_client` middleware + custom metric decorators

**Почему**: 
- Standard library для Python
- Интегрируется через FastAPI middleware (minimal overhead)
- Supports custom metrics via Gauge, Counter, Histogram
- Already used in production by many FastAPI apps

**Альтернативы рассмотрены**:
- StatsD + Telegraf: overkill для PoC, требует additional service
- OpenMetrics SDK: более сложный setup

**Реализация**:
```python
# Prometheus middleware в core/server.py
from prometheus_client import Counter, Histogram
from prometheus_client.middleware import DispatcherMiddleware
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

# Standard HTTP metrics (auto from middleware)
REQUEST_COUNT = Counter(
    'http_requests_total',
    'Total HTTP requests',
    ['method', 'endpoint', 'status']
)

REQUEST_LATENCY = Histogram(
    'http_request_duration_seconds',
    'HTTP request latency',
    ['method', 'endpoint'],
    buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0]
)

# Custom application metrics
CELERY_TASKS_PROCESSED = Counter(...)
LLM_MODEL_GENERATION_SUCCESS = Counter(...)
BASKET_CALCULATION_TIME = Histogram(...)
```

---

### 2. Structured Logs → Loki via Promtail

**Выбранный Подход**: Promtail читает logs из container stdout

**Почему**:
- Structlog уже настроен с JSON output для prod
- Promtail scrapes container logs (stdout)
- Zero changes в app code
- Loki parses JSON и автоматически создает labels

**Альтернативы рассмотрены**:
- Loki Python SDK (direct push): требует хост:port в env vars; более сложная обработка ошибок
- Filebeat: более heavy-weight, требует file monitoring

**Реализация**:
```yaml
# promtail-config.yml
scrape_configs:
  - job_name: docker
    static_configs:
      - targets:
          - localhost
        labels:
          job: docker
          __path__: /var/lib/docker/containers/*/*-json.log
    pipeline_stages:
      - json:
          expressions:
            message: message
            service_name: service_name
            user_id: user_id
            request_id: request_id
            procedure_name: procedure_name
            procedure_state: procedure_state
```

---

### 3. Langfuse SDK для LLM Трейсинга

**Выбранный Подход**: Wrap `call_openrouter_tools()` с Langfuse trace context

**Почему**:
- Single entry point для всех LLM вызовов (легко обернуть)
- Langfuse SDK handles retries + offline mode
- User context через contextvars (shared с structlog)
- Automatic cost calculation из token counts

**Альтернативы рассмотрены**:
- Custom logging to CSV: not scalable, no cost attribution
- OpenTelemetry: overkill для LLM-specific tracing

**Реализация**:
```python
# core/llm.py с Langfuse трейсингом
from langfuse import Langfuse
from contextvars import ContextVar

user_id_context: ContextVar[str] = ContextVar('user_id', default=None)

langfuse_client = Langfuse(api_key=os.getenv('LANGFUSE_API_KEY'))

def call_openrouter_tools_traced(...) -> list[ToolCall]:
    user_id = user_id_context.get()
    
    with langfuse_client.trace(
        name="openrouter_tool_call",
        metadata={"user_id": user_id, "model": model}
    ) as trace:
        # существующий вызов
        result = call_openrouter_tools(...)
        
        # Langfuse автоматически отслеживает tokens и latency
        return result
```

---

### 4. Flower для Celery Мониторинга

**Выбранный Подход**: Standalone Flower сервис в docker-compose

**Почему**:
- Connects к existing Redis broker (no code changes)
- Real-time task monitoring + historical stats
- Web UI доступен на localhost:5555
- Lightweight, minimal resource overhead

**Альтернативы рассмотрены**:
- Celery events logging to file: not real-time, no UI
- Prometheus exporter для Celery: requires additional exporter setup

**Реализация**:
```yaml
# docker-compose.yml
flower:
  image: mher/flower:latest
  environment:
    CELERY_BROKER_URL: redis://redis:6379/0
    CELERY_RESULT_BACKEND: redis://redis:6379/0
  ports:
    - "5555:5555"
  depends_on:
    - redis
```

---

### 5. Grafana Dashboards: 3-Dashboard Strategy

**Выбранный Подход**: Отдельные dashboards для каждой role

**Почему**:
- DevOps dashboard: API Health + Celery Queue (операционная видимость)
- ML Engineer dashboard: LLM Usage & Costs (бизнес-интеллект)
- Не перегруженные UI; легче диагностировать
- Easy to share/customize per team

**Dashboard 1: API Health & Performance**
```
- Latency heatmap (p50, p95, p99)
- Error rate by endpoint
- Request count by method/endpoint
- Active connections
- Pod/container resource usage (if k8s; skipped for docker-compose)
```

**Dashboard 2: Celery Task Queue**
```
- Queue depth by queue name
- Active workers + status
- Task execution time histogram
- Success vs failure rates
- Slow tasks (outliers)
```

**Dashboard 3: LLM Usage & Costs**
```
- Total tokens per user (line chart over time)
- Total cost per user (table)
- Model distribution (pie chart)
- Cost per day (bar chart)
- Requests per user (ranked table)
```

---

## Интеграция Точек Соприкосновения: Детальные Паттерны

### A. Context Propagation для User ID

**Проблема**: LLM вызовы происходят в разных слоях (routes, services, tasks); как передать user_id?

**Решение**: Используй `contextvars` (уже in use by structlog)

```python
# In dependencies/auth.py
from contextvars import ContextVar

user_id_context: ContextVar[str] = ContextVar('user_id', default=None)

async def get_current_user(token: str = ...) -> User:
    user = await auth_service.verify_token(token)
    user_id_context.set(str(user.id))  # Set for downstream code
    return user

# In core/llm.py
def call_openrouter_tools_traced(...):
    user_id = user_id_context.get()
    langfuse_trace.metadata["user_id"] = user_id
    return call_openrouter_tools(...)
```

---

### B. Graceful Degradation если Langfuse недоступен

**Проблема**: Если Langfuse API down, приложение должно продолжать работать

**Решение**: Try-catch в trace wrapper; fallback to logging

```python
def call_openrouter_tools_traced(...):
    try:
        with langfuse_client.trace(...):
            return call_openrouter_tools(...)
    except Exception as e:
        structlog.get_logger().warning(
            "langfuse_unavailable",
            error=str(e),
            user_id=user_id_context.get()
        )
        # Fallback: normal execution
        return call_openrouter_tools(...)
```

---

### C. Custom Metrics Exporters

**Проблема**: Как экспортировать task counts, model success rate, basket calc time?

**Решение**: Decorators + Prometheus Gauge updates

```python
# services/challenge.py
from prometheus_client import Counter, Histogram

LLM_GENERATION_SUCCESS = Counter(
    'llm_challenge_generation_success_total',
    'Successful LLM challenge generations',
    ['model']
)

LLM_GENERATION_FAILED = Counter(
    'llm_challenge_generation_failed_total',
    'Failed LLM challenge generations',
    ['model', 'error_type']
)

def generate_challenge(user_id: str, ...):
    try:
        challenge = call_openrouter_tools(...)
        LLM_GENERATION_SUCCESS.labels(model=model).inc()
        return challenge
    except Exception as e:
        LLM_GENERATION_FAILED.labels(
            model=model,
            error_type=type(e).__name__
        ).inc()
        raise
```

---

## Рекомендации для Phase 1 Дизайна

1. **Structlog Integration**: Убедитесь что все 5 labels (`service_name`, `user_id`, `request_id`, `procedure_name`, `procedure_state`) всегда присутствуют в logs

2. **Prometheus Endpoint**: Expose `/metrics` endpoint в FastAPI (не в main routes; используй separate app или middleware)

3. **Langfuse SDK Initialization**: Initialize в `main.py` с graceful handling missing API key

4. **Docker Volume Mounts**:
   - Promtail needs access к container logs
   - Grafana needs persistent volume для dashboards
   - Loki needs persistent volume для logs

5. **Environment Variables**: Документировать все новые env vars (`LANGFUSE_API_KEY`, `PROMETHEUS_MULTIPROC_DIR`, etc.)

---

## Заключение

✅ Все technical decisions resolved. Ready for Phase 1 design (data model, contracts, quickstart).
