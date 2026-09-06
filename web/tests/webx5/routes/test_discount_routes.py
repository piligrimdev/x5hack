from __future__ import annotations

import os
import uuid
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
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


def test_available_requires_auth():
    raw = TestClient(app)
    resp = raw.get("/discounts/available")
    assert resp.status_code == 401


def test_available_returns_described_discounts(client, user_id):
    http, session = client
    discount = SimpleNamespace(
        id=uuid.uuid4(),
        value=Decimal("10"),
        value_type="percent",
        discount_type=SimpleNamespace(name="персональная"),
        link_type=SimpleNamespace(name="all"),
        entity_id=None,
        loyalty_card_id=user_id,
        valid_from=None,
        valid_to=datetime(2026, 9, 13, 15, 0, tzinfo=MOSCOW),
    )

    with patch("webx5.crud.discount.DiscountRepository.list_available_for_user", return_value=[discount]):
        resp = http.get("/discounts/available")

    assert resp.status_code == 200
    body = resp.json()
    assert len(body["items"]) == 1
    item = body["items"][0]
    assert item["title"] == "Персональная скидка 10%"
    assert "на все покупки" in item["description"]
    assert item["is_personal"] is True
