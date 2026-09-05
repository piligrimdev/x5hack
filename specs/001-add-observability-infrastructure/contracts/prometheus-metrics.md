# Prometheus Metrics Contract

**Версия**: 1.0  
**Дата**: 2026-09-05

## Обзор

Fastapi приложение экспортирует метрики на endpoint `/metrics` в Prometheus-совместимом формате (text/plain).

---

## Endpoint

```
GET /metrics
Accept: text/plain; version=0.0.4
```

**Response**: 200 OK  
**Content-Type**: `text/plain; charset=utf-8`

---

## Метрики: Standard HTTP

### http_requests_total (Counter)

**Формат**:
```
http_requests_total{method="METHOD",endpoint="/path",status="CODE"} COUNT
```

**Labels**:
- `method`: HTTP method (GET, POST, PUT, DELETE, PATCH)
- `endpoint`: Request path (e.g., `/challenges`, `/receipts`, `/auth/login`)
- `status`: HTTP status code (200, 400, 401, 404, 500, etc.)

**Пример**:
```
http_requests_total{method="GET",endpoint="/challenges",status="200"} 1234
http_requests_total{method="POST",endpoint="/receipts",status="201"} 456
http_requests_total{method="POST",endpoint="/challenges",status="500"} 12
```

**Validation**:
- Counter values MUST NOT decrease
- status MUST be 3-digit HTTP code
- endpoint MUST be normalized (no user IDs in path)

---

### http_request_duration_seconds (Histogram)

**Формат**:
```
http_request_duration_seconds_bucket{le="0.01",method="METHOD",endpoint="/path"} COUNT
http_request_duration_seconds_bucket{le="0.025",method="METHOD",endpoint="/path"} COUNT
...
http_request_duration_seconds_bucket{le="+Inf",method="METHOD",endpoint="/path"} COUNT
http_request_duration_seconds_sum{method="METHOD",endpoint="/path"} TOTAL_SECONDS
http_request_duration_seconds_count{method="METHOD",endpoint="/path"} COUNT
```

**Buckets**: 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, +Inf

**Labels**:
- `le` (bucket boundary, seconds)
- `method`
- `endpoint`

**Пример**:
```
http_request_duration_seconds_bucket{le="0.01",method="GET",endpoint="/challenges"} 543
http_request_duration_seconds_bucket{le="0.025",method="GET",endpoint="/challenges"} 890
http_request_duration_seconds_bucket{le="+Inf",method="GET",endpoint="/challenges"} 2341
http_request_duration_seconds_sum{method="GET",endpoint="/challenges"} 125.45
http_request_duration_seconds_count{method="GET",endpoint="/challenges"} 2341
```

**Validation**:
- `_sum` >= `_count` * `le` for all buckets
- `le` values MUST be in ascending order

---

### http_errors_total (Counter)

**Формат**:
```
http_errors_total{method="METHOD",endpoint="/path",error_type="TYPE"} COUNT
```

**Labels**:
- `method`
- `endpoint`
- `error_type`: Exception class name (ValidationError, NotFoundError, InternalError, RateLimitError)

**Пример**:
```
http_errors_total{method="POST",endpoint="/challenges",error_type="ValidationError"} 34
http_errors_total{method="GET",endpoint="/receipts",error_type="NotFoundError"} 8
http_errors_total{method="POST",endpoint="/auth/login",error_type="AuthenticationError"} 5
```

---

## Метрики: Custom Application

### celery_tasks_processed_total (Counter)

**Формат**:
```
celery_tasks_processed_total{task_name="NAME",status="STATUS"} COUNT
```

**Labels**:
- `task_name`: Celery task module path (e.g., `webx5.tasks.receipt.process_receipt`)
- `status`: "success" или "failed"

**Пример**:
```
celery_tasks_processed_total{task_name="webx5.tasks.receipt.process_receipt",status="success"} 9821
celery_tasks_processed_total{task_name="webx5.tasks.receipt.process_receipt",status="failed"} 45
celery_tasks_processed_total{task_name="webx5.tasks.generation.generate_challenge",status="success"} 3421
```

---

### celery_task_duration_seconds (Histogram)

