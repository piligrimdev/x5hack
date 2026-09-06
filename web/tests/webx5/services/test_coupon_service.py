from __future__ import annotations

import uuid
from datetime import date
from unittest.mock import MagicMock

from sqlalchemy.exc import IntegrityError

from webx5.entities.coupon import CouponAccount
from webx5.entities.task import Task
from webx5.services.coupon import CouponService


def _account(user_id: uuid.UUID, balance: int = 0) -> CouponAccount:
    a = CouponAccount()
    a.id = uuid.uuid4()
    a.loyalty_card_id = user_id
    a.balance = balance
    return a


def _service(repo: MagicMock, n: int = 3, week: date | None = None) -> CouponService:
    week = week or date(2026, 9, 1)
    return CouponService(repo=repo, weekly_n=lambda: n, week_start=lambda: week)


def test_weekly_grant_idempotent_same_week() -> None:
    user_id = uuid.uuid4()
    account = _account(user_id, 0)
    repo = MagicMock()
    repo.lock_account_for_update.return_value = account
    repo.has_weekly_grant.side_effect = [False, True]
    session = MagicMock()
    service = _service(repo)

    first = service.ensure_weekly_grant(session, user_id)
    second = service.ensure_weekly_grant(session, user_id)

    assert first == 3
    assert second == 0
    repo.bump_balance.assert_called_once_with(session, account, 3)


def test_weekly_grant_n_zero_writes_nothing() -> None:
    user_id = uuid.uuid4()
    account = _account(user_id)
    repo = MagicMock()
    repo.lock_account_for_update.return_value = account
    repo.has_weekly_grant.return_value = False
    service = _service(repo, n=0)

    awarded = service.ensure_weekly_grant(MagicMock(), user_id)

    assert awarded == 0
    repo.insert_transaction.assert_not_called()
    repo.bump_balance.assert_not_called()


def test_weekly_grant_changing_n_does_not_rewrite_existing_pack() -> None:
    user_id = uuid.uuid4()
    account = _account(user_id, 3)
    repo = MagicMock()
    repo.lock_account_for_update.return_value = account
    repo.has_weekly_grant.return_value = True
    service = _service(repo, n=5)

    awarded = service.ensure_weekly_grant(MagicMock(), user_id)

    assert awarded == 0
    repo.bump_balance.assert_not_called()


def test_weekly_grant_missed_week_only_current_week_start() -> None:
    user_id = uuid.uuid4()
    account = _account(user_id, 0)
    repo = MagicMock()
    repo.lock_account_for_update.return_value = account
    repo.has_weekly_grant.return_value = False
    session = MagicMock()
    this_week = date(2026, 9, 8)
    service = CouponService(
        repo=repo, weekly_n=lambda: 3, week_start=lambda: this_week
    )

    awarded = service.ensure_weekly_grant(session, user_id)

    assert awarded == 3
    kwargs = repo.insert_transaction.call_args.kwargs
    assert kwargs["week_start"] == this_week
    assert kwargs["type"] == "weekly_grant"


def test_weekly_grant_integrity_error_is_noop() -> None:
    user_id = uuid.uuid4()
    account = _account(user_id)
    repo = MagicMock()
    repo.lock_account_for_update.return_value = account
    repo.has_weekly_grant.return_value = False
    repo.insert_transaction.side_effect = IntegrityError("x", {}, None)
    session = MagicMock()
    service = _service(repo)

    awarded = service.ensure_weekly_grant(session, user_id)

    assert awarded == 0
    repo.bump_balance.assert_not_called()


def test_debit_for_spin_success_and_deny() -> None:
    user_id = uuid.uuid4()
    spin_id = uuid.uuid4()
    account = _account(user_id, 1)
    repo = MagicMock()
    repo.lock_account_for_update.return_value = account
    service = _service(repo)
    session = MagicMock()

    assert service.debit_for_spin(session, user_id, spin_id) is True
    repo.debit_balance.assert_called_once_with(session, account, 1)

    account.balance = 0
    assert service.debit_for_spin(session, user_id, spin_id) is False


def test_award_for_task_once() -> None:
    task = Task()
    task.id = uuid.uuid4()
    task.loyalty_card_id = uuid.uuid4()
    account = _account(task.loyalty_card_id)
    repo = MagicMock()
    repo.has_task_grant.side_effect = [False, True]
    repo.get_or_create_account.return_value = account
    session = MagicMock()
    service = _service(repo)

    assert service.award_for_task(session, task) == 1
    assert service.award_for_task(session, task) == 0
    repo.bump_balance.assert_called_once_with(session, account, 1)
