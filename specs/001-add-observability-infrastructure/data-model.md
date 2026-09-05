# Phase 1: Модель Данных

**Дата**: 2026-09-05  
**Статус**: Завершено

## Обзор

Инфраструктура observability оперирует четырьмя основными сущностями данных, каждая с собственной моделью хранилища:

1. **Log Entry** — структурированный лог от приложения (Loki)
2. **Metric** — временной ряд производительности (Prometheus)
3. **LLM Trace** — запись LLM API вызова (Langfuse/PostgreSQL)
4. **Celery Task** — история выполнения задачи (Flower/Redis/Backend DB)

---

## 1. Log Entry (Loki)

### Модель

```
LogEntry {
  timestamp: ISO8601        # 2026-09-05T12:34:56.789Z
  level: string             # "INFO", "WARNING", "ERROR"
  service_name: string      # "webx5", "webx5-worker", "webx5-beat"
  logger: string            # "app.routes.auth", "app.services.llm"
  message: string           # "challenge_generated", "request_received"
  
  # Mandatory Labels (queryable in Loki)
  user_id: string           # UUID, extracted from request context
  request_id: string        # Unique per HTTP request
  procedure_name: string    # "generate_challenge", "validate_receipt"
  procedure_state: string   # "started", "processing", "completed", "failed"
  
  # Contextual Fields
  duration_ms?: integer     # Time taken for step
  error_type?: string       # Exception type if level=ERROR
  error_message?: string    # Exception message
  stack_trace?: string      # Full traceback
  external_api?: string     # "openrouter", "stripe" if applicable
  tokens_used?: integer     # For LLM calls
}
```

### Validation Rules

- **timestamp** MUST be ISO8601; auto-added by structlog
- **level** MUST be one of: DEBUG, INFO, WARNING, ERROR, CRITICAL
- **service_name** MUST be exactly one of: "webx5", "webx5-worker", "webx5-beat"
- **user_id** MUST NOT be null for authenticated requests; OK to be null for public endpoints (e.g., /health)
- **request_id** MUST be generated per request; unique within 24-hour window
- **procedure_name** MUST match function/method name or explicit operation name
- **procedure_state** MUST follow state machine: started → processing → completed OR failed
- All fields MUST be JSON-serializable

### State Transitions

```
Log Entry Procedure State Machine:
┌─────────────┐
│   started   │  Operation begins
└──────┬──────┘
       │
       ▼
┌─────────────────┐
│  processing     │  In-flight; may have multiple entries
└──────┬──────────┘
       │
       ├──────────────────────┐
       │                      │
       ▼                      ▼
┌──────────────┐         ┌────────┐
│  completed   │         │ failed │  Terminal states
└──────────────┘         └────────┘
```

### Example Logs

```json
{
  "timestamp": "2026-09-05T12:34:56.123Z",
  "level": "INFO",
  "service_name": "webx5",
  "logger": "app.routes.challenges",
  "message": "challenge_generated",
  "user_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "request_id": "req-20260905-abc123",
  "procedure_name": "generate_challenge",
  "procedure_state": "completed",
  "duration_ms": 1250,
  "tokens_used": 450
}

{
  "timestamp": "2026-09-05T12:35:10.456Z",
  "level": "ERROR",
  "service_name": "webx5",
  "logger": "app.core.llm",
  "message": "openrouter_api_error",
  "user_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "request_id": "req-20260905-abc123",
  "procedure_name": "call_openrouter_tools",
  "procedure_state": "failed",
  "external_api": "openrouter",
  "error_type": "HTTPStatusError",
  "error_message": "429 Too Many Requests",
  "stack_trace": "..."
}
```

---

## 2. Metric (Prometheus)

### Модель

Метрики в Prometheus хранятся как временные ряды с labels (dimensions). Три типа метрик:

#### A. Standard HTTP Metrics

```
http_requests_total (Counter)
  Labels: method, endpoint, status
  Example: http_requests_total{method="POST", endpoint="/challenges", status="200"} 1234

http_request_duration_seconds (Histogram)
  Labels: method, endpoint
  Buckets: 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0
  Example: http_request_duration_seconds_bucket{le="0.1", method="GET", endpoint="/challenges"} 5623

http_errors_total (Counter)
  Labels: method, endpoint, error_type
  Example: http_errors_total{method="POST", endpoint="/receipts", error_type="ValidationError"} 42
```

