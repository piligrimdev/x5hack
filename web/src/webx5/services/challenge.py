"""High-level challenge service: batch generation via `synth.challenges` +
resolving current-active list for API.

Synth API (single call → list[dict] of exactly 5 records, each with
`challenge_slot ∈ {'llm_habit', 'llm_discovery', 'llm_basket', 'generic',
'vibe'}`). De-dup with active tasks is done via `task.challenge_slot`.
"""

from __future__ import annotations

import uuid
from typing import Any

import structlog
from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from synth.challenges import CHALLENGE_SLOTS, generate_challenge_for_user
from synth.config import SynthConfig
from webx5.crud.challenge_log import ChallengeLogRepository
from webx5.crud.task import TaskRepository
from webx5.entities.receipt import Receipt
from webx5.entities.task import Task
from webx5.services.challenge_adapter import ChallengeAdapter
from webx5.services.openrouter_capturing import capture_openrouter_io

logger = structlog.get_logger("challenges")


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

    def generate_batch(
        self,
        session: Session,
        user_id: uuid.UUID,
        count: int,
        target_slots: set[str] | None = None,
    ) -> list[uuid.UUID]:
        """Generate up to `count` new tasks for `user_id`, filling missing challenge slots.
        Respects invariant "no more than 5 active tasks" (FR-001).

        Synth API: one call → list[dict] with exactly 5 records, always in the
        same fixed order (`generic`, `llm_habit`, `llm_discovery`, `llm_basket`,
        `vibe` — see `generate_challenge_for_user`).

        `target_slots`, when given, names the EXACT slot(s) to fill — e.g. the
        slots of the tasks that just completed/expired — and every other slot
        in the batch is skipped regardless of the fixed order above. Without
        this, a caller that only knows "N slots became free" (not which ones)
        has to fall back to "persist the first N slots in the fixed order that
        aren't already active" — which silently refills the WRONG slots
        whenever the ones that actually emptied aren't the first N in that
        order. Observed in production: a receipt completed llm_habit +
        llm_basket + vibe in one shot, three separate count=1 calls were
        dispatched, and — walking the same fixed order each time — all three
        landed on generic/llm_habit/llm_basket, permanently starving `vibe`
        (last in the fixed order) even though it was one of the three slots
        that had just emptied. `target_slots=None` keeps the old count-based
        behavior, used only where every slot is empty anyway (first-receipt
        trigger) and so there's nothing for a fixed order to get wrong.
        """
        active_tasks = self.task_repo.get_active_for_user(session, user_id)
        remaining_slots = len(CHALLENGE_SLOTS) - len(active_tasks)
        want = len(target_slots) if target_slots is not None else min(count, remaining_slots)
        if want <= 0 or remaining_slots <= 0:
            logger.info(
                "generate_batch.no_slots",
                user_id=str(user_id),
                requested_count=count,
                target_slots=list(target_slots) if target_slots is not None else None,
                active_count=len(active_tasks),
            )
            return []

        active_slots = {t.challenge_slot for t in active_tasks if t.challenge_slot}
        # Cross-slot duplicate guard: two independently-LLM-routed
        # slots (or a new slot and an already-active task) can land on the
        # same (criterion_type, criterion_entity_id) pair — e.g. `vibe`
        # genuinely overlapping a user's habitual top category — which would
        # otherwise create two functionally-duplicate challenge cards.
        existing_criteria: set[tuple[str, uuid.UUID]] = {
            (t.criterion_type, t.criterion_entity_id) for t in active_tasks if t.criterion_type and t.criterion_entity_id
        }
        # Cross-cycle duplicate guard for the `generic` slot ONLY (see the
        # `slot == "generic"` check below, where this is consumed) — its
        # pick has no natural variation source and would otherwise repeat
        # forever. LLM-driven slots and `vibe` are deliberately NOT subject
        # to this: a stable habit legitimately recommending the same target
        # cycle after cycle is correct behavior, not a duplicate to block —
        # an earlier version of this check applied to every slot and made
        # llm_habit/vibe permanently unfillable whenever the LLM kept
        # recommending the same product. Independent of `existing_criteria`
        # above (which only guards THIS batch/active tasks against each
        # other, not against history).
        previous_by_slot = self.task_repo.get_last_criterion_per_slot(session, user_id)
        profile = self.adapter.build_profile(session, user_id, self.synth_config)

        logger.info(
            "generate_batch.start",
            user_id=str(user_id),
            want=want,
            target_slots=list(target_slots) if target_slots is not None else None,
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

            # Per-slot prompt/response (set by `synth.challenges._run_llm_slot`
            # on its own successful "personal" record) — NOT the batch-level
            # `captured_prompt`/`captured_response` above, which only ever
            # holds the LAST LLM call made inside this `generate_batch` run
            # and would otherwise get logged against every slot's row,
            # including slots that never called the LLM at all (`generic`)
            # or whose own call failed (`generic_fallback`) — `.get(...)`
            # already returns None for those, which is the honest answer.
            log_id = self.log_repo.record(
                session,
                user_id=user_id,
                challenge_type=slot,
                script_result=script_result,
                prompt=script_result.get("prompt"),
                response=script_result.get("response"),
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

            if target_slots is not None:
                if slot not in target_slots:
                    logger.info(
                        "generate_batch.not_targeted_skip",
                        user_id=str(user_id),
                        challenge_slot=slot,
                        target_slots=list(target_slots),
                    )
                    continue
            elif len(created_ids) >= want:
                logger.info(
                    "generate_batch.want_reached_skip",
                    user_id=str(user_id),
                    challenge_slot=slot,
                    want=want,
                )
                continue

            try:
                criterion = self.adapter.resolve_criterion(session, script_result)
            except Exception as e:  # noqa: BLE001 — same failure modes persist_challenge would hit
                logger.error(
                    "generation.persist_failed",
                    user_id=str(user_id),
                    challenge_slot=slot,
                    error=str(e),
                )
                continue

            # Scoped to `generic` only — its pick has no natural source of
            # variation (a pure function of user_id, only rotated across
            # cycles via `generic_cycle_index`), so without this check it
            # could repeat forever. LLM-driven slots (llm_habit/llm_discovery/
            # llm_basket) and `vibe` legitimately CAN and should repeat their
            # own previous target when the underlying habit/theme hasn't
            # changed — blocking that made those slots permanently unfillable
            # in practice whenever the LLM kept recommending the same thing.
            if slot == "generic" and previous_by_slot.get(slot) == criterion:
                logger.info(
                    "generate_batch.repeats_previous_cycle_skip",
                    user_id=str(user_id),
                    challenge_slot=slot,
                    criterion_type=criterion[0],
                    criterion_entity_id=str(criterion[1]),
                )
                continue

            if criterion in existing_criteria:
                logger.info(
                    "generate_batch.duplicate_criterion_skip",
                    user_id=str(user_id),
                    challenge_slot=slot,
                    criterion_type=criterion[0],
                    criterion_entity_id=str(criterion[1]),
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
            existing_criteria.add(criterion)
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
