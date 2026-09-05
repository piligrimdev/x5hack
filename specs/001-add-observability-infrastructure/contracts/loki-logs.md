# Loki Logs Contract

**Версия**: 1.0  
**Дата**: 2026-09-05

## Обзор

Приложение emits структурированные JSON логи в stdout; Promtail собирает их и пересылает в Loki для querying.

---

## Log Format

### JSON Structure

Все логи ДОЛЖНЫ быть valid JSON, одна строка за log entry:

```json
{
  "timestamp": "ISO8601",
  "level": "LEVEL",
  "service_name": "STRING",
  "logger": "STRING",
  "message": "STRING",
  
  "user_id": "UUID or null",
  "request_id": "STRING",
  "procedure_name": "STRING",
  "procedure_state": "STRING",
  
  "duration_ms": "INTEGER or null",
  "error_type": "STRING or null",
  "error_message": "STRING or null",
  "stack_trace": "STRING or null",
  "external_api": "STRING or null",
  "tokens_used": "INTEGER or null"
}
```

### Example Logs

**Info Log** (normal operation):
```json
{"timestamp":"2026-09-05T12:34:56.123Z","level":"INFO","service_name":"webx5","logger":"app.routes.challenges","message":"challenge_retrieved","user_id":"f47ac10b-58cc-4372-a567-0e02b2c3d479","request_id":"req-abc123","procedure_name":"get_challenge","procedure_state":"completed","duration_ms":45}
```

**Error Log** (with stack trace):
```json
{"timestamp":"2026-09-05T12:35:10.456Z","level":"ERROR","service_name":"webx5","logger":"app.core.llm","message":"openrouter_api_error","user_id":"f47ac10b-58cc-4372-a567-0e02b2c3d479","request_id":"req-abc123","procedure_name":"call_openrouter_tools","procedure_state":"failed","external_api":"openrouter","error_type":"HTTPStatusError","error_message":"429 Too Many Requests","stack_trace":"Traceback (most recent call last):\n  File \"app/core/llm.py\", line 45, in call_openrouter_tools\n    resp.raise_for_status()\n..."}
```

**Public Endpoint Log** (null user_id):
```json
{"timestamp":"2026-09-05T12:36:00.789Z","level":"INFO","service_name":"webx5","logger":"app.routes.health","message":"health_check","user_id":null,"request_id":"req-def456","procedure_name":"health_check","procedure_state":"completed","duration_ms":2}
```

**Worker Log** (background task):
```json
{"timestamp":"2026-09-05T12:37:15.321Z","level":"INFO","service_name":"webx5-worker","logger":"app.tasks.receipt","message":"receipt_processing_started","user_id":"f47ac10b-58cc-4372-a567-0e02b2c3d479","request_id":null,"procedure_name":"process_receipt","procedure_state":"started"}
```

---

## Field Specifications

### Mandatory Fields

| Field | Type | Example | Rules |
|-------|------|---------|-------|
| `timestamp` | ISO8601 string | `2026-09-05T12:34:56.123Z` | MUST be ISO8601 with Z suffix |
| `level` | string | `INFO`, `ERROR` | One of: DEBUG, INFO, WARNING, ERROR, CRITICAL |
| `service_name` | string | `webx5`, `webx5-worker` | Must be one of: webx5, webx5-worker, webx5-beat |
| `logger` | string | `app.routes.challenges` | Module.function format |
| `message` | string | `challenge_retrieved` | Lowercase snake_case, max 100 chars |
| `user_id` | UUID string or null | `f47ac10b-...` or `null` | NULL OK for public endpoints |
| `request_id` | string | `req-20260905-abc123` | Must be unique per request; NULL for background tasks |
| `procedure_name` | string | `get_challenge` | Function name or operation name, snake_case |
| `procedure_state` | string | `started`, `completed`, `failed` | One of: started, processing, completed, failed |

### Optional Fields

| Field | Type | Example | When Used |
|-------|------|---------|-----------|
| `duration_ms` | integer | `150` | When procedure state is "completed" or "failed" |
| `error_type` | string | `ValidationError` | When level is ERROR or WARNING |
| `error_message` | string | `Invalid email format` | When error_type present |
| `stack_trace` | string | `Traceback (...)` | When ERROR level and exception available |
| `external_api` | string | `openrouter`, `stripe` | When calling external API |
| `tokens_used` | integer | `450` | When LLM call occurred |

---

## Loki Labels (Extracted by Promtail)

Promtail pipeline MUST extract these labels from JSON:

```yaml
pipeline_stages:
  - json:
      expressions:
        timestamp: timestamp
        level: level
        service_name: service_name
        user_id: user_id
        request_id: request_id
        procedure_name: procedure_name
        procedure_state: procedure_state
```

### Queryable Labels

After extraction, Loki can query by:
- `{service_name="webx5"}` — All logs from API
- `{service_name="webx5-worker"}` — All logs from worker
- `{user_id="f47ac10b-..."}` — All logs for specific user
- `{request_id="req-abc123"}` — All logs for specific request
- `{procedure_name="call_openrouter_tools"}` — All logs for specific procedure
- `{procedure_state="failed"}` — All failed operations
- `{level="ERROR"}` — All errors
- Combinations: `{service_name="webx5", level="ERROR", user_id="..."}` — Errors for user in API

---

## Validation Rules

### Per Log Entry
- [ ] JSON is valid (can be parsed)
- [ ] timestamp is ISO8601 format
- [ ] level is one of: DEBUG, INFO, WARNING, ERROR, CRITICAL
- [ ] service_name is one of: webx5, webx5-worker, webx5-beat
- [ ] message is max 100 characters
- [ ] user_id is valid UUID or null
- [ ] procedure_state is one of: started, processing, completed, failed
- [ ] If level=ERROR: error_type and error_message present
- [ ] If procedure_state=completed/failed: duration_ms present

### Loki Constraints
- [ ] Log size < 1 MB per entry
- [ ] Cardinality of (service_name, user_id, procedure_name) < 100,000 unique combinations
- [ ] No sensitive data in logs (passwords, API keys, PII)

---

## Query Examples (Logql)

```logql
# All logs for specific user
{user_id="f47ac10b-58cc-4372-a567-0e02b2c3d479"}

# Errors from API
{service_name="webx5", level="ERROR"}

# LLM calls for user
{user_id="f47ac10b-58cc-4372-a567-0e02b2c3d479"} | json | procedure_name="call_openrouter_tools"

# Failed procedures
{procedure_state="failed"}

# Slow procedures (>5 seconds)
{procedure_state="completed"} | json | duration_ms > 5000

# Openrouter errors
{external_api="openrouter", level="ERROR"}
```

---

## Log Output Checklist

- [ ] Logs go to stdout (not files)
- [ ] Each log is single-line JSON (no pretty-print)
- [ ] No sensitive data (credentials, API keys, PII)
- [ ] Timestamps always ISO8601
- [ ] All 5 mandatory labels present
- [ ] Error logs include stack_trace
- [ ] No duplicate logs for same operation
