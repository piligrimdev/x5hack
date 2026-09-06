# Quickstart: Validating Observability Infrastructure

**Дата**: 2026-09-05  
**Назначение**: Пошаговая валидация что инфраструктура observability полностью интегрирована и работает

---

## Prerequisites

- Docker & Docker Compose installed
- Python 3.12 environment with web/ dependencies installed
- Terminal with curl, jq (for JSON parsing)
- Access to OpenRouter API key (set in `.env`)

---

## Setup: Start the Stack

### 1. Update docker-compose.yml

```bash
cd /Users/pgdev/x5hack
```

Ensure docker-compose.yml contains all monitoring services:
- `prometheus`
- `loki`
- `promtail`
- `grafana`
- `flower`
- `langfuse` (with PostgreSQL)

### 2. Start Services

```bash
docker-compose up -d
```

Verify services are running:
```bash
docker-compose ps
```

Expected output:
```
NAME                COMMAND             STATUS
web                 python -m uvicorn   Up (healthy)
worker              celery -A webx5     Up
beat                celery -A webx5     Up
db                  postgres            Up (healthy)
redis               redis-cli ping      Up (healthy)
prometheus          /bin/prometheus     Up
loki                loki -config        Up
promtail            -config.file        Up
grafana             /run.sh             Up
flower              celery -A webx5     Up
langfuse            python -m langfuse  Up
```

---

## Validation Scenarios

### Scenario 1: Prometheus Metrics Endpoint

**Goal**: Verify that `/metrics` endpoint exports Prometheus metrics

**Steps**:

```bash
# 1. Check that metrics endpoint is accessible
curl http://localhost:8000/metrics 2>/dev/null | head -20

# Expected output: Multiple lines starting with #
# HELP http_requests_total ...
# TYPE http_requests_total counter
# http_requests_total{...} N
```

**Validation**:
- [ ] HTTP 200 response
- [ ] Content-Type: text/plain
- [ ] At least 20+ lines of output
- [ ] Metrics include:
  - [ ] `http_requests_total`
  - [ ] `http_request_duration_seconds`
  - [ ] `active_celery_workers`

---

### Scenario 2: Structured Logs in Loki

**Goal**: Verify that logs are collected in Loki with mandatory labels

**Steps**:

```bash
# 1. Make a request to generate logs
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"phone_number":"+79991234567","password":"test"}' 2>/dev/null

# 2. Query Loki for recent logs
curl -s http://localhost:3100/loki/api/v1/query \
  --data-urlencode 'query={service_name="webx5"}' | jq '.data.result[0].values' | tail -5

# Expected output: Recent log entries
```

**Validation**:
- [ ] Logs appear in Loki within 5 seconds
- [ ] Each log contains mandatory labels:
  - [ ] `service_name`
  - [ ] `user_id` (or null for public endpoints)
  - [ ] `request_id`
  - [ ] `procedure_name`
  - [ ] `procedure_state`

**Query Examples in Grafana**:

```logql
# All logs from API
{service_name="webx5"}

# Errors only
{service_name="webx5", level="ERROR"}

# Logs for specific user (if authenticated)
{service_name="webx5", user_id="<user-uuid>"}
```

---

### Scenario 3: LLM Traces in Langfuse

**Goal**: Verify that OpenRouter calls are traced with user_id and token counts

**Steps**:

```bash
# 1. Trigger an LLM call via generate challenge endpoint
# (requires valid user_id and auth token)

curl -X POST http://localhost:8000/challenges/generate \
  -H "Authorization: Bearer <auth_token>" \
  -H "Content-Type: application/json" \
  -d '{"user_id":"<user-uuid>","preferences":{"category":"food"}}' 2>/dev/null

# 2. Check Langfuse dashboard
# Navigate to: http://localhost:3000 (Langfuse)
# (if self-hosted; or langfuse.com if cloud)

# Or query API:
curl -s http://localhost:3000/api/traces?user_id=<user-uuid> | jq '.traces | length'

# Expected: At least 1 trace
```

**Validation**:
- [ ] Langfuse shows LLM trace within 2 seconds
- [ ] Trace contains:
  - [ ] `user_id` (not null)
  - [ ] `model` (e.g., "anthropic/claude-haiku-4.5")
  - [ ] `input_tokens` (>0)
  - [ ] `output_tokens` (>0)
  - [ ] `latency_ms` (>0)
  - [ ] `cost_usd` (calculated automatically)
  - [ ] `status` (success or error)

---

### Scenario 4: Grafana Dashboards

**Goal**: Verify that 3 dashboards display metrics and logs

**Steps**:

```bash
# 1. Open Grafana
# Navigate to: http://localhost:3000
# Default credentials: admin / admin (change on first login)

# 2. Check dashboards
# Dashboard → Search → "API Health"
# Dashboard → Search → "Celery Task Queue"
# Dashboard → Search → "LLM Usage & Costs"
```

**Validation**:

**Dashboard 1: API Health & Performance**
- [ ] Metric: HTTP latency histogram visible
- [ ] Metric: Error rate by endpoint visible
- [ ] Metric: Request count by method visible
- [ ] Loki logs: Error traces searchable by user_id

**Dashboard 2: Celery Task Queue**
- [ ] Flower integration shows queue depth
- [ ] Active worker count displayed
- [ ] Task execution time histogram visible
- [ ] Success vs failure rate visible

**Dashboard 3: LLM Usage & Costs**
- [ ] Total tokens per user visible (table)
- [ ] Total cost per user visible (table)
- [ ] Cost over time visible (line chart)
- [ ] Model distribution visible (pie chart)

---

### Scenario 5: Flower UI for Celery

**Goal**: Verify Flower shows task queue and worker status

**Steps**:

