"""Celery Beat task: expire overdue open tasks + enqueue replacements.

Runs every 60 seconds (see celery_app.beat_schedule).
"""

from __future__ import annotations

from collections import defaultdict

import structlog

from webx5.core.celery_app import celery_app

logger = structlog.get_logger("tasks.expiration")


@celery_app.task(name="webx5.tasks.expiration.expire_tasks", queue="challenges")
def expire_tasks() -> dict:
    from webx5.core.challenges import task_repo
    from webx5.core.db import db
    from webx5.tasks.generation import generate_challenges

    logger.info("expire_tasks.enter")

    with db.get_sync_session() as session:
        with session.begin():
            expired = task_repo.expire_overdue(session, batch_size=100)

    if not expired:
        logger.info("expire_tasks.no_expired")
        return {"status": "no_expired", "count": 0, "users": 0}

    # One combined call per user naming the exact slots that expired (see
    # ChallengeService.generate_batch's target_slots docstring — several
    # anonymous "fill N slots" calls silently refill the wrong slots when
    # more than one expires for the same user in the same sweep). A legacy
    # task with no challenge_slot falls back to the old anonymous count.
    slots_by_user: dict[str, list[str]] = defaultdict(list)
    unknown_slot_count_by_user: dict[str, int] = defaultdict(int)
    for task in expired:
        user_id = str(task.loyalty_card_id)
        if task.challenge_slot:
            slots_by_user[user_id].append(task.challenge_slot)
        else:
            unknown_slot_count_by_user[user_id] += 1
        logger.info(
            "expire_tasks.expired_task",
            task_id=str(task.id),
            user_id=user_id,
            deadline=task.deadline.isoformat() if task.deadline else None,
            title=task.title,
        )

    for user_id, slots in slots_by_user.items():
        generate_challenges.apply_async(args=[user_id, len(slots), slots], queue="challenges")
    for user_id, count in unknown_slot_count_by_user.items():
        generate_challenges.apply_async(args=[user_id, count], queue="challenges")

    users = set(slots_by_user) | set(unknown_slot_count_by_user)
    logger.info("expire_tasks.done", count=len(expired), users=len(users))
    return {"status": "expired", "count": len(expired), "users": len(users)}
