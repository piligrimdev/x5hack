"""Celery application: broker + result backend from env; queues and Beat schedule.

Autodiscovers tasks in `webx5.tasks` package.
"""

from __future__ import annotations

import os

from celery import Celery
from dotenv import load_dotenv

load_dotenv()

REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")

# Explicit module list — Celery's autodiscover_tasks(packages=[...]) expects
# a Django-style "each package contains a `tasks` module" layout, which we
# don't have. Listing modules directly ensures every @celery_app.task in
# these files is registered at worker startup.
_TASK_MODULES = [
    "webx5.tasks.receipt",
    "webx5.tasks.generation",
    "webx5.tasks.expiration",
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
