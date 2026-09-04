"""Feature 007 US3: preview_for_calculate is read-only and returns cashback estimate.

Verifies:
- anonymous (loyalty_card_id=None) → returns None (no cashback block for anon);
- user with balance → returns preview with correct fields;
- preview is read-only: no calls to deduct_balance / insert_spend;
- points_requested='all' → uses full balance;
- points_requested None or 0 → applied_points=0 but preview still populated.
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

from webx5.entities.points import PointsAccount
from webx5.services.points import PointsService


def _account(balance: int = 500) -> PointsAccount:
    a = PointsAccount()
    a.id = uuid.uuid4()
    a.loyalty_card_id = uuid.uuid4()
    a.balance = balance
    return a


def test_preview_returns_none_for_anonymous():
    repo = MagicMock()
    svc = PointsService(repo=repo)

    preview = svc.preview_for_calculate(
        MagicMock(), loyalty_card_id=None, points_requested_raw="all", subtotal_rub=500
    )

    assert preview is None
    repo.get_or_create_account.assert_not_called()


def test_preview_happy_path_all_within_balance():
    account = _account(balance=500)
    repo = MagicMock()
    repo.get_rate.return_value = 10
    repo.get_or_create_account.return_value = account
    svc = PointsService(repo=repo)

    preview = svc.preview_for_calculate(
        MagicMock(),
        loyalty_card_id=account.loyalty_card_id,
        points_requested_raw="all",
        subtotal_rub=200,
    )

    assert preview is not None
    assert preview.points_available == 500
    assert preview.points_to_apply == 500
    assert preview.cashback_rub == 50
    assert preview.total_paid_rub == 150
    assert preview.points_balance_after == 0
    assert preview.points_capped_by == "none"
    assert preview.rate_points_per_rub == 10
    # read-only: no mutations
    repo.deduct_balance.assert_not_called()
    repo.insert_spend.assert_not_called()
    repo.lock_account_for_update.assert_not_called()


def test_preview_capped_by_receipt_total():
    # balance huge, subtotal small
    account = _account(balance=10000)
    repo = MagicMock()
    repo.get_rate.return_value = 10
    repo.get_or_create_account.return_value = account
    svc = PointsService(repo=repo)

    preview = svc.preview_for_calculate(
        MagicMock(),
        loyalty_card_id=account.loyalty_card_id,
        points_requested_raw=8000,
        subtotal_rub=500,
    )

    assert preview.points_to_apply == 5000  # 500 rub * 10 rate
    assert preview.cashback_rub == 500
    assert preview.total_paid_rub == 0
    assert preview.points_capped_by == "receipt_total"


def test_preview_zero_when_no_points_requested():
    account = _account(balance=500)
    repo = MagicMock()
    repo.get_rate.return_value = 10
    repo.get_or_create_account.return_value = account
    svc = PointsService(repo=repo)

    preview = svc.preview_for_calculate(
        MagicMock(),
        loyalty_card_id=account.loyalty_card_id,
        points_requested_raw=None,
        subtotal_rub=200,
    )

    assert preview.points_available == 500
    assert preview.points_to_apply == 0
    assert preview.cashback_rub == 0
    assert preview.total_paid_rub == 200
    assert preview.points_balance_after == 500


def test_preview_empty_account_returns_zero_apply():
    account = _account(balance=0)
    repo = MagicMock()
    repo.get_rate.return_value = 10
    repo.get_or_create_account.return_value = account
    svc = PointsService(repo=repo)

    preview = svc.preview_for_calculate(
        MagicMock(),
        loyalty_card_id=account.loyalty_card_id,
        points_requested_raw="all",
        subtotal_rub=500,
    )

    assert preview.points_available == 0
    assert preview.points_to_apply == 0
    assert preview.cashback_rub == 0
    assert preview.total_paid_rub == 500
