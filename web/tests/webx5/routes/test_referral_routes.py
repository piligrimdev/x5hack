from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+psycopg2://postgres:password@localhost:5432/x5hack_test",
)
os.environ.setdefault("JWT_SECRET_KEY", "test-secret")
os.environ.setdefault("TERMINAL_TOKEN", "test-terminal-token")
os.environ.setdefault("REFERRAL_INVITEE_DISCOUNT_PERCENT", "10")
os.environ.setdefault("REFERRAL_INVITER_COUPONS", "2")
os.environ.setdefault("REFERRAL_INVITER_CASHBACK_RUB", "50")

from webx5.core.server import app
from webx5.dependencies.auth import _get_current_user_id
from webx5.dependencies.db import get_db
from webx5.entities.referral import ReferralCode
from webx5.schemas.referral import ReferralOut


@pytest.fixture()
def user_id():
    return uuid.uuid4()


@pytest.fixture()
def client(user_id):
    fake_session = MagicMock()

    def _override_db():
        yield fake_session

    app.dependency_overrides[_get_current_user_id] = lambda: user_id
    app.dependency_overrides[get_db] = _override_db
    yield TestClient(app), fake_session
    app.dependency_overrides.clear()


def _out(code: str, status: str = "issued") -> ReferralOut:
    now = datetime(2026, 9, 6, tzinfo=timezone.utc)
    return ReferralOut(
        id=uuid.uuid4(),
        code=code,
        status=status,  # type: ignore[arg-type]
        created_at=now,
    )


def test_issue_requires_auth():
    raw = TestClient(app)
    resp = raw.post("/referrals")
    assert resp.status_code == 401


def test_list_requires_auth():
    raw = TestClient(app)
    resp = raw.get("/referrals")
    assert resp.status_code == 401


def test_issue_twice_returns_different_codes(client, user_id):
    http, _session = client
    first = ReferralCode()
    first.id = uuid.uuid4()
    first.code = "AbC12x"
    first.created_at = datetime(2026, 9, 6, tzinfo=timezone.utc)
    second = ReferralCode()
    second.id = uuid.uuid4()
    second.code = "Xy9kL2"
    second.created_at = datetime(2026, 9, 6, tzinfo=timezone.utc)

    with (
        patch("webx5.core.referral.referral_service.issue", side_effect=[first, second]),
        patch(
            "webx5.core.referral.referral_service.list_for_inviter",
            side_effect=[
                [_out("AbC12x")],
                [_out("Xy9kL2"), _out("AbC12x")],
            ],
        ),
    ):
        r1 = http.post("/referrals")
        r2 = http.post("/referrals")
    assert r1.status_code == 201
    assert r2.status_code == 201
    assert r1.json()["code"] != r2.json()["code"]
    assert len(r1.json()["code"]) == 6


def test_list_four_statuses_and_no_friend_ids(client):
    http, _session = client
    items = [
        _out("Issued1", "issued"),
        _out("Await1x", "awaiting_purchase"),
        _out("Reward1", "rewarded"),
        _out("Expire1", "expired"),
    ]
    with patch("webx5.core.referral.referral_service.list_for_inviter", return_value=items):
        resp = http.get("/referrals")
    assert resp.status_code == 200
    body = resp.json()
    assert [item["status"] for item in body["items"]] == [
        "issued",
        "awaiting_purchase",
        "rewarded",
        "expired",
    ]
    blob = resp.text
    assert "invitee" not in blob
    assert "phone" not in blob


def test_list_empty(client):
    http, _session = client
    with patch("webx5.core.referral.referral_service.list_for_inviter", return_value=[]):
        resp = http.get("/referrals")
    assert resp.status_code == 200
    assert resp.json() == {"items": []}
