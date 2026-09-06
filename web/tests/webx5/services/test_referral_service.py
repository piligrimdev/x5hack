from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import pytest
from fastapi import HTTPException

from webx5.entities.referral import ReferralCode, ReferralLink
from webx5.services.referral import (
    ERR_ACTIVE,
    ERR_NOT_FOUND,
    ERR_RECENT,
    ERR_SELF,
    ERR_USED,
    ReferralService,
)

TZ = ZoneInfo("Europe/Moscow")
NOW = datetime(2026, 9, 6, 18, 0, tzinfo=TZ)


def _code(inviter_id: uuid.UUID, value: str = "AbC12x") -> ReferralCode:
    row = ReferralCode()
    row.id = uuid.uuid4()
    row.code = value
    row.inviter_id = inviter_id
    row.created_at = NOW
    return row


def _link(
    *,
    inviter_id: uuid.UUID,
    invitee_id: uuid.UUID,
    status: str = "awaiting_purchase",
    window_until: datetime | None = None,
) -> ReferralLink:
    link = ReferralLink()
    link.id = uuid.uuid4()
    link.referral_code_id = uuid.uuid4()
    link.inviter_id = inviter_id
    link.invitee_id = invitee_id
    link.activated_at = NOW
    link.discount_percent = Decimal("10")
    link.inviter_coupons = 2
    link.inviter_cashback_rub = 50
    link.discount_valid_to = window_until or (NOW + timedelta(days=7))
    link.purchase_window_until = window_until or (NOW + timedelta(days=7))
    link.reward_status = status
    return link


def _service(repo: MagicMock) -> ReferralService:
    discount_type = MagicMock()
    discount_type.id = uuid.uuid4()
    link_type = MagicMock()
    link_type.id = uuid.uuid4()
    discount_repo = MagicMock()
    discount_repo.get_type_by_name.return_value = discount_type
    discount_repo.get_link_type_by_name.return_value = link_type
    return ReferralService(
        repo=repo,
        discount_repo=discount_repo,
        coupon_service=MagicMock(),
        points_service=MagicMock(),
        settings=lambda: (Decimal("10"), 2, 50),
        clock=lambda _now=None: NOW,
    )


def test_issue_two_codes_are_different_and_six_alnum() -> None:
    repo = MagicMock()
    issued: list[str] = []

    def insert(_session, _inviter, code: str):
        issued.append(code)
        return _code(uuid.uuid4(), code)

    repo.insert_code.side_effect = insert
    service = _service(repo)
    session = MagicMock()
    session.begin_nested.return_value = MagicMock()
    inviter = uuid.uuid4()

    first = service.issue(session, inviter)
    second = service.issue(session, inviter)

    assert first.code != second.code
    for value in issued:
        assert len(value) == 6
        assert all(ch.isalnum() and ch.isascii() for ch in value)


def test_activate_new_user_creates_link() -> None:
    inviter = uuid.uuid4()
    invitee = uuid.uuid4()
    code = _code(inviter, "AbC12x")
    repo = MagicMock()
    repo.lock_code_for_update.return_value = code
    repo.get_link_by_code_id.return_value = None
    repo.get_active_link_for_invitee.return_value = None
    repo.insert_link.side_effect = lambda _s, link: link
    service = _service(repo)
    session = MagicMock()

    session.begin_nested.return_value = MagicMock()
    link = service.activate(session, invitee, "AbC12x", is_new_user=True)

    assert link.inviter_id == inviter
    assert link.invitee_id == invitee
    assert link.reward_status == "awaiting_purchase"
    assert link.inviter_coupons == 2
    repo.has_recent_receipt.assert_not_called()
    session.add.assert_called()
    repo.insert_code.assert_called_once()
    assert repo.insert_code.call_args.args[1] == inviter


def test_activate_issues_new_code_for_inviter() -> None:
    inviter = uuid.uuid4()
    invitee = uuid.uuid4()
    code = _code(inviter, "AbC12x")
    repo = MagicMock()
    repo.lock_code_for_update.return_value = code
    repo.get_link_by_code_id.return_value = None
    repo.get_active_link_for_invitee.return_value = None
    repo.insert_link.side_effect = lambda _s, link: link
    repo.insert_code.side_effect = lambda _s, _inviter, value: _code(inviter, value)
    service = _service(repo)
    session = MagicMock()
    session.begin_nested.return_value = MagicMock()

    service.activate(session, invitee, "AbC12x", is_new_user=True)

    repo.insert_code.assert_called_once()
    assert repo.insert_code.call_args.args[1] == inviter
    replacement = repo.insert_code.call_args.args[2]
    assert replacement != "AbC12x"
    assert len(replacement) == 6


def test_activate_rejects_used_code() -> None:
    inviter = uuid.uuid4()
    repo = MagicMock()
    repo.lock_code_for_update.return_value = _code(inviter)
    repo.get_link_by_code_id.return_value = _link(inviter_id=inviter, invitee_id=uuid.uuid4())
    service = _service(repo)

    with pytest.raises(HTTPException) as exc:
        service.activate(MagicMock(), uuid.uuid4(), "AbC12x", is_new_user=True)
    assert exc.value.status_code == 409
    assert exc.value.detail == ERR_USED
    repo.insert_link.assert_not_called()


