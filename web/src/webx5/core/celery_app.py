"""Celery application: broker + result backend from env; queues and Beat schedule.

Autodiscovers tasks in `webx5.tasks` package.
"""

from __future__ import annotations

import os
import time

import structlog
from celery import Celery
from celery.signals import task_failure, task_postrun, task_prerun, worker_init, worker_process_init
from dotenv import load_dotenv

load_dotenv()

_log = structlog.get_logger("webx5.celery")
_task_start_times: dict[str, float] = {}


@task_prerun.connect
def on_task_prerun(task_id: str, task, **kwargs) -> None:
    _task_start_times[task_id] = time.monotonic()
    _log.info(
        "celery.task.started",
        task_name=task.name,
        task_id=task_id,
        procedure_name=task.name,
        procedure_state="started",
    )


@task_postrun.connect
def on_task_postrun(task_id: str, task, retval, state: str, **kwargs) -> None:
    from webx5.utils.metrics import CELERY_TASK_DURATION, CELERY_TASKS_PROCESSED

    start = _task_start_times.pop(task_id, None)
    duration = time.monotonic() - start if start is not None else 0.0
    status = "success" if state == "SUCCESS" else "failed"

    CELERY_TASKS_PROCESSED.labels(task_name=task.name, status=status).inc()
    CELERY_TASK_DURATION.labels(task_name=task.name).observe(duration)

    _log.info(
        "celery.task.completed",
        task_name=task.name,
        task_id=task_id,
        state=state,
        procedure_state="completed" if status == "success" else "failed",
        duration_ms=round(duration * 1000, 2),
    )


@worker_init.connect
def on_worker_init(**kwargs) -> None:
    """Solo/threads pool: no fork, so a single init in the worker process is enough."""
    from webx5.core.langfuse_client import init_langfuse

    init_langfuse()


@worker_process_init.connect
def on_worker_process_init(**kwargs) -> None:
    """Prefork pool: rebuild the SDK in each child — the parent's flush thread dies on fork."""
    from webx5.core.langfuse_client import init_langfuse

    init_langfuse(force=True)


@task_failure.connect
def on_task_failure(task_id: str, exception, traceback, **kwargs) -> None:
    _log.error(
        "celery.task.failed",
        task_id=task_id,
        error_type=type(exception).__name__,
        error_message=str(exception),
        procedure_state="failed",
    )

REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")

# Explicit module list — Celery's autodiscover_tasks(packages=[...]) expects
# a Django-style "each package contains a `tasks` module" layout, which we
# don't have. Listing modules directly ensures every @celery_app.task in
# these files is registered at worker startup.
_TASK_MODULES = [
    "webx5.tasks.receipt",
    "webx5.tasks.generation",
    "webx5.tasks.expiration",
    "webx5.tasks.basket",
]

celery_app = Celery(
    "webx5",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=_TASK_MODULES,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_time_limit=180,
    task_soft_time_limit=120,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_default_queue="receipts",
    beat_schedule={
        "expire-tasks-every-minute": {
            "task": "webx5.tasks.expiration.expire_tasks",
            "schedule": 60.0,
        },
    },
)
