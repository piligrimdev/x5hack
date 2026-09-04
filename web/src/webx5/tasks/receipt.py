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

    logger.info("process_receipt.enter", receipt_id=receipt_id)

    rid = uuid.UUID(receipt_id)
    with db.get_sync_session() as session:
        with session.begin():
            receipt = session.get(Receipt, rid)
            if receipt is None:
                logger.warning("process_receipt.receipt_not_found", receipt_id=receipt_id)
                return {"status": "no_op", "reason": "receipt_not_found"}
            if receipt.loyalty_card_id is None:
                logger.info("process_receipt.anonymous", receipt_id=receipt_id, store_id=str(receipt.store_id))
                return {"status": "no_op", "reason": "anonymous_receipt"}

            user_id = receipt.loyalty_card_id
            logger.info(
                "process_receipt.locked_user",
                receipt_id=receipt_id,
                user_id=str(user_id),
                store_id=str(receipt.store_id),
                purchase_date=receipt.purchase_date.isoformat() if receipt.purchase_date else None,
            )
            # Pessimistic user-level lock (FR-014).
            session.execute(select(User).where(User.id == user_id).with_for_update()).scalar_one()

            active = task_repo.get_active_for_user(session, user_id)
            logger.info(
                "process_receipt.active_tasks",
                receipt_id=receipt_id,
                user_id=str(user_id),
                active_count=len(active),
                active_task_ids=[str(t.id) for t in active],
            )

            # First-receipt trigger (R9): no active tasks → generate 3.
            if not active:
                logger.info(
                    "process_receipt.first_receipt_trigger",
                    user_id=str(user_id),
                    receipt_id=receipt_id,
                )
                generate_challenges.apply_async(args=[str(user_id), 3], queue="challenges")
                return {"status": "first_receipt_generation_enqueued", "user_id": str(user_id)}

            # US2: increment progress + reward.
            completed_count = 0
            for task in active:
                did_complete = task_completion_service.apply_receipt(session, task, receipt)
                logger.info(
                    "process_receipt.task_progress",
                    task_id=str(task.id),
                    receipt_id=receipt_id,
                    user_id=str(user_id),
                    criterion_type=task.criterion_type,
                    quantity_current=task.quantity_current,
                    quantity_target=task.quantity_target,
                    completed=did_complete,
                )
                if did_complete:
                    completed_count += 1

            # Enqueue replacements (one per completed task).
            for _ in range(completed_count):
                generate_challenges.apply_async(args=[str(user_id), 1], queue="challenges")

            logger.info(
                "process_receipt.done",
                receipt_id=receipt_id,
                user_id=str(user_id),
                active_count=len(active),
                completed_count=completed_count,
            )
            return {
                "status": "processed",
                "user_id": str(user_id),
                "active_count": len(active),
                "completed_count": completed_count,
            }