def test_activate_case_sensitive_lookup() -> None:
    repo = MagicMock()
    repo.lock_code_for_update.return_value = None
    service = _service(repo)

    session = MagicMock()
    with pytest.raises(HTTPException) as exc:
        service.activate(session, uuid.uuid4(), "abc12x", is_new_user=True)
    assert exc.value.detail == ERR_NOT_FOUND
    repo.lock_code_for_update.assert_called_once_with(session, "abc12x")


def test_activate_rejects_self_invite() -> None:
    user = uuid.uuid4()
    repo = MagicMock()
    repo.lock_code_for_update.return_value = _code(user)
    repo.get_link_by_code_id.return_value = None
    service = _service(repo)

    with pytest.raises(HTTPException) as exc:
        service.activate(MagicMock(), user, "AbC12x", is_new_user=False)
    assert exc.value.detail == ERR_SELF
    repo.insert_link.assert_not_called()


def test_activate_rejects_recent_purchases() -> None:
    inviter = uuid.uuid4()
    invitee = uuid.uuid4()
    repo = MagicMock()
    repo.lock_code_for_update.return_value = _code(inviter)
    repo.get_link_by_code_id.return_value = None
    repo.get_active_link_for_invitee.return_value = None
    repo.has_recent_receipt.return_value = True
    service = _service(repo)

    with pytest.raises(HTTPException) as exc:
        service.activate(MagicMock(), invitee, "AbC12x", is_new_user=False)
    assert exc.value.status_code == 409
    assert exc.value.detail == ERR_RECENT
    repo.insert_link.assert_not_called()


def test_activate_allows_old_purchases() -> None:
    inviter = uuid.uuid4()
    invitee = uuid.uuid4()
    repo = MagicMock()
    repo.lock_code_for_update.return_value = _code(inviter)
    repo.get_link_by_code_id.return_value = None
    repo.get_active_link_for_invitee.return_value = None
    repo.has_recent_receipt.return_value = False
    repo.insert_link.side_effect = lambda _s, link: link
    service = _service(repo)
    session = MagicMock()
    session.begin_nested.return_value = MagicMock()

    link = service.activate(session, invitee, "AbC12x", is_new_user=False)
    assert link.invitee_id == invitee
    repo.has_recent_receipt.assert_called_once()
    repo.insert_code.assert_called_once()
    assert repo.insert_code.call_args.args[1] == inviter


def test_activate_rejects_second_active_link() -> None:
    inviter = uuid.uuid4()
    invitee = uuid.uuid4()
    repo = MagicMock()
    repo.lock_code_for_update.return_value = _code(inviter)
    repo.get_link_by_code_id.return_value = None
    repo.get_active_link_for_invitee.return_value = _link(
        inviter_id=uuid.uuid4(), invitee_id=invitee
    )
    service = _service(repo)

    with pytest.raises(HTTPException) as exc:
        service.activate(MagicMock(), invitee, "AbC12x", is_new_user=True)
    assert exc.value.detail == ERR_ACTIVE


def test_award_once_inside_window() -> None:
    invitee = uuid.uuid4()
    link = _link(inviter_id=uuid.uuid4(), invitee_id=invitee)
    repo = MagicMock()
    repo.get_awaiting_link_for_invitee.return_value = link
    service = _service(repo)
    session = MagicMock()
    receipt_id = uuid.uuid4()

    result = service.award_on_receipt(session, invitee, receipt_id)

    assert result is link
    assert link.reward_status == "rewarded"
    assert link.qualifying_receipt_id == receipt_id
    service._coupon_service.award_for_referral.assert_called_once()
    service._points_service.award_for_referral.assert_called_once()


def test_award_skips_when_no_awaiting_link() -> None:
    repo = MagicMock()
    repo.get_awaiting_link_for_invitee.return_value = None
    service = _service(repo)

    assert service.award_on_receipt(MagicMock(), uuid.uuid4(), uuid.uuid4()) is None
    service._coupon_service.award_for_referral.assert_not_called()


def test_award_zero_snapshots_skip_ledger() -> None:
    invitee = uuid.uuid4()
    link = _link(inviter_id=uuid.uuid4(), invitee_id=invitee)
    link.inviter_coupons = 0
    link.inviter_cashback_rub = 0
    repo = MagicMock()
    repo.get_awaiting_link_for_invitee.return_value = link
    service = _service(repo)

    service.award_on_receipt(MagicMock(), invitee, uuid.uuid4())

    service._coupon_service.award_for_referral.assert_not_called()
    service._points_service.award_for_referral.assert_not_called()
    assert link.reward_status == "rewarded"


def test_list_statuses() -> None:
    inviter = uuid.uuid4()
    issued = _code(inviter, "Issued1")
    awaiting = _code(inviter, "Await1")
    rewarded = _code(inviter, "Reward")
    expired = _code(inviter, "Expire")
    repo = MagicMock()
    repo.list_codes_for_inviter.return_value = [
        (issued, None),
        (awaiting, _link(inviter_id=inviter, invitee_id=uuid.uuid4())),
        (
            rewarded,
            _link(
                inviter_id=inviter,
                invitee_id=uuid.uuid4(),
                status="rewarded",
            ),
        ),
        (
            expired,
            _link(
                inviter_id=inviter,
                invitee_id=uuid.uuid4(),
                window_until=NOW - timedelta(hours=1),
            ),
        ),
    ]
    service = _service(repo)
    items = service.list_for_inviter(MagicMock(), inviter)
    assert [item.status for item in items] == [
        "issued",
        "awaiting_purchase",
        "rewarded",
        "expired",
    ]
    assert all(item.code for item in items)
