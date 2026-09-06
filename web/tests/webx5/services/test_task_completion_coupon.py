from __future__ import annotations

import inspect
import uuid
from decimal import Decimal
from unittest.mock import MagicMock, patch

from webx5.entities.receipt import Receipt
from webx5.entities.task import Task, TaskCriterion
from webx5.services.task_completion import TaskCompletionService


def _make_task() -> Task:
    t = Task()
    t.id = uuid.uuid4()
    t.loyalty_card_id = uuid.uuid4()
    t.quantity_current = 2
    t.quantity_target = 2
    t.criterion_type = "product"
    t.criterion_entity_id = uuid.uuid4()
    t.mechanic = "test"
    t.reward_rub = Decimal("50")
    t.reward_type = "cashback"
    return t


def _make_criterion() -> TaskCriterion:
    c = TaskCriterion()
    c.id = uuid.uuid4()
    c.kind = "item_quantity"
    c.value_num = Decimal("2")
    return c


def test_completion_does_not_award_coupon() -> None:
    task = _make_task()
    task_repo = MagicMock()
    task_repo.record_increment.return_value = True
    task_repo.get_task_criteria.return_value = [_make_criterion()]
    task_item_repo = MagicMock()
    task_item_repo.get_items_for_task.return_value = []
    service = TaskCompletionService(task_repo=task_repo, task_item_repo=task_item_repo)
    session = MagicMock()
    fake_points = MagicMock()

    with patch(
        "webx5.services.task_completion.TaskCompletionService._count_matching_quantity",
        return_value=2,
    ), patch(
        "webx5.core.points.points_service", fake_points
    ), patch.dict(
        "webx5.services.task_completion.CHECKERS_BY_KIND",
        {"item_quantity": lambda s, t, c, r: True},
        clear=False,
    ):
        result = service.apply_receipt(session, task, Receipt())

    assert result is True
    fake_points.award_for_task.assert_called_once_with(session, task)
    source = inspect.getsource(TaskCompletionService.apply_receipt)
    assert "coupon_service" not in source


def test_expiration_path_does_not_award_coupon() -> None:
    """Expiration sweep must not import or call coupon awarding."""
    from webx5.tasks import expiration

    source = inspect.getsource(expiration)
    assert "coupon_service" not in source
    assert "award_for_task" not in source
