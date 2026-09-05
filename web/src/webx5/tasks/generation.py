"""Celery task: generate one or several challenges for a user.

Idempotent via `TaskRepository.count_active_for_user` check + `session.begin()`
+ pessimistic lock on the User row.
"""

from __future__ import annotations

import uuid

import structlog
from sqlalchemy import select

from webx5.core.celery_app import celery_app
from webx5.entities.user import User

logger = structlog.get_logger("tasks.generation")


@celery_app.task(name="webx5.tasks.generation.generate_challenges", queue="challenges")
def generate_challenges(user_id: str, count: int = 4) -> dict:
    from webx5.core.challenges import challenge_service
    from webx5.core.db import db

    logger.info("generate_challenges.enter", user_id=user_id, requested_count=count)

    uid = uuid.UUID(user_id)
    with db.get_sync_session() as session:
        with session.begin():
            # Pessimistic user-level lock — sequential processing per user (FR-014).
            user = session.execute(
                select(User).where(User.id == uid).with_for_update()
            ).scalar_one_or_none()
            if user is None:
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
