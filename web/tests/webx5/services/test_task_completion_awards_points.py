"""Feature 007: closing a task must award points (not create Discount).

Focused on the integration point in TaskCompletionService.apply_receipt:
when all criteria pass, the code calls points_service.award_for_task +
mark_completed_without_reward (instead of create_reward_discount + mark_completed).

Idempotency of the award itself is covered in test_points_award.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import MagicMock, patch

from webx5.entities.receipt import Receipt
from webx5.entities.task import Task, TaskCriterion
from webx5.services.task_completion import TaskCompletionService


def _make_task(reward_rub: str = "50") -> Task:
    t = Task()
    t.id = uuid.uuid4()
    t.loyalty_card_id = uuid.uuid4()
    t.quantity_current = 2
    t.quantity_target = 2
    t.criterion_type = "product"
    t.criterion_entity_id = uuid.uuid4()
    t.mechanic = "test"
    t.reward_rub = Decimal(reward_rub)
    return t


def _make_criterion(kind: str = "item_quantity", value_num: str = "2") -> TaskCriterion:
    c = TaskCriterion()
    c.id = uuid.uuid4()
    c.kind = kind
    c.value_num = Decimal(value_num)
    return c


def _make_receipt() -> Receipt:
    r = Receipt()
    r.id = uuid.uuid4()
    return r


def test_completion_awards_points_and_marks_completed_without_reward():
    task = _make_task("50")
    crit = _make_criterion()
    task_repo = MagicMock()
    task_repo.record_increment.return_value = True
    task_repo.get_task_criteria.return_value = [crit]

    fake_points_service = MagicMock()
    fake_points_service.award_for_task.return_value = 50

    service = TaskCompletionService(task_repo=task_repo)
    session = MagicMock()

    with patch(
        "webx5.services.task_completion.TaskCompletionService._count_matching_quantity",
        return_value=2,
    ), patch(
        "webx5.core.points.points_service", fake_points_service
    ), patch.dict(
        "webx5.services.task_completion.CHECKERS_BY_KIND",
        {"item_quantity": lambda s, t, c, r: True},
        clear=False,
    ):
        result = service.apply_receipt(session, task, _make_receipt())

    assert result is True
    fake_points_service.award_for_task.assert_called_once_with(session, task)
    task_repo.mark_completed_without_reward.assert_called_once_with(session, task)
    # Legacy Discount path MUST NOT be invoked
    task_repo.create_reward_discount.assert_not_called()
    task_repo.mark_completed.assert_not_called()