```bash
# 1. Open Flower
# Navigate to: http://localhost:5555

# 2. Enqueue a test task (via API or direct call)
curl -X POST http://localhost:8000/receipts/process \
  -H "Authorization: Bearer <auth_token>" \
  -H "Content-Type: application/json" \
  -d '{"receipt_data":{...}}' 2>/dev/null

# 3. Check Flower UI
# Tasks tab: Should show the new task
# Workers tab: Should show active worker(s)
# Graphs: Should show task/sec metric
```

**Validation**:
- [ ] Flower UI accessible at port 5555
- [ ] Workers tab shows active workers (count >= 1)
- [ ] Tasks tab shows recent task executions
- [ ] Task status reflects actual task state (PENDING → STARTED → SUCCESS/FAILURE)
- [ ] Queue depth displayed for each queue

---

### Scenario 6: Graceful Degradation (Langfuse Unavailable)

**Goal**: Verify that app continues working if Langfuse is unavailable

**Steps**:

```bash
# 1. Stop Langfuse
docker-compose stop langfuse

# 2. Make LLM call (should still succeed)
curl -X POST http://localhost:8000/challenges/generate \
  -H "Authorization: Bearer <auth_token>" \
  -H "Content-Type: application/json" \
  -d '{"user_id":"<user-uuid>","preferences":{...}}' 2>/dev/null

# Expected: 200 OK (not 500 error)

# 3. Check logs for fallback warning
docker-compose logs web | grep langfuse_trace_failed

# Expected: Warning logged to structlog

# 4. Restart Langfuse
docker-compose start langfuse

# Wait 10s, then repeat LLM call
# Traces should appear in Langfuse again
```

**Validation**:
- [ ] App does NOT crash when Langfuse unavailable
- [ ] Request completes successfully (200 OK)
- [ ] Warning logged to structlog
- [ ] After Langfuse restarts, traces resume normally

---

### Scenario 7: End-to-End User Request Tracing

**Goal**: Verify complete observability flow for single user request

**Steps**:

```bash
# 1. Pick a user UUID and request ID
USER_UUID="f47ac10b-58cc-4372-a567-0e02b2c3d479"
REQUEST_ID="req-e2e-test-$(date +%s)"

# 2. Make authenticated API request
curl -X POST http://localhost:8000/challenges/generate \
  -H "Authorization: Bearer <auth_token>" \
  -H "Content-Type: application/json" \
  -d "{\"user_id\":\"$USER_UUID\",\"preferences\":{...}}" 2>/dev/null

# 3. Verify in Loki: logs contain request_id and user_id
curl -s http://localhost:3100/loki/api/v1/query \
  --data-urlencode "query={user_id=\"$USER_UUID\"}" | jq '.data.result'

# 4. Verify in Langfuse: trace exists for user
curl -s "http://localhost:3000/api/traces?user_id=$USER_UUID" | jq '.traces[-1]'

# 5. Verify in Prometheus: metrics incremented
curl -s http://localhost:8000/metrics | grep 'http_requests_total{.*endpoint="/challenges"' | head -1

# 6. Verify in Grafana: all dashboards updated
# Navigate to each dashboard and check timestamps are recent
```

**Validation**:
- [ ] Loki contains >= 3 log entries for user (request start, procedure processing, LLM call)
- [ ] Langfuse contains >= 1 trace for user
- [ ] Prometheus counters incremented (http_requests_total > 0)
- [ ] Grafana dashboards show recent activity (last 5 minutes)

---

## Test Data Generation

To populate observability data for testing:

```bash
# 1. Generate multiple requests
for i in {1..5}; do
  curl -X POST http://localhost:8000/challenges/generate \
    -H "Authorization: Bearer <token>" \
    -H "Content-Type: application/json" \
    -d "{\"user_id\":\"<user-id>\"}" 2>/dev/null
  sleep 1
done

# 2. Trigger worker tasks
curl -X POST http://localhost:8000/receipts/bulk-process \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d "{\"count\":10}" 2>/dev/null

# 3. Wait for propagation (5-10 seconds)
sleep 10

# 4. Check dashboards are populated
# Grafana, Flower, Langfuse should show data
```

---

## Troubleshooting

### Prometheus metrics not appearing
- [ ] Check `/metrics` endpoint is exposing metrics
- [ ] Verify Prometheus config points to `http://web:8000/metrics`
- [ ] Check Prometheus scrape logs: `docker-compose logs prometheus | grep -i error`

### Logs not in Loki
- [ ] Verify app is emitting JSON logs to stdout
- [ ] Check Promtail config: `docker-compose logs promtail | grep -i error`
- [ ] Verify Loki is running: `curl http://localhost:3100/loki/api/v1/status`

### Langfuse traces missing
- [ ] Check Langfuse is running: `docker-compose logs langfuse | tail -20`
- [ ] Verify LANGFUSE_API_KEY is set in .env
- [ ] Check app logs for "langfuse_unavailable" warnings
- [ ] Verify network connectivity between web and langfuse containers

### Grafana dashboards empty
- [ ] Ensure data sources are configured (Prometheus + Loki)
- [ ] Check dashboard timestamp is set to "Last 1 hour" or "Last 5 minutes"
- [ ] Regenerate data by triggering new requests (see Test Data Generation above)

---

## Cleanup

To stop all services:

```bash
docker-compose down
```

To reset data (careful!):

```bash
docker-compose down -v  # Remove volumes too
```

---

## Success Criteria

Quickstart is complete when:
- [ ] All 7 scenarios pass validation
- [ ] No errors in any service logs
- [ ] Grafana dashboards show recent data
- [ ] Langfuse shows traces with correct user_id and tokens
- [ ] Flower shows active workers and task execution
- [ ] App continues working even if Langfuse unavailable