**Формат**:
```
celery_task_duration_seconds_bucket{le="SECONDS",task_name="NAME"} COUNT
celery_task_duration_seconds_sum{task_name="NAME"} TOTAL_SECONDS
celery_task_duration_seconds_count{task_name="NAME"} COUNT
```

**Buckets**: 0.1, 0.5, 1.0, 5.0, 10.0, 30.0, 60.0, +Inf

**Пример**:
```
celery_task_duration_seconds_bucket{le="1.0",task_name="webx5.tasks.receipt.process_receipt"} 450
celery_task_duration_seconds_bucket{le="10.0",task_name="webx5.tasks.receipt.process_receipt"} 470
celery_task_duration_seconds_bucket{le="+Inf",task_name="webx5.tasks.receipt.process_receipt"} 475
celery_task_duration_seconds_sum{task_name="webx5.tasks.receipt.process_receipt"} 1234.56
celery_task_duration_seconds_count{task_name="webx5.tasks.receipt.process_receipt"} 475
```

---

### llm_generation_success_total (Counter)

**Формат**:
```
llm_generation_success_total{model="MODEL"} COUNT
```

**Labels**:
- `model`: LLM model name (e.g., `anthropic/claude-haiku-4.5`)

**Пример**:
```
llm_generation_success_total{model="anthropic/claude-haiku-4.5"} 1523
```

---

### llm_generation_failed_total (Counter)

**Формат**:
```
llm_generation_failed_total{model="MODEL",error_type="TYPE"} COUNT
```

**Labels**:
- `model`
- `error_type`: HTTP status or error type (e.g., `429`, `500`, `HTTPStatusError`, `TimeoutError`)

**Пример**:
```
llm_generation_failed_total{model="anthropic/claude-haiku-4.5",error_type="429"} 5
llm_generation_failed_total{model="anthropic/claude-haiku-4.5",error_type="TimeoutError"} 2
```

---

### basket_calculation_duration_seconds (Histogram)

**Формат**:
```
basket_calculation_duration_seconds_bucket{le="SECONDS",operation="OP"} COUNT
basket_calculation_duration_seconds_sum{operation="OP"} TOTAL_SECONDS
basket_calculation_duration_seconds_count{operation="OP"} COUNT
```

**Labels**:
- `operation`: "add_item", "remove_item", "apply_discount", "checkout"

**Buckets**: 0.01, 0.05, 0.1, 0.25, +Inf

**Пример**:
```
basket_calculation_duration_seconds_bucket{le="0.1",operation="apply_discount"} 2341
basket_calculation_duration_seconds_bucket{le="+Inf",operation="apply_discount"} 2350
basket_calculation_duration_seconds_sum{operation="apply_discount"} 45.67
basket_calculation_duration_seconds_count{operation="apply_discount"} 2350
```

---

### active_celery_workers (Gauge)

**Формат**:
```
active_celery_workers WORKER_COUNT
```

**Пример**:
```
active_celery_workers 4
```

**Validation**:
- Value MUST be >= 0

---

## Scrape Configuration (Prometheus)

```yaml
scrape_configs:
  - job_name: 'webx5-api'
    static_configs:
      - targets: ['localhost:8000']
    metrics_path: '/metrics'
    scrape_interval: 15s
    scrape_timeout: 10s
```

---

## Querying Examples (PromQL)

```promql
# Average request latency in last 5 minutes
rate(http_request_duration_seconds_sum[5m]) / rate(http_request_duration_seconds_count[5m])

# Error rate per endpoint
rate(http_errors_total[5m]) / rate(http_requests_total[5m])

# Celery task success rate
rate(celery_tasks_processed_total{status="success"}[5m]) / 
  (rate(celery_tasks_processed_total{status="success"}[5m]) + 
   rate(celery_tasks_processed_total{status="failed"}[5m]))

# P95 basket calculation latency
histogram_quantile(0.95, rate(basket_calculation_duration_seconds_bucket[5m]))
```

---

## Validation Checklist

- [ ] `/metrics` endpoint returns 200 OK
- [ ] Content-Type is `text/plain`
- [ ] All metrics follow Prometheus naming convention (snake_case, _total suffix for counters)
- [ ] No user IDs in labels
- [ ] Counter values never decrease
- [ ] Histogram bucket boundaries are in ascending order
- [ ] All required metrics present in output
