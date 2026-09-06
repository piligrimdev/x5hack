"""Unit tests for composite task progress via task_item rows.

Covers:
  * Partial item completion does NOT complete the task
  * Items matching different criteria each get independent progress bumps
  * All items complete + criteria pass → task marked completed
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from webx5.entities.receipt import Receipt, ReceiptItem
from webx5.entities.task import Task, TaskCriterion, TaskItem
from webx5.services.task_completion import TaskCompletionService


# ---------- helpers ----------

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


def _make_task_item(
    *,
    task_id: uuid.UUID,
    criterion_type: str = "category",
    criterion_entity_id: uuid.UUID | None = None,
    quantity_target: int = 2,
    quantity_current: int = 0,
    label: str | None = None,
) -> TaskItem:
    item = TaskItem()
    item.id = uuid.uuid4()
    item.task_id = task_id
    item.criterion_type = criterion_type
    item.criterion_entity_id = criterion_entity_id or uuid.uuid4()
    item.quantity_target = quantity_target
    item.quantity_current = quantity_current
    item.label = label
    return item


def _make_receipt() -> Receipt:
    r = Receipt()
    r.id = uuid.uuid4()
    return r


def _make_service(
    task_repo: MagicMock,
    task_item_repo: MagicMock,
) -> TaskCompletionService:
    return TaskCompletionService(task_repo=task_repo, task_item_repo=task_item_repo)


# ---------- tests ----------

class TestPartialItemCompletion:
    def test_partial_item_progress_does_not_complete_task(self) -> None:
        """When task_item records exist but not all are complete, apply_receipt returns False."""
        task = _make_task(quantity_current=2, quantity_target=2)
        receipt = _make_receipt()

        item_complete = _make_task_item(
            task_id=task.id, quantity_target=2, quantity_current=2
        )
        item_incomplete = _make_task_item(
            task_id=task.id, quantity_target=3, quantity_current=1
        )

        task_repo = MagicMock()
        task_repo.record_increment.return_value = True
        task_repo.get_task_criteria.return_value = [
            _make_criterion("item_quantity", Decimal("2"))
        ]

        task_item_repo = MagicMock()
        task_item_repo.get_items_for_task.return_value = [item_complete, item_incomplete]
        # all_items_complete returns False because item_incomplete is not done
        task_item_repo.all_items_complete.return_value = False

        service = _make_service(task_repo, task_item_repo)

        with patch(
            "webx5.services.task_completion.TaskCompletionService._count_matching_quantity",
            return_value=1,
        ), patch(
            "webx5.services.task_completion.TaskCompletionService._count_matching_for_criterion",
            return_value=0,
        ):
            result = service.apply_receipt(MagicMock(), task, receipt)

        assert result is False
        task_repo.mark_completed_without_reward.assert_not_called()


class TestParallelItemProgress:
    def test_items_with_different_criteria_each_get_progress(self) -> None:
        """Each task_item is checked independently — different entity IDs each match separately."""
        task = _make_task(quantity_current=0, quantity_target=1)
        receipt = _make_receipt()

        category_id_a = uuid.uuid4()
        category_id_b = uuid.uuid4()

        item_a = _make_task_item(
            task_id=task.id,
            criterion_type="category",
            criterion_entity_id=category_id_a,
            quantity_target=1,
            quantity_current=0,
        )
        item_b = _make_task_item(
            task_id=task.id,
            criterion_type="category",
            criterion_entity_id=category_id_b,
            quantity_target=1,
            quantity_current=0,
        )

        task_repo = MagicMock()
        task_repo.record_increment.return_value = True
        task_repo.get_task_criteria.return_value = [
            _make_criterion("item_quantity", Decimal("1"))
        ]

        task_item_repo = MagicMock()
        task_item_repo.get_items_for_task.return_value = [item_a, item_b]
        # Both items complete after bumps
        task_item_repo.all_items_complete.return_value = True

        # _count_matching_for_criterion returns 1 for each item's criterion
        def _count_for_criterion(session, criterion_type, criterion_entity_id, receipt):
            if criterion_entity_id in (category_id_a, category_id_b):
                return 1
            return 0

        service = _make_service(task_repo, task_item_repo)

        with patch(
            "webx5.services.task_completion.TaskCompletionService._count_matching_quantity",
            return_value=1,
        ), patch(
            "webx5.services.task_completion.TaskCompletionService._count_matching_for_criterion",
            side_effect=_count_for_criterion,
        ), patch(
            "webx5.services.task_completion.get_forbidden_categories",
            return_value=frozenset(),
        ), patch("webx5.core.points.points_service") as mock_points, patch(
            "webx5.core.wheel.coupon_service"
        ):
            result = service.apply_receipt(MagicMock(), task, receipt)

        # bump_item_progress called once for each item
        assert task_item_repo.bump_item_progress.call_count == 2


class TestAllItemsCompleteTask:
    def test_all_items_complete_and_criteria_pass_marks_task_completed(self) -> None:
        """When all task_item records are complete and criteria pass, task is marked completed."""
        task = _make_task(quantity_current=2, quantity_target=2)
        receipt = _make_receipt()

        item = _make_task_item(
            task_id=task.id, quantity_target=2, quantity_current=2
        )

        task_repo = MagicMock()
        task_repo.record_increment.return_value = True
        task_repo.get_task_criteria.return_value = [
            _make_criterion("item_quantity", Decimal("2"))
        ]

        task_item_repo = MagicMock()
        task_item_repo.get_items_for_task.return_value = [item]
        task_item_repo.all_items_complete.return_value = True

        service = _make_service(task_repo, task_item_repo)

        with patch(
            "webx5.services.task_completion.TaskCompletionService._count_matching_quantity",
            return_value=0,
        ), patch(
            "webx5.services.task_completion.TaskCompletionService._count_matching_for_criterion",
            return_value=0,
        ), patch(
            "webx5.services.task_completion.get_forbidden_categories",
            return_value=frozenset(),
        ), patch("webx5.core.points.points_service") as mock_points, patch(
            "webx5.core.wheel.coupon_service"
        ):
            result = service.apply_receipt(MagicMock(), task, receipt)

        assert result is True
        task_repo.mark_completed_without_reward.assert_called_once()

    def test_no_task_items_bypasses_item_check_and_uses_criteria_only(self) -> None:
        """If there are no task_item rows, the item completeness gate is skipped."""
        task = _make_task(quantity_current=0, quantity_target=1)
        receipt = _make_receipt()

        task_repo = MagicMock()
        task_repo.record_increment.return_value = True
        # No criteria → returns False (existing behaviour)
        task_repo.get_task_criteria.return_value = []

        task_item_repo = MagicMock()
        task_item_repo.get_items_for_task.return_value = []
        task_item_repo.all_items_complete.return_value = False

        service = _make_service(task_repo, task_item_repo)

        with patch(
            "webx5.services.task_completion.TaskCompletionService._count_matching_quantity",
            return_value=0,
        ), patch(
            "webx5.services.task_completion.TaskCompletionService._count_matching_for_criterion",
            return_value=0,
        ):
            result = service.apply_receipt(MagicMock(), task, receipt)

        assert result is False
        # all_items_complete must NOT be called when items list is empty
        task_item_repo.all_items_complete.assert_not_called()
