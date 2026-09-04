"""DI wiring for the challenges feature: single point that constructs
repositories, adapter, service, and completion service. Imported by
routes and by Celery tasks.

No side effects on module import beyond object construction — do NOT open
DB connections here.
"""

from __future__ import annotations

import os

from webx5.crud.challenge_log import ChallengeLogRepository
from webx5.crud.task import TaskRepository
from webx5.services.challenge import ChallengeService
from webx5.services.challenge_adapter import ChallengeAdapter
from webx5.services.task_completion import TaskCompletionService
from webx5.utils.forbidden_categories import get_synth_config

# --- repositories ---
task_repo = TaskRepository()
challenge_log_repo = ChallengeLogRepository()

# --- adapter (ORM ↔ synth dict-profile) ---
challenge_adapter = ChallengeAdapter(task_repo=task_repo)

# --- LLM config from env ---
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
CHALLENGE_LLM_MODEL = os.environ.get("CHALLENGE_LLM_MODEL", "anthropic/claude-haiku-4.5")

# --- SynthConfig — loaded once, cached ---
synth_config = get_synth_config()

# --- services ---
challenge_service = ChallengeService(
    task_repo=task_repo,
    log_repo=challenge_log_repo,
    adapter=challenge_adapter,
    synth_config=synth_config,
    model=CHALLENGE_LLM_MODEL,
    api_key=OPENROUTER_API_KEY,
)

task_completion_service = TaskCompletionService(task_repo=task_repo)
