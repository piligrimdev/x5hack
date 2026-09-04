from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import MagicMock

from webx5.entities.points import PointsAccount, PointsTransaction
from webx5.entities.task import Task
from webx5.services.points import PointsService


def _make_task(reward_rub: str = "50") -> Task:
    t = Task()
    t.id = uuid.uuid4()
    t.loyalty_card_id = uuid.uuid4()
    t.reward_rub = Decimal(reward_rub)
    return t


def _account(loyalty_card_id: uuid.UUID, balance: int = 0) -> PointsAccount:
    a = PointsAccount()
    a.id = uuid.uuid4()
    a.loyalty_card_id = loyalty_card_id
    a.balance = balance
    return a


def test_award_for_task_happy_path() -> None:
    task = _make_task("50")
    account = _account(task.loyalty_card_id)
    repo = MagicMock()
    repo.get_or_create_account.return_value = account
    tx = PointsTransaction()
    tx.id = uuid.uuid4()
    tx.rate_at_time = None
    repo.insert_earn.return_value = tx
    service = PointsService(repo=repo)
    session = MagicMock()

    awarded = service.award_for_task(session, task)

    assert awarded == 50
    repo.get_or_create_account.assert_called_once_with(session, task.loyalty_card_id)
    repo.insert_earn.assert_called_once_with(session, account.id, task.id, 50)
    repo.bump_balance.assert_called_once_with(session, account, 50)
    # rate_at_time is not applied on earn (feature 007 clarification)
    assert repo.insert_earn.call_args.args[3] == 50


def test_award_for_task_reward_zero_is_noop() -> None:
    task = _make_task("0")
    repo = MagicMock()
    service = PointsService(repo=repo)

    awarded = service.award_for_task(MagicMock(), task)

    assert awarded == 0
    repo.get_or_create_account.assert_not_called()
    repo.insert_earn.assert_not_called()
    repo.bump_balance.assert_not_called()


def test_award_for_task_idempotent_when_earn_conflicts() -> None:
    task = _make_task("50")
    account = _account(task.loyalty_card_id, balance=100)
    repo = MagicMock()
    repo.get_or_create_account.return_value = account
    repo.insert_earn.return_value = None  # simulate IntegrityError → duplicate
    service = PointsService(repo=repo)

    awarded = service.award_for_task(MagicMock(), task)

    assert awarded == 0
    repo.bump_balance.assert_not_called()
    assert account.balance == 100  # unchanged


def test_award_for_task_reward_rub_decimal_is_floored() -> None:
    # Decimal("50.99") → 50 points (integer floor)
    task = _make_task("50.99")
    account = _account(task.loyalty_card_id)
    repo = MagicMock()
    repo.get_or_create_account.return_value = account
    repo.insert_earn.return_value = PointsTransaction()
    service = PointsService(repo=repo)
    session = MagicMock()

    awarded = service.award_for_task(session, task)

    assert awarded == 50
    repo.insert_earn.assert_called_once_with(session, account.id, task.id, 50)