#### B. Custom Application Metrics

```
celery_tasks_processed_total (Counter)
  Labels: task_name, status (success/failed)
  Example: celery_tasks_processed_total{task_name="receipt_processing", status="success"} 9821

celery_task_duration_seconds (Histogram)
  Labels: task_name
  Example: celery_task_duration_seconds_bucket{le="60", task_name="generate_challenge"} 450

llm_generation_success_total (Counter)
  Labels: model
  Example: llm_generation_success_total{model="anthropic/claude-haiku-4.5"} 1523

llm_generation_failed_total (Counter)
  Labels: model, error_type
  Example: llm_generation_failed_total{model="anthropic/claude-haiku-4.5", error_type="RateLimitError"} 5

basket_calculation_duration_seconds (Histogram)
  Labels: operation (add_item, remove_item, apply_discount)
  Example: basket_calculation_duration_seconds_bucket{le="0.1", operation="apply_discount"} 2341

active_celery_workers (Gauge)
  No labels
  Example: active_celery_workers 4
```

### Storage & Retention

- **Prometheus retention**: 30 days (default; configurable in prometheus.yml)
- **Scrape interval**: 15 seconds (standard)
- **Labels cardinality**: Avoid unbounded labels (e.g., user_id as label would explode series count)

---

## 3. LLM Trace (Langfuse/PostgreSQL)

### Модель

```sql
-- Conceptual schema (Langfuse handles internals)
CREATE TABLE llm_traces (
  id UUID PRIMARY KEY,
  user_id UUID NOT NULL,
  model VARCHAR(255),
  
  -- Tokens
  input_tokens INTEGER,
  output_tokens INTEGER,
  total_tokens INTEGER,
  
  -- Timing
  started_at TIMESTAMP,
  ended_at TIMESTAMP,
  latency_ms INTEGER,
  
  -- Costs
  cost_usd DECIMAL(10, 6),
  
  -- Status
  status VARCHAR(50), -- "success", "failed"
  error_type VARCHAR(255) NULL,
  error_message TEXT NULL,
  
  -- Context
  request_id VARCHAR(255),
  model_id VARCHAR(255),
  parameters JSONB,
  
  created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_user_id ON llm_traces(user_id);
CREATE INDEX idx_created_at ON llm_traces(created_at);
```

### Langfuse SDK Integration

```python
# core/llm.py
from langfuse import Langfuse

langfuse = Langfuse(
    api_key=os.getenv('LANGFUSE_API_KEY'),
    secret_key=os.getenv('LANGFUSE_SECRET_KEY'),  # optional
)

def call_openrouter_tools_traced(
    model: str,
    system: str,
    user: str,
    tools: list[dict],
    user_id: str = None,
) -> list[ToolCall]:
    user_id = user_id or user_id_context.get()
    
    with langfuse.trace(
        name="openrouter_completion",
        metadata={"user_id": user_id}
    ) as trace:
        start = time.time()
        
        # Call OpenRouter
        resp = httpx.post(...)
        resp.raise_for_status()
        data = resp.json()
        
        latency_ms = int((time.time() - start) * 1000)
        
        # Log to Langfuse
        trace.event(
            name="completion",
            input={
                "system": system,
                "user": user,
                "tools": tools,
            },
            output=data,
            metadata={
                "model": model,
                "latency_ms": latency_ms,
                "user_id": user_id,
            }
        )
        
        return parse_tool_calls(data)
```

### Example Trace

```json
{
  "id": "trace-uuid-123",
  "user_id": "user-456",
  "model": "anthropic/claude-haiku-4.5",
  "input_tokens": 250,
  "output_tokens": 150,
  "total_tokens": 400,
  "cost_usd": 0.000060,
  "started_at": "2026-09-05T12:34:56Z",
  "ended_at": "2026-09-05T12:35:01Z",
  "latency_ms": 4500,
  "status": "success",
  "request_id": "req-20260905-abc123"
}
```

