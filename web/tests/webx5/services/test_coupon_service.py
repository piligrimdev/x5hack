from __future__ import annotations

import uuid
from unittest.mock import MagicMock

from webx5.entities.coupon import CouponAccount
from webx5.services.coupon import CouponService


def _account(
    user_id: uuid.UUID, balance: int = 0, remainder: int = 0
) -> CouponAccount:
    a = CouponAccount()
    a.id = uuid.uuid4()
    a.loyalty_card_id = user_id
    a.balance = balance
    a.spend_remainder_rub = remainder
    return a


def test_debit_for_spin_success_and_deny() -> None:
    user_id = uuid.uuid4()
    spin_id = uuid.uuid4()
    account = _account(user_id, 1)
    repo = MagicMock()
    repo.lock_account_for_update.return_value = account
    service = CouponService(repo=repo)
    session = MagicMock()

    assert service.debit_for_spin(session, user_id, spin_id) is True
    repo.debit_balance.assert_called_once_with(session, account, 1)

    account.balance = 0
    assert service.debit_for_spin(session, user_id, spin_id) is False


def test_award_for_referral_skips_zero_and_awards() -> None:
    user_id = uuid.uuid4()
    link_id = uuid.uuid4()
    account = _account(user_id, 0)
    repo = MagicMock()
    repo.lock_account_for_update.return_value = account
    session = MagicMock()
    service = CouponService(repo=repo)

    assert service.award_for_referral(session, user_id, 0, link_id) == 0
    repo.insert_transaction.assert_not_called()

    assert service.award_for_referral(session, user_id, 2, link_id) == 2
    repo.bump_balance.assert_called_once_with(session, account, 2)


def test_award_for_purchase_thresholds() -> None:
    user_id = uuid.uuid4()
    receipt_id = uuid.uuid4()
    account = _account(user_id, remainder=400)
    repo = MagicMock()
    repo.lock_account_for_update.return_value = account
    repo.has_purchase_grant.return_value = False
    session = MagicMock()
    service = CouponService(repo=repo)

    assert service.award_for_purchase(session, user_id, 500, receipt_id) == 0
    repo.insert_transaction.assert_not_called()
    repo.bump_balance.assert_not_called()
    assert account.spend_remainder_rub == 900

    assert service.award_for_purchase(session, user_id, 2500, uuid.uuid4()) == 3
    repo.bump_balance.assert_called_once()
    assert repo.bump_balance.call_args.args[2] == 3
    assert account.spend_remainder_rub == 400


def test_award_for_purchase_skips_zero_and_duplicate() -> None:
    user_id = uuid.uuid4()
    receipt_id = uuid.uuid4()
    account = _account(user_id)
    repo = MagicMock()
    repo.lock_account_for_update.return_value = account
    repo.has_purchase_grant.return_value = True
    session = MagicMock()
    service = CouponService(repo=repo)

    assert service.award_for_purchase(session, user_id, 0, receipt_id) == 0
    repo.lock_account_for_update.assert_not_called()

    assert service.award_for_purchase(session, user_id, 1000, receipt_id) == 0
    repo.insert_transaction.assert_not_called()
    repo.bump_balance.assert_not_called()
