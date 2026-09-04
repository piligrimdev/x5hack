"""Completion checker: applies one receipt to one task.

Polymorphic on `task_criterion.kind`. Each known kind has a pure-function
checker in CHECKERS_BY_KIND. A task is considered *completed* when
ALL of its criteria return True — logical AND (FR-024).

Unknown kinds (e.g. added to task_criterion by an adapter extension but
without a paired checker) are treated as "never true" — the task simply
cannot be closed. This is FR-024's safety guard: we don't hand out rewards
based on partial validation.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Callable

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from webx5.crud.task import TaskRepository
from webx5.entities.product import Product
from webx5.entities.receipt import Receipt, ReceiptItem
from webx5.entities.task import Task, TaskCriterion
from webx5.utils.forbidden_categories import get_forbidden_categories

logger = structlog.get_logger("task_completion")


# ---------- Kind-specific checkers ----------
def _receipt_lines_with_products(
    session: Session, receipt_id: uuid.UUID
) -> list[tuple[ReceiptItem, Product]]:
    return list(
        session.execute(
            select(ReceiptItem, Product)
            .join(Product, ReceiptItem.product_id == Product.id)
            .where(ReceiptItem.receipt_id == receipt_id)
        ).all()
    )


def _check_item_quantity(
    session: Session,
    task: Task,
    criterion: TaskCriterion,
    receipt: Receipt,
) -> bool:
    """True if this receipt's qualifying items push quantity_current to target.

    Qualifying = matches task.criterion_type/entity AND category not in forbidden.
    Does NOT mutate — a caller (`apply_receipt`) both bumps quantity_current and
    then re-checks via this function.
    """
    forbidden = get_forbidden_categories()
    lines = _receipt_lines_with_products(session, receipt.id)
    target = int(criterion.value_num or task.quantity_target or 1)
    # quantity_current already reflects this receipt if apply_receipt bumped it.
    return task.quantity_current >= target


def _check_spend_threshold_rub(
    session: Session,
    task: Task,
    criterion: TaskCriterion,
    receipt: Receipt,
) -> bool:
    """True if THIS receipt's total paid amount is >= threshold."""
    threshold = Decimal(str(criterion.value_num or 0))
    total_paid = Decimal("0")
    lines = _receipt_lines_with_products(session, receipt.id)
    for ri, _product in lines:
        total_paid += Decimal(str(ri.paid_price)) * Decimal(int(ri.quantity))
    return total_paid >= threshold


CHECKERS_BY_KIND: dict[str, Callable[[Session, Task, TaskCriterion, Receipt], bool]] = {
    "item_quantity": _check_item_quantity,
    "spend_threshold_rub": _check_spend_threshold_rub,
}


class TaskCompletionService:
    def __init__(self, task_repo: TaskRepository) -> None:
        self.task_repo = task_repo

    def _count_matching_quantity(
        self, session: Session, task: Task, receipt: Receipt
    ) -> int:
        """How many qualifying units did this receipt bring for the task's main criterion."""
        forbidden = get_forbidden_categories()
        lines = _receipt_lines_with_products(session, receipt.id)
        total_qty = 0
        for ri, product in lines:
            # Forbidden category → do not count (FR-008)
            category_name = product.category.name if product.category else ""
            if category_name in forbidden:
                continue
            matches = False
            if task.criterion_type == "product" and ri.product_id == task.criterion_entity_id:
                matches = True
            elif task.criterion_type == "category" and product.category_id == task.criterion_entity_id:
                matches = True
            if matches:
                total_qty += int(ri.quantity)
        return total_qty

    def apply_receipt(
        self,
        session: Session,
        task: Task,
        receipt: Receipt,
    ) -> bool:
        """Try to progress `task` with `receipt`. Returns True iff the task
        transitioned to 'выполнено' as a result of this call (i.e. reward is
        due).

        Idempotency: if this receipt was already applied to this task,
        returns False without side effects.
        """
        # 1) Idempotency — try to record the pair; if it already existed → skip.
        recorded = self.task_repo.record_increment(session, task.id, receipt.id)
        if not recorded:
            return False

        # 2) Bump quantity_current based on matching items (for item_quantity kind).
        matching_qty = self._count_matching_quantity(session, task, receipt)
        if matching_qty > 0:
            self.task_repo.bump_progress(session, task, matching_qty)

        # 3) Evaluate all criteria — logical AND.
        criteria = self.task_repo.get_task_criteria(session, task.id)
        if not criteria:
            return False

        for crit in criteria:
            checker = CHECKERS_BY_KIND.get(crit.kind)
            if checker is None:
                logger.warning(
                    "task_completion.unknown_kind",
                    task_id=str(task.id),
                    kind=crit.kind,
                )
                return False
            if not checker(session, task, crit, receipt):
                return False

        # 4) All criteria passed — create reward + mark completed atomically.
        reward = self.task_repo.create_reward_discount(session, task)
        self.task_repo.mark_completed(session, task, reward.id)
        return True