---

## 4. Celery Task (Flower/Redis)

### Модель (Flower Events)

Flower не хранит задачи в БД; он reads events из Celery broker (Redis):

```
Task Event {
  uuid: string              # Task ID
  name: string              # "webx5.tasks.receipt.process_receipt"
  queue: string             # "receipts", "challenges"
  
  # State machine
  state: string             # "PENDING", "STARTED", "SUCCESS", "FAILURE"
  sent_at: datetime
  received_at: datetime
  started_at: datetime
  succeeded_at: datetime
  failed_at: datetime
  
  # Metadata
  args: array
  kwargs: dict
  result: any               # Return value or exception
  exception: string         # If failed
  traceback: string         # If failed
  
  # Execution
  worker: string            # Worker name that executed task
  retries: integer
  eta: datetime             # Estimated time of arrival (if scheduled)
  expires: datetime
  routing_key: string
}
```

### Display in Flower UI

Flower aggregates events и displays:
- **Tasks Tab**: All tasks (recent first) with status, execution time, worker
- **Workers Tab**: Active workers, status, task count, pool size
- **Queue Tab**: Queue depth per queue name
- **Graphs Tab**: Tasks/sec, failure rate, execution time histogram

### Storage Lifecycle

- **Live data**: Stored in Redis (broker)
- **Historical data**: Depends on `result_backend` config (Redis, DB, Disk)
- **Flower retention**: Default 24 hours; configurable

---

## Relationships

```
┌─────────────────────────────────────────────────────────┐
│ HTTP Request to API                                     │
│ GET /challenges?user_id=abc                             │
└────────────────────┬────────────────────────────────────┘
                     │
            ┌────────▼────────┐
            │ request_id gen  │
            │ user_id_context │
            └────────┬────────┘
                     │
        ┌────────────┴────────────┐
        │                         │
        ▼                         ▼
    ┌─────────┐          ┌──────────────┐
    │ Log     │          │ Prometheus   │
    │ Entry 1 │◄─────────┤ HTTP Metrics │
    │ (log)   │          │ (counter++)  │
    └────┬────┘          └──────────────┘
         │
         │ user_id context available
         │
         ▼
    ┌──────────────────┐
    │ Call LLM         │
    │ call_openrouter_ │
    │ tools_traced()   │
    └────┬─────────────┘
         │
      ┌──▼──────────────────┐
      │ LLM Trace (Langfuse)│
      │ - model             │
      │ - tokens            │
      │ - latency_ms        │
      │ - user_id           │
      │ - request_id        │
      └─────────────────────┘
         + Log Entry 2 (structured log of LLM call)

    ┌────────────────────┐
    │ Enqueue Celery     │
    │ Task               │
    └────┬───────────────┘
         │
      ┌──▼───────────────────┐
      │ Celery Task Event    │
      │ (in Flower/Redis)    │
      │ - name               │
      │ - state              │
      │ - worker             │
      └──────────────────────┘
         + Log Entry 3 (task started)
```

---

## Validation Constraints

### Log Entry
- ✅ All 5 labels present OR (user_id=null AND endpoint is public)
- ✅ procedure_state follows FSM
- ✅ timestamp is ISO8601

### Metric
- ✅ No unbounded label cardinality (don't include user_id as label)
- ✅ Histogram buckets cover 95% of expected latency range
- ✅ Counter values monotonically increase

### LLM Trace
- ✅ user_id NOT NULL (always extracted from context)
- ✅ cost_usd = (input_tokens * rate_per_1k_in + output_tokens * rate_per_1k_out) / 1000
- ✅ latency_ms > 0

### Celery Task
- ✅ state follows CELERY state machine
- ✅ timestamps ordered: sent < received < started < succeeded/failed

---

## Заключение

4 сущности данных покрывают полный жизненный цикл запроса:
1. **Logs** — судебно-следственные доказательства (что произошло)
2. **Metrics** — анализ тенденций (как часто, как быстро)
3. **LLM Traces** — атрибуция затрат (кто, что стоило)
4. **Celery Tasks** — мониторинг работы (очередь здорова)
