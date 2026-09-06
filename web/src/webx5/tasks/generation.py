"""Celery task: generate one or several challenges for a user.

Idempotent via `TaskRepository.count_active_for_user` check + `session.begin()`
+ pessimistic lock on the User row.
"""

from __future__ import annotations

import uuid

import structlog
from sqlalchemy import select

from synth.challenges import CHALLENGE_SLOTS
from webx5.core.celery_app import celery_app
from webx5.entities.user import User

logger = structlog.get_logger("tasks.generation")


@celery_app.task(name="webx5.tasks.generation.generate_challenges", queue="challenges")
def generate_challenges(user_id: str, count: int = len(CHALLENGE_SLOTS)) -> dict:
    """`count` is informational only — see `ChallengeService.generate_batch`,
    which fills every currently-missing slot regardless of `count`."""
    from webx5.core.challenges import challenge_service
    from webx5.core.db import db

    from webx5.utils.contextvars_utils import user_id_context

    user_id_context.set(user_id)
    logger.info("generate_challenges.enter", user_id=user_id, requested_count=count)

    uid = uuid.UUID(user_id)
    with db.get_sync_session() as session:
        with session.begin():
            # Pessimistic user-level lock — sequential processing per user
            # (FR-014). Locks via `User.id` alone (no join, so no "FOR UPDATE
            # on the nullable side of an outer join" error from the
            # lazy="joined" `vibe_type` relationship) and does NOT select
            # the full `User` entity here: doing so with `noload(User.vibe_type)`
            # (an earlier version of this lock) planted a `User` row in this
            # session's identity map with `vibe_type` permanently left
            # unloaded (None) — `ChallengeAdapter.build_profile`'s later
            # `session.get(User, user_id)` then returned that SAME cached,
            # vibe_type-less instance instead of issuing a fresh, properly
            # joined query, so a user's actually-selected vibe was silently
            # ignored in favor of the hash-rotated fallback theme.
            locked_user_id = session.execute(
                select(User.id).where(User.id == uid).with_for_update()
            ).scalar_one_or_none()
            if locked_user_id is None:
                logger.warning("generate_challenges.user_not_found", user_id=user_id)
                return {"status": "no_op", "reason": "user_not_found"}

            created = challenge_service.generate_batch(session, uid, count)

    logger.info(
        "generate_challenges.done",
        user_id=user_id,
        requested=count,
        created_count=len(created),
        created_task_ids=[str(tid) for tid in created],
    )
    return {
        "status": "generated",
        "requested": count,
        "created": len(created),
        "task_ids": [str(tid) for tid in created],
    }
