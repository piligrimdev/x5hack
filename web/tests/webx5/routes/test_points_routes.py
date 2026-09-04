"""Feature 007 US4/US6: /points endpoints — routing + auth guards.

Uses FastAPI dependency_overrides to swap DB session and auth.
Real DB isolation is out of PoC scope — logic is mocked via patched core services.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg2://postgres:password@localhost:5432/x5hack_test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("SYNTH_CONFIG_PATH", "/dev/null")
os.environ.setdefault("OPENROUTER_API_KEY", "")
TERMINAL_TOKEN = os.environ.get("TERMINAL_TOKEN") or "change-me-in-production"
os.environ["TERMINAL_TOKEN"] = TERMINAL_TOKEN

import pytest
from fastapi.testclient import TestClient

from webx5.core.server import app
from webx5.dependencies.auth import _get_current_user_id


@pytest.fixture()
def user_id():
    return uuid.uuid4()


@pytest.fixture()
def client(user_id):
    fake_session = MagicMock()
    app.dependency_overrides[_get_current_user_id] = lambda: user_id
    from webx5.core.db import db
    app.dependency_overrides[db.get_db] = lambda: iter([fake_session])
    yield TestClient(app), fake_session
    app.dependency_overrides.clear()


def test_balance_returns_401_without_auth():
    # unmounted deps → HTTPBearer rejects → 401
    client = TestClient(app)
    r = client.get("/points/balance")
    assert r.status_code == 401


def test_balance_returns_view_for_authed_user(client, user_id):
    tc, _session = client
    fake_view = MagicMock()
    fake_view.balance = 500
    fake_view.rate_points_per_rub = 10
    fake_view.balance_rub_equivalent = 50

    with patch("webx5.core.points.points_service") as ps:
        ps.get_balance.return_value = fake_view
        r = tc.get("/points/balance", headers={"Authorization": "Bearer x"})

    assert r.status_code == 200
    assert r.json() == {
        "balance": 500,
        "rate_points_per_rub": 10,
        "balance_rub_equivalent": 50,
    }


def test_transactions_returns_empty_for_new_user(client, user_id):
    tc, _session = client
    with patch("webx5.core.points.points_service") as ps:
        ps.list_transactions.return_value = ([], 0)
        r = tc.get("/points/transactions", headers={"Authorization": "Bearer x"})

    assert r.status_code == 200
    body = r.json()
    assert body["items"] == []
    assert body["total"] == 0
    assert body["limit"] == 20
    assert body["offset"] == 0


def test_transactions_returns_history(client, user_id):
    tc, _session = client
    tx = MagicMock()
    tx.id = uuid.uuid4()
    tx.type = "earn"
    tx.amount = 50
    tx.related_task_id = uuid.uuid4()
    tx.related_receipt_id = None
    tx.rate_at_time = None
    tx.created_at = datetime.now(timezone.utc)
    with patch("webx5.core.points.points_service") as ps:
        ps.list_transactions.return_value = ([tx], 1)
        r = tc.get(
            "/points/transactions?limit=5&offset=0",
            headers={"Authorization": "Bearer x"},
        )

    assert r.status_code == 200
    body = r.json()
    assert len(body["items"]) == 1
    assert body["items"][0]["type"] == "earn"
    assert body["items"][0]["amount"] == 50
    assert body["total"] == 1
    assert body["limit"] == 5


def test_get_rate_is_public():
    tc = TestClient(app)
    fake_session = MagicMock()
    from webx5.core.db import db
    app.dependency_overrides[db.get_db] = lambda: iter([fake_session])
    try:
        with patch("webx5.core.points.points_repo") as pr:
            pr.get_rate.return_value = 10
            r = tc.get("/points/settings/rate")
        assert r.status_code == 200
        assert r.json() == {"rate_points_per_rub": 10}
    finally:
        app.dependency_overrides.clear()


def test_set_rate_without_terminal_token_is_401():
    tc = TestClient(app)
    fake_session = MagicMock()
    from webx5.core.db import db
    app.dependency_overrides[db.get_db] = lambda: iter([fake_session])
    try:
        r = tc.put("/points/settings/rate", json={"rate_points_per_rub": 20})
        assert r.status_code == 401
    finally:
        app.dependency_overrides.clear()


def test_set_rate_with_terminal_token_updates_rate():
    tc = TestClient(app)
    fake_session = MagicMock()
    from webx5.core.db import db
    app.dependency_overrides[db.get_db] = lambda: iter([fake_session])
    try:
        with patch("webx5.core.points.points_service") as ps:
            ps.set_rate.return_value = 20
            r = tc.put(
                "/points/settings/rate",
                headers={"X-Terminal-Token": TERMINAL_TOKEN},
                json={"rate_points_per_rub": 20},
            )
        assert r.status_code == 200
        assert r.json() == {"rate_points_per_rub": 20}
        ps.set_rate.assert_called_once()
    finally:
        app.dependency_overrides.clear()


def test_set_rate_zero_is_422():
    tc = TestClient(app)
    fake_session = MagicMock()
    from webx5.core.db import db
    app.dependency_overrides[db.get_db] = lambda: iter([fake_session])
    try:
        r = tc.put(
            "/points/settings/rate",
            headers={"X-Terminal-Token": TERMINAL_TOKEN},
            json={"rate_points_per_rub": 0},
        )
        # Pydantic gt=0 → 422
        assert r.status_code == 422
    finally:
        app.dependency_overrides.clear()
