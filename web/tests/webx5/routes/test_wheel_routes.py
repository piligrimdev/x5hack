from __future__ import annotations

import os
import uuid
from datetime import date, datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+psycopg2://postgres:password@localhost:5432/x5hack_test",
)
os.environ.setdefault("JWT_SECRET_KEY", "test-secret")
os.environ.setdefault("TERMINAL_TOKEN", "test-terminal-token")
os.environ.setdefault("FORTUNE_WHEEL_WEEKLY_COUPONS", "3")

from webx5.core.server import app  # noqa: E402
from webx5.dependencies.auth import _get_current_user_id  # noqa: E402
from webx5.dependencies.db import get_db  # noqa: E402


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


def _state(user_id: uuid.UUID) -> dict:
    cat = uuid.uuid4()
    return {
        "coupons": 3,
        "can_spin": True,
        "weekly_coupons": 3,
        "week_start": date(2026, 9, 1),
        "sectors": [
            {
                "code": "small_cashback",
                "label": "Небольшой кешбэк",
                "description": "10 ₽ на счёт баллов",
                "prize_type": "cashback",
                "probability_percent": 40,
                "cashback_rub": 10,
                "gift": None,
            },
            {
                "code": "medium_cashback",
                "label": "Средний кешбэк",
                "description": "30 ₽ на счёт баллов",
                "prize_type": "cashback",
                "probability_percent": 30,
                "cashback_rub": 30,
                "gift": None,
            },
            {
                "code": "gift_chocolate",
                "label": "Подарок: 1 шоколадка бесплатно",
                "description": "1 бесплатная единица товара категории «кондитерка»",
                "prize_type": "gift",
                "probability_percent": 20,
                "cashback_rub": None,
                "gift": {
                    "criterion_type": "category",
                    "criterion_entity_id": cat,
                    "quantity": 1,
                },
            },
            {
                "code": "large_cashback",
                "label": "Крупный кешбэк",
                "description": "100 ₽ на счёт баллов",
                "prize_type": "cashback",
                "probability_percent": 10,
                "cashback_rub": 100,
                "gift": None,
            },
        ],
    }


def test_get_wheel_401_without_auth():
    client = TestClient(app)
    r = client.get("/wheel")
    assert r.status_code == 401


def test_get_wheel_200_contract(client, user_id):
    tc, _session = client
    with patch("webx5.core.wheel.wheel_service") as svc:
        svc.get_state.return_value = _state(user_id)
        r = tc.get("/wheel", headers={"Authorization": "Bearer x"})

    assert r.status_code == 200
    body = r.json()
    assert len(body["sectors"]) >= 2
    assert sum(s["probability_percent"] for s in body["sectors"]) == 100
    types = {s["prize_type"] for s in body["sectors"]}
    assert "cashback" in types and "gift" in types
    assert body["can_spin"] == (body["coupons"] > 0)


def test_spin_409_insufficient(client):
    tc, _session = client
    from webx5.services.wheel import InsufficientCouponsError

    with patch("webx5.core.wheel.wheel_service") as svc:
        svc.spin.side_effect = InsufficientCouponsError("INSUFFICIENT_COUPONS")
        r = tc.post("/wheel/spin", headers={"Authorization": "Bearer x"}, json={})

    assert r.status_code == 409
    assert r.json()["detail"] == "INSUFFICIENT_COUPONS"


def test_spin_200(client, user_id):
    tc, _session = client
    spin_id = uuid.uuid4()
    with patch("webx5.core.wheel.wheel_service") as svc:
        svc.spin.return_value = {
            "spin_id": spin_id,
            "sector_code": "small_cashback",
            "prize_type": "cashback",
            "prize_label": "Небольшой кешбэк",
            "cashback_rub": 10,
            "points_awarded": 100,
            "gift_reward_id": None,
            "coupons_after": 2,
            "created_at": datetime.now(timezone.utc),
        }
        r = tc.post("/wheel/spin", headers={"Authorization": "Bearer x"}, json={})

    assert r.status_code == 200
    assert r.json()["spin_id"] == str(spin_id)
    assert r.json()["coupons_after"] == 2


def test_spins_empty(client, user_id):
    tc, _session = client
    with patch("webx5.core.wheel.wheel_service") as svc:
        svc.list_spins.return_value = ([], 0)
        r = tc.get("/wheel/spins", headers={"Authorization": "Bearer x"})
    assert r.status_code == 200
    assert r.json()["items"] == []
    assert r.json()["total"] == 0


def test_history_endpoints_401_without_auth():
    bare = TestClient(app)
    assert bare.get("/wheel/spins").status_code == 401
    assert bare.get("/coupons/transactions").status_code == 401


def test_spins_desc_order(client):
    tc, _session = client
    newer = datetime(2026, 9, 6, 12, tzinfo=timezone.utc)
    older = datetime(2026, 9, 5, 12, tzinfo=timezone.utc)
    items = [
        {
            "id": uuid.uuid4(),
            "sector_code": "a",
            "prize_type": "cashback",
            "prize_label": "new",
            "cashback_rub": 10,
            "gift_reward_id": None,
            "gift_status": None,
            "coupons_spent": 1,
            "created_at": newer,
        },
        {
            "id": uuid.uuid4(),
            "sector_code": "b",
            "prize_type": "cashback",
            "prize_label": "old",
            "cashback_rub": 30,
            "gift_reward_id": None,
            "gift_status": None,
            "coupons_spent": 1,
            "created_at": older,
        },
    ]
    with patch("webx5.core.wheel.wheel_service") as svc:
        svc.list_spins.return_value = (items, 2)
        r = tc.get("/wheel/spins", headers={"Authorization": "Bearer x"})
    body = r.json()
    assert body["total"] == 2
    assert body["items"][0]["prize_label"] == "new"
    assert body["items"][1]["prize_label"] == "old"
