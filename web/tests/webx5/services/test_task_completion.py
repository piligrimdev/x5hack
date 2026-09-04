"""Unit tests for TaskCompletionService and its polymorphic checkers.

Uses MagicMock in place of a real DB session — targets pure logic:
  * item_quantity checker returns True only when quantity_current >= target
  * spend_threshold_rub checker sums receipt line paid_price × qty vs threshold
  * unknown kind is treated as never-true (FR-024 safety)
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from webx5.entities.product import Product
from webx5.entities.receipt import Receipt, ReceiptItem
from webx5.entities.task import Task, TaskCriterion
from webx5.services.task_completion import (
    CHECKERS_BY_KIND,
    TaskCompletionService,
    _check_item_quantity,
    _check_spend_threshold_rub,
)


def _make_task(*, quantity_current: int = 0, quantity_target: int = 1) -> Task:
    t = Task()
    t.id = uuid.uuid4()
    t.loyalty_card_id = uuid.uuid4()
    t.quantity_current = quantity_current
    t.quantity_target = quantity_target
    t.criterion_type = "category"
    t.criterion_entity_id = uuid.uuid4()
    t.mechanic = "test"
    return t


def _make_criterion(kind: str, value_num: Decimal | None = None) -> TaskCriterion:
    c = TaskCriterion()
    c.id = uuid.uuid4()
    c.kind = kind
    c.value_num = value_num
    return c


def _make_receipt() -> Receipt:
    r = Receipt()
    r.id = uuid.uuid4()
    return r


def test_item_quantity_checker_returns_true_when_current_meets_target():
    task = _make_task(quantity_current=2, quantity_target=2)
    crit = _make_criterion("item_quantity", Decimal("2"))
    with patch("webx5.services.task_completion.get_forbidden_categories", return_value=frozenset()):
        assert _check_item_quantity(MagicMock(), task, crit, _make_receipt()) is True


def test_item_quantity_checker_returns_false_when_below_target():
    task = _make_task(quantity_current=0, quantity_target=2)
    crit = _make_criterion("item_quantity", Decimal("2"))
    with patch("webx5.services.task_completion.get_forbidden_categories", return_value=frozenset()):
        assert _check_item_quantity(MagicMock(), task, crit, _make_receipt()) is False


def test_spend_threshold_checker_true_when_receipt_total_ge_threshold():
    task = _make_task()
    crit = _make_criterion("spend_threshold_rub", Decimal("1500"))
    session = MagicMock()

    ri = ReceiptItem()
    ri.paid_price = Decimal("800")
    ri.quantity = 2  # total 1600 >= 1500
    product = Product()

    with patch(
        "webx5.services.task_completion._receipt_lines_with_products",
        return_value=[(ri, product)],
    ):
        assert _check_spend_threshold_rub(session, task, crit, _make_receipt()) is True


def test_spend_threshold_checker_false_when_below():
    task = _make_task()
    crit = _make_criterion("spend_threshold_rub", Decimal("2000"))
    session = MagicMock()

    ri = ReceiptItem()
    ri.paid_price = Decimal("500")
    ri.quantity = 1

    with patch(
        "webx5.services.task_completion._receipt_lines_with_products",
        return_value=[(ri, Product())],
    ):
        assert _check_spend_threshold_rub(session, task, crit, _make_receipt()) is False


def test_unknown_kind_is_never_completable_fr024_safety():
    """FR-024: task with an unrecognized criterion.kind cannot be closed."""
    task = _make_task()
    unknown_crit = _make_criterion("some_future_kind_not_registered", Decimal("42"))

    task_repo = MagicMock()
    task_repo.record_increment.return_value = True
    task_repo.get_task_criteria.return_value = [unknown_crit]

    service = TaskCompletionService(task_repo=task_repo)
    with patch(
        "webx5.services.task_completion.TaskCompletionService._count_matching_quantity",
        return_value=0,
    ):
        result = service.apply_receipt(MagicMock(), task, _make_receipt())
    assert result is False


def test_apply_receipt_idempotent_when_already_recorded():
    task = _make_task()
    task_repo = MagicMock()
    task_repo.record_increment.return_value = False  # already recorded → skip

    service = TaskCompletionService(task_repo=task_repo)
    assert service.apply_receipt(MagicMock(), task, _make_receipt()) is False
    task_repo.bump_progress.assert_not_called()
    task_repo.mark_completed.assert_not_called()


def test_checkers_registry_covers_known_kinds():
    assert "item_quantity" in CHECKERS_BY_KIND
    assert "spend_threshold_rub" in CHECKERS_BY_KIND
