"""Celery task: process one receipt.

Responsibilities (US1 slice):
  * Detect "first receipt for user" and enqueue 3-task generation batch.

Extended in US2 to also increment task progress and create rewards.
"""

from __future__ import annotations

import uuid

import structlog
from sqlalchemy import select

from webx5.core.celery_app import celery_app
from webx5.entities.receipt import Receipt
from webx5.entities.user import User

logger = structlog.get_logger("tasks.receipt")


@celery_app.task(name="webx5.tasks.receipt.process_receipt", queue="receipts")
def process_receipt(receipt_id: str) -> dict:
    from webx5.core.challenges import task_completion_service, task_repo
    from webx5.core.db import db
    from webx5.tasks.generation import generate_challenges

    rid = uuid.UUID(receipt_id)
    with db.get_sync_session() as session:
        with session.begin():
            receipt = session.get(Receipt, rid)
            if receipt is None:
                logger.warning("process.receipt_not_found", receipt_id=receipt_id)
                return {"status": "no_op", "reason": "receipt_not_found"}
            if receipt.loyalty_card_id is None:
                return {"status": "no_op", "reason": "anonymous_receipt"}

            user_id = receipt.loyalty_card_id
            # Pessimistic user-level lock (FR-014).
            session.execute(select(User).where(User.id == user_id).with_for_update()).scalar_one()

            active = task_repo.get_active_for_user(session, user_id)

            # First-receipt trigger (R9): no active tasks → generate 3.
            if not active:
                generate_challenges.apply_async(args=[str(user_id), 3], queue="challenges")
                return {"status": "first_receipt_generation_enqueued", "user_id": str(user_id)}

            # US2: increment progress + reward.
            completed_count = 0
            for task in active:
                if task_completion_service.apply_receipt(session, task, receipt):
                    completed_count += 1

            # Enqueue replacements (one per completed task).
            for _ in range(completed_count):
                generate_challenges.apply_async(args=[str(user_id), 1], queue="challenges")

            return {
                "status": "processed",
                "user_id": str(user_id),
                "active_count": len(active),
                "completed_count": completed_count,
            }
