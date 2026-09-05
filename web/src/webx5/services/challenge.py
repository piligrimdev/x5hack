"""High-level challenge service: batch generation via `synth.challenges` +
resolving current-active list for API.

Synth API (single call → list[dict] of exactly 4 records, each with
`challenge_slot ∈ {'llm_habit', 'llm_discovery', 'generic', 'vibe'}`).
De-dup with active tasks is done via `task.challenge_slot`.
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
from webx5.entities.receipt import Receipt
from webx5.entities.task import Task
from webx5.services.challenge_adapter import ChallengeAdapter
from webx5.services.openrouter_capturing import capture_openrouter_io

logger = structlog.get_logger("challenges")

ALL_SLOTS: tuple[str, ...] = ("llm_habit", "llm_discovery", "generic", "vibe")


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
        """Generate up to `count` new tasks for `user_id`, filling missing challenge slots.
        Respects invariant "no more than 4 active tasks" (FR-001).

        Synth API: one call → list[dict] with exactly 4 records.
        We filter the returned records by challenge_slot to skip slots the user
        already has active, then persist up to `count` of the remaining.
        """
        active_tasks = self.task_repo.get_active_for_user(session, user_id)
        remaining_slots = 4 - len(active_tasks)
        want = min(count, remaining_slots)
        if want <= 0:
            logger.info(
                "generate_batch.no_slots",
                user_id=str(user_id),
                requested_count=count,
                active_count=len(active_tasks),
            )
            return []

        active_slots = {t.challenge_slot for t in active_tasks if t.challenge_slot}
        profile = self.adapter.build_profile(session, user_id, self.synth_config)

        logger.info(
            "generate_batch.start",
            user_id=str(user_id),
            want=want,
            active_slots=list(active_slots),
            profile_receipts_count=len(profile.get("receipts", [])),
            profile_habitual_categories=profile.get("habitual_categories", []),
        )

        captured_prompt: str | None = None
        captured_response: str | None = None
        try:
            with capture_openrouter_io() as capture:
                script_results = generate_challenge_for_user(
                    profile=profile,
                    config=self.synth_config,
                    model=self.model,
                    api_key=self.api_key or None,
                    dry_run=False,
                )
            if capture.get("system") is not None:
                captured_prompt = f"[SYSTEM]\n{capture['system']}\n\n[USER]\n{capture.get('user', '')}"
            captured_response = capture.get("response")
        except Exception as e:  # noqa: BLE001 — must not propagate
            logger.error("generation.script_exception", user_id=str(user_id), error=str(e))
            self.log_repo.record(
                session,
                user_id=user_id,
                challenge_type="batch",
                script_result={"path": "generic_fallback", "error": str(e)},
                prompt=captured_prompt,
                response=captured_response,
            )
            return []

        # Log every returned record + persist those whose slot isn't already active.
        created_ids: list[uuid.UUID] = []
        for script_result in script_results:
            slot = script_result.get("challenge_slot") or "unknown"

            log_id = self.log_repo.record(
                session,
                user_id=user_id,
                challenge_type=slot,
                script_result=script_result,
                prompt=captured_prompt,
                response=captured_response,
            )

            logger.info(
                "generate_batch.script_result",
                user_id=str(user_id),
                challenge_slot=slot,
                path=script_result.get("path"),
                model=script_result.get("model"),
                title=script_result.get("challenge_title"),
                target_categories=script_result.get("target_categories"),
                target_sku_id=script_result.get("target_sku_id"),
                target_quantity=script_result.get("target_quantity"),
                mechanic=script_result.get("mechanic"),
                reward_rub=script_result.get("reward_rub"),
                favorite_item=script_result.get("favorite_item"),
                novel_item=script_result.get("novel_item"),
                spend_threshold_rub=script_result.get("spend_threshold_rub"),
                reasoning=script_result.get("reasoning"),
                receptiveness=script_result.get("receptiveness_signal"),
                frequency_signal=script_result.get("frequency_signal"),
            )

            if script_result.get("path") == "no_challenge":
                logger.info(
                    "generation.no_challenge",
                    user_id=str(user_id),
                    challenge_slot=slot,
                    reasoning=script_result.get("reasoning"),
                )
                continue

            if slot in active_slots:
                logger.info(
                    "generate_batch.slot_already_active_skip",
                    user_id=str(user_id),
                    challenge_slot=slot,
                )
                continue

            if len(created_ids) >= want:
                logger.info(
                    "generate_batch.want_reached_skip",
                    user_id=str(user_id),
                    challenge_slot=slot,
                    want=want,
                )
                continue

            try:
                task_id = self.adapter.persist_challenge(session, user_id, script_result)
            except Exception as e:  # noqa: BLE001
                logger.error(
                    "generation.persist_failed",
                    user_id=str(user_id),
                    challenge_slot=slot,
                    error=str(e),
                )
                continue

            self.log_repo.attach_task(session, log_id, task_id)
            active_slots.add(slot)
            created_ids.append(task_id)
            logger.info(
                "generate_batch.task_created",
                user_id=str(user_id),
                task_id=str(task_id),
                challenge_slot=slot,
                path=script_result.get("path"),
            )

        return created_ids

    # ------- read side (for GET /challenges/history) -------
    def get_history(
        self,
        session: Session,
        user_id: uuid.UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Task], int]:
        """Non-open tasks + total count for pagination."""
        items = self.task_repo.get_history_for_user(session, user_id, limit=limit, offset=offset)
        total = self.task_repo.count_history_for_user(session, user_id)
        return items, total

    # ------- read side (for GET /challenges/current) -------
    def get_current(self, session: Session, user_id: uuid.UUID) -> tuple[list[Task], str]:
        """Returns (list of active tasks, empty_reason).
        empty_reason ∈ {'none', 'no_history'}."""
        active = self.task_repo.get_active_for_user(session, user_id)
        if active:
            return active, "none"

        has_receipts = session.execute(
            select(exists().where(Receipt.loyalty_card_id == user_id))
        ).scalar()
        if not has_receipts:
            return [], "no_history"

        return [], "none"
