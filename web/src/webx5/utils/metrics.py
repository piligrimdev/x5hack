"""Prometheus metrics for observability.

Provides counters, histograms, and gauges for:
- Standard HTTP metrics (request count, latency, errors)
- Custom application metrics (Celery tasks, LLM generations, basket calculations)
"""

from prometheus_client import Counter, Histogram, Gauge

# Standard HTTP metrics
REQUEST_COUNT = Counter(
    'webx5_request_count',
    'Total HTTP requests',
    ['method', 'endpoint', 'status'],
)

REQUEST_LATENCY = Histogram(
    'webx5_request_latency',
    'HTTP request latency in seconds',
    ['method', 'endpoint'],
    buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
)

ERROR_COUNT = Counter(
    'webx5_error_count',
    'Total HTTP errors',
    ['method', 'endpoint', 'error_type'],
)

# Celery task metrics
CELERY_TASKS_PROCESSED = Counter(
    'webx5_celery_tasks_processed',
    'Total Celery tasks processed',
    ['task_name', 'status'],
)

CELERY_TASK_DURATION = Histogram(
    'webx5_celery_task_duration',
    'Celery task execution duration in seconds',
    ['task_name'],
    buckets=[0.1, 0.5, 1.0, 5.0, 10.0, 30.0, 60.0, 300.0],
)

ACTIVE_CELERY_WORKERS = Gauge(
    'webx5_celery_active_workers',
    'Number of active Celery workers',
)

# LLM generation metrics
LLM_GENERATION_SUCCESS = Counter(
    'webx5_llm_generation_success',
    'Successful LLM generations',
    ['model'],
)

LLM_GENERATION_FAILED = Counter(
    'webx5_llm_generation_failed',
    'Failed LLM generations',
    ['model', 'error_type'],
)

LLM_TOKENS = Counter(
    'webx5_llm_tokens',
    'LLM tokens consumed',
    ['model', 'user_id', 'token_type'],
)

LLM_COST_USD = Counter(
    'webx5_llm_cost_usd',
    'LLM cost in USD',
    ['model', 'user_id'],
)

# Basket calculation metrics
BASKET_CALCULATION_DURATION = Histogram(
    'webx5_basket_calculation_duration',
    'Basket calculation duration in seconds',
    ['operation'],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 5.0],
)
