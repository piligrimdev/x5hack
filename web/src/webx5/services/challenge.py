"""High-level challenge service: batch generation via `synth.challenges` +
resolving current-active list for API.

Path type derivation (which synth `challenge_type` a Task came from) is done
by reading `task.path` field written at persist time — but the *challenge type*
label is broader than `path` (e.g. spend_threshold and category_expansion both
yield path='personal'). We use `task.mechanic` as the discriminator instead.
"""

from __future__ import annotations

import uuid
from typing import Any

import structlog
from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from synth.challenges import generate_challenge_for_user
from synth.config import SynthConfig
from webx5.crud.challenge_log import ChallengeLogRepository
from webx5.crud.task import TaskRepository
from webx5.entities.challenge_log import ChallengeGenerationLog
from webx5.entities.receipt import Receipt
from webx5.entities.task import Task
from webx5.services.challenge_adapter import ChallengeAdapter
from webx5.services.openrouter_capturing import capture_openrouter_io

logger = structlog.get_logger("challenges")

# Preferred order: cheap deterministic paths first, then LLM (research.md R2).
CHALLENGE_TYPES_ORDER: list[str] = ["spend_threshold", "category_expansion", "llm"]

# Reverse map: task.mechanic → challenge_type (used to detect what types are already active).
MECHANIC_TO_TYPE: dict[str, str] = {
    "порог трат + скидка на любимый товар": "spend_threshold",
    "скидка на новую категорию": "category_expansion",
}


def _type_from_task(task: Task) -> str:
    """Best-effort classification of a Task into its origin challenge_type.
    Falls back to 'llm' for anything not explicitly mapped (LLM-generated
    tasks and generic-pool tasks both count as 'llm-slot' for de-dup purposes)."""
    return MECHANIC_TO_TYPE.get(task.mechanic, "llm")


class ChallengeService:
    def __init__(
        self,
        task_repo: TaskRepository,
        log_repo: ChallengeLogRepository,
        adapter: ChallengeAdapter,
        synth_config: SynthConfig,
        model: str,
        api_key: str,
    ) -> None:
        self.task_repo = task_repo
        self.log_repo = log_repo
        self.adapter = adapter
        self.synth_config = synth_config
        self.model = model
        self.api_key = api_key

    def generate_batch(self, session: Session, user_id: uuid.UUID, count: int) -> list[uuid.UUID]:
        """Generate up to `count` new tasks for `user_id`, filling missing challenge_types.
        Respects the invariant "no more than 3 active tasks" (FR-001).
        """
        active_tasks = self.task_repo.get_active_for_user(session, user_id)
        remaining_slots = 3 - len(active_tasks)
        count = min(count, remaining_slots)
        if count <= 0:
            return []

        active_types = {_type_from_task(t) for t in active_tasks}
        missing = [t for t in CHALLENGE_TYPES_ORDER if t not in active_types]
        to_generate = missing[:count]

        profile = self.adapter.build_profile(session, user_id, self.synth_config)

        created_ids: list[uuid.UUID] = []
        for challenge_type in to_generate:
            captured_prompt: str | None = None
            captured_response: str | None = None
            try:
                with capture_openrouter_io() as capture:
                    script_result = generate_challenge_for_user(
                        profile=profile,
                        config=self.synth_config,
                        model=self.model,
                        api_key=self.api_key or None,
                        dry_run=False,
                        challenge_type=challenge_type,
                    )
                if capture.get("system") is not None:
                    captured_prompt = f"[SYSTEM]\n{capture['system']}\n\n[USER]\n{capture.get('user', '')}"
                captured_response = capture.get("response")
            except Exception as e:  # noqa: BLE001 — must not propagate; fallback to skip + log
                logger.error("generation.script_exception", user_id=str(user_id), challenge_type=challenge_type, error=str(e))
                self.log_repo.record(
                    session,
                    user_id=user_id,
                    challenge_type=challenge_type,
                    script_result={"path": "generic_fallback", "error": str(e)},
                    prompt=captured_prompt,
                    response=captured_response,
                )
                continue

            log_id = self.log_repo.record(
                session,
                user_id=user_id,
                challenge_type=challenge_type,
                script_result=script_result,
                prompt=captured_prompt,
                response=captured_response,
            )

            if script_result.get("path") == "no_challenge":
                # Saturated — slot stays empty by design (FR-022).
                logger.info(
                    "generation.no_challenge",
                    user_id=str(user_id),
                    challenge_type=challenge_type,
                )
                continue

            try:
                task_id = self.adapter.persist_challenge(session, user_id, script_result)
            except Exception as e:  # noqa: BLE001 — persistence failure shouldn't kill the batch
                logger.error(
                    "generation.persist_failed",
                    user_id=str(user_id),
                    challenge_type=challenge_type,
                    error=str(e),
                )
                continue

            self.log_repo.attach_task(session, log_id, task_id)
            created_ids.append(task_id)

        return created_ids

    # ------- read side (for GET /challenges/current) -------
    def get_current(self, session: Session, user_id: uuid.UUID) -> tuple[list[Task], str]:
        """Returns (list of active tasks, empty_reason).
        empty_reason ∈ {'none', 'no_history', 'saturated'}."""
        active = self.task_repo.get_active_for_user(session, user_id)
        if active:
            return active, "none"

        has_receipts = session.execute(
            select(exists().where(Receipt.loyalty_card_id == user_id))
        ).scalar()
        if not has_receipts:
            return [], "no_history"

        last_log = session.execute(
            select(ChallengeGenerationLog)
            .where(ChallengeGenerationLog.user_id == user_id)
            .order_by(ChallengeGenerationLog.created_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        if last_log is not None and last_log.path == "no_challenge":
            return [], "saturated"

        return [], "none"
