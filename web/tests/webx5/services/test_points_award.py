from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

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
    repo.get_rate.return_value = 10
    repo.get_or_create_account.return_value = account
    tx = PointsTransaction()
    tx.id = uuid.uuid4()
    tx.rate_at_time = None
    repo.insert_earn.return_value = tx
    service = PointsService(repo=repo)
    session = MagicMock()

    awarded = service.award_for_task(session, task)

    # reward_rub=50, rate=10 -> 50*10=500, already a multiple of 10
    assert awarded == 500
    repo.get_rate.assert_called_once_with(session)
    repo.get_or_create_account.assert_called_once_with(session, task.loyalty_card_id)
    repo.insert_earn.assert_called_once_with(session, account.id, task.id, 500)
    repo.bump_balance.assert_called_once_with(session, account, 500)
    # rate_at_time is not applied on earn (feature 007 clarification)
    assert repo.insert_earn.call_args.args[3] == 500


def test_award_for_task_reward_zero_is_noop() -> None:
    task = _make_task("0")
    repo = MagicMock()
    repo.get_rate.return_value = 10
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
    repo.get_rate.return_value = 10
    repo.get_or_create_account.return_value = account
    repo.insert_earn.return_value = None  # simulate IntegrityError → duplicate
    service = PointsService(repo=repo)

    awarded = service.award_for_task(MagicMock(), task)

    assert awarded == 0
    repo.bump_balance.assert_not_called()
    assert account.balance == 100  # unchanged


@pytest.mark.parametrize(("reward_rub", "expected"), [("50.99", 510), ("55", 550), ("33.33", 330)])
def test_award_for_task_reward_rub_scaled_and_rounded_to_nearest_10(reward_rub: str, expected: int) -> None:
    task = _make_task(reward_rub)
    account = _account(task.loyalty_card_id)
    repo = MagicMock()
    repo.get_rate.return_value = 10
    repo.get_or_create_account.return_value = account
    repo.insert_earn.return_value = PointsTransaction()
    service = PointsService(repo=repo)
    session = MagicMock()

    awarded = service.award_for_task(session, task)

    assert awarded == expected
    repo.insert_earn.assert_called_once_with(session, account.id, task.id, expected)


def test_award_for_task_uses_configured_rate() -> None:
    # reward_rub=20 at rate=5 -> 20*5=100, already a multiple of 10
    task = _make_task("20")
    account = _account(task.loyalty_card_id)
    repo = MagicMock()
    repo.get_rate.return_value = 5
    repo.get_or_create_account.return_value = account
    repo.insert_earn.return_value = PointsTransaction()
    service = PointsService(repo=repo)
    session = MagicMock()

    awarded = service.award_for_task(session, task)

    assert awarded == 100
    repo.insert_earn.assert_called_once_with(session, account.id, task.id, 100)
