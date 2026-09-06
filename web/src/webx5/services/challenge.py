"""High-level challenge service: batch generation via `synth.challenges` +
resolving current-active list for API.

Synth API (single call → list[dict] of exactly 5 records, each with
`challenge_slot ∈ {'llm_habit', 'llm_discovery', 'llm_basket', 'generic',
'vibe'}`). De-dup with active tasks is done via `task.challenge_slot`.
"""

from __future__ import annotations

import uuid

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
from webx5.services.survival import SurvivalCurveStore

logger = structlog.get_logger("challenges")

# Slots whose pick has no natural source of cycle-to-cycle variation. The set
# is retained for repeat telemetry, but repeat/dedup signals must not suppress
# a missing slot: the product invariant is exactly five active challenges.
_SLOTS_WITHOUT_NATURAL_VARIATION = frozenset({"generic"})


class ChallengeService:
    def __init__(
        self,
        task_repo: TaskRepository,
        log_repo: ChallengeLogRepository,
        adapter: ChallengeAdapter,
        synth_config: SynthConfig,
        model: str,
        api_key: str,
        curve_store: SurvivalCurveStore,
    ) -> None:
        self.task_repo = task_repo
        self.log_repo = log_repo
        self.adapter = adapter
        self.synth_config = synth_config
        self.model = model
        self.api_key = api_key
        self.curve_store = curve_store

    @staticmethod
    def _needs_slot_repair(task: Task) -> bool:
        """Detect old generic cards occupying the themed slots.

        Earlier generator versions created the basket and vibe records via
        ``generic_fallback`` when the train split/LLM was unavailable. Those
        records still count as active slots, so changing the generator alone
        cannot make the corrected cards appear for existing users.
        """
        slot = task.challenge_slot
        path = getattr(task, "path", None)
        if slot == "llm_basket":
            return path == "generic_fallback" or (
                isinstance(getattr(task, "mechanic", None), str)
                and task.mechanic != "кэшбэк за сумму корзины"
            )
        if slot == "vibe":
            return path == "generic_fallback" or (
                isinstance(getattr(task, "title", None), str)
                and not task.title.startswith("Вайб месяца:")
            )
        return False

    def generate_batch(self, session: Session, user_id: uuid.UUID, count: int) -> list[uuid.UUID]:
        """Fill every currently-missing challenge slot for `user_id` in one
        shot. Respects invariant "no more than 5 active tasks" (FR-001) —
        naturally, since there are only `len(CHALLENGE_SLOTS)` known slots
        and each is guarded below by `slot_already_active_skip`.

        `count` is accepted for the caller's own logging/bookkeeping only —
        it does NOT cap how many slots get filled. An earlier design capped
        persistence at `count` slots, walking `generate_challenge_for_user`'s
        FIXED result order (`generic`, `llm_habit`, `llm_discovery`,
        `llm_basket`, `vibe`) and stopping once `count` were persisted. That
        silently filled the WRONG slots whenever the ones that actually
        needed filling weren't first in that order: (1) several slots
        completing in one receipt each dispatched their own `count=1` call,
        and — walking the same fixed order every time — all of them landed
        on the earlier slots, permanently starving `vibe` (last in the
        order); (2) an account that had never had an `llm_basket` task
        (created before that slot existed) could never get one, because a
        `count`-sized replacement for its other 4 slots always preferred
        them over the never-yet-filled 5th. Filling every eligible slot
        unconditionally fixes both. The only hard skip is an already-active
        slot; duplicate and repeat signals are logged for diagnostics but
        cannot make the five-slot batch shorter.
        """
        active_tasks = self.task_repo.get_active_for_user(session, user_id)
        obsolete_tasks = [task for task in active_tasks if self._needs_slot_repair(task)]
        if obsolete_tasks:
            for task in obsolete_tasks:
                self.task_repo.mark_expired_for_replacement(session, task)
            logger.info(
                "generate_batch.repaired_obsolete_slots",
                user_id=str(user_id),
                slots=[task.challenge_slot for task in obsolete_tasks],
            )
            active_tasks = self.task_repo.get_active_for_user(session, user_id)
        active_slots = {t.challenge_slot for t in active_tasks if t.challenge_slot}
        # The count alone is not enough: users created before the five-slot
        # scheme (or a previous partial generation) can have five active
        # tasks while `llm_basket` or `vibe` is still absent. In that case we
        # must repair the missing slots instead of returning early.
        if (
            len(active_tasks) >= len(CHALLENGE_SLOTS)
            and set(CHALLENGE_SLOTS).issubset(active_slots)
        ):
            logger.info(
                "generate_batch.no_slots",
                user_id=str(user_id),
                requested_count=count,
                active_count=len(active_tasks),
            )
            return []

        # Cross-slot duplicate telemetry: two independently-LLM-routed
        # slots (or a new slot and an already-active task) can land on the
        # same (criterion_type, criterion_entity_id) pair — e.g. `vibe`
        # genuinely overlapping a user's habitual top category — which would
        # otherwise create two functionally-duplicate challenge cards.
        existing_criteria: set[tuple[str, uuid.UUID]] = {
            (t.criterion_type, t.criterion_entity_id) for t in active_tasks if t.criterion_type and t.criterion_entity_id
        }
        # Category-level duplicate telemetry: catches two slots
        # landing on DIFFERENT products of the SAME category (e.g. "сметана"
        # vs "яйца", both "молочные продукты и яйца") — the exact-criterion
        # check above only sees identical products and lets this through,
        # which still reads as "two of the same kind of challenge" to a user.
        existing_category_ids: set[uuid.UUID] = {
            cat_id
            for t in active_tasks
            if t.criterion_type and t.criterion_entity_id
            for cat_id in [self.adapter.resolve_category_id(session, t.criterion_type, t.criterion_entity_id)]
            if cat_id is not None
        }
        # Cross-cycle duplicate telemetry for the `generic` slot ONLY (see the
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
            requested_count=count,
            active_slots=list(active_slots),
            profile_receipts_count=len(profile.get("receipts", [])),
            profile_habitual_categories=profile.get("habitual_categories", []),
        )

        captured_prompt: str | None = None
        captured_response: str | None = None
        try:
            # Refit the population model after the latest receipt has been
            # committed. The user's profile is already read fresh below;
            # refreshing the population curves keeps both sides of the
            # survival score on the same data snapshot.
            category_curves = self.curve_store.refresh()
            with capture_openrouter_io() as capture:
                script_results = generate_challenge_for_user(
                    profile=profile,
                    config=self.synth_config,
                    model=self.model,
                    api_key=self.api_key or None,
                    dry_run=False,
                    category_curves=category_curves,
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

            # Repeat detection is diagnostic only. A missing slot must still
            # be persisted so the user keeps five active challenges.
            if slot in _SLOTS_WITHOUT_NATURAL_VARIATION and previous_by_slot.get(slot) == criterion:
                logger.info(
                    "generate_batch.repeats_previous_cycle_allow",
                    user_id=str(user_id),
                    challenge_slot=slot,
                    criterion_type=criterion[0],
                    criterion_entity_id=str(criterion[1]),
                )

            # Duplicate checks are diagnostic only. The basket has an
            # independent spend-threshold criterion and may share its anchor
            # product/category with a survival challenge; no check may remove
            # a missing slot from the five-slot batch.
            if criterion in existing_criteria:
                logger.info(
                    "generate_batch.duplicate_criterion_allow",
                    user_id=str(user_id),
                    challenge_slot=slot,
                    criterion_type=criterion[0],
                    criterion_entity_id=str(criterion[1]),
                )

            category_id = self.adapter.resolve_category_id(session, *criterion)
            if category_id is not None and category_id in existing_category_ids:
                logger.info(
                    "generate_batch.duplicate_category_allow",
                    user_id=str(user_id),
                    challenge_slot=slot,
                    category_id=str(category_id),
                )

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
            if category_id is not None:
                existing_category_ids.add(category_id)
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
