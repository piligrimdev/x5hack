from __future__ import annotations

import os
import uuid
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+psycopg2://postgres:password@localhost:5432/x5hack_test",
)
os.environ.setdefault("JWT_SECRET_KEY", "test-secret")
os.environ.setdefault("TERMINAL_TOKEN", "test-terminal-token")

from webx5.core.server import app
from webx5.dependencies.auth import _get_current_user_id
from webx5.dependencies.db import get_db
from webx5.routes.receipts import _inclusive_day_bounds

MOSCOW = ZoneInfo("Europe/Moscow")


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


def test_inclusive_bounds_cover_full_last_day():
    start, end = _inclusive_day_bounds(date(2026, 8, 1), date(2026, 8, 31))
    assert start == datetime(2026, 8, 1, tzinfo=MOSCOW)
    assert end == datetime(2026, 9, 1, tzinfo=MOSCOW)


def test_economy_rejects_inverted_range(client):
    http, _session = client
    resp = http.get("/receipts/economy?date_from=2026-09-10&date_to=2026-09-01")
    assert resp.status_code == 422


def test_economy_forwards_period_to_repo(client, user_id):
    http, _session = client
    with patch("webx5.core.purchases.receipt_repo.get_economy_summary") as summary:
        summary.return_value = {
            "total_saved": Decimal("12"),
            "total_paid": Decimal("88"),
            "receipts_count": 1,
        }
        resp = http.get("/receipts/economy?date_from=2026-09-01&date_to=2026-09-07")

    assert resp.status_code == 200
    start, end = summary.call_args.kwargs["date_from"], summary.call_args.kwargs["date_to"]
    assert start == datetime(2026, 9, 1, tzinfo=MOSCOW)
    assert end == datetime(2026, 9, 8, tzinfo=MOSCOW)
    assert summary.call_args.args[1] == user_id
