from __future__ import annotations

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


def test_completion_awards_coupon_with_points() -> None:
    task = _make_task()
    task_repo = MagicMock()
    task_repo.record_increment.return_value = True
    task_repo.get_task_criteria.return_value = [_make_criterion()]
    task_item_repo = MagicMock()
    task_item_repo.get_items_for_task.return_value = []
    service = TaskCompletionService(task_repo=task_repo, task_item_repo=task_item_repo)
    session = MagicMock()
    fake_points = MagicMock()
    fake_coupons = MagicMock()
    fake_coupons.award_for_task.return_value = 1

    with patch(
        "webx5.services.task_completion.TaskCompletionService._count_matching_quantity",
        return_value=2,
    ), patch(
        "webx5.core.points.points_service", fake_points
    ), patch(
        "webx5.core.wheel.coupon_service", fake_coupons
    ), patch.dict(
        "webx5.services.task_completion.CHECKERS_BY_KIND",
        {"item_quantity": lambda s, t, c, r: True},
        clear=False,
    ):
        result = service.apply_receipt(session, task, Receipt())

    assert result is True
    fake_points.award_for_task.assert_called_once_with(session, task)
    fake_coupons.award_for_task.assert_called_once_with(session, task)


def test_completion_coupon_idempotent_via_service() -> None:
    from webx5.entities.coupon import CouponAccount
    from webx5.services.coupon import CouponService

    task = _make_task()
    account = CouponAccount()
    account.id = uuid.uuid4()
    account.loyalty_card_id = task.loyalty_card_id
    account.balance = 0
    repo = MagicMock()
    repo.has_task_grant.side_effect = [False] + [True] * 99
    repo.get_or_create_account.return_value = account
    service = CouponService(
        repo=repo, weekly_n=lambda: 3, week_start=lambda: None
    )
    session = MagicMock()

    awards = [service.award_for_task(session, task) for _ in range(100)]

    assert awards[0] == 1
    assert all(a == 0 for a in awards[1:])
    assert repo.bump_balance.call_count == 1


def test_expiration_path_does_not_award_coupon() -> None:
    """Expiration sweep must not import or call coupon awarding."""
    import inspect

    from webx5.tasks import expiration

    source = inspect.getsource(expiration)
    assert "coupon_service" not in source
    assert "award_for_task" not in source
