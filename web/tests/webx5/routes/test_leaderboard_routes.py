from __future__ import annotations

import os
import uuid
from unittest.mock import patch

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


@pytest.fixture()
def user_id():
    return uuid.uuid4()


@pytest.fixture()
def client(user_id):
    from unittest.mock import MagicMock

    fake_session = MagicMock()

    def _override_db():
        yield fake_session

    app.dependency_overrides[_get_current_user_id] = lambda: user_id
    app.dependency_overrides[get_db] = _override_db
    yield TestClient(app), fake_session
    app.dependency_overrides.clear()


def _ready_snapshot(user_id: uuid.UUID) -> dict:
    store_id = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
    return {
        "status": "ready",
        "period": {"year": 2026, "month": 9, "timezone": "Europe/Moscow"},
        "store": {"id": store_id, "name": "Пятёрочка, d_03"},
        "participant_count": 2,
        "me": {
            "rank": 1,
            "savings_percent": 10,
            "beats_percent": 50,
            "top_percent": 25,
            "in_top": True,
        },
        "entries": [
            {
                "rank": 1,
                "label": "сосед 14",
                "savings_percent": 10,
                "is_me": True,
            },
            {
                "rank": 2,
                "label": "сосед 81",
                "savings_percent": 5,
                "is_me": False,
            },
        ],
        "solo": False,
    }


def test_leaderboard_401_without_auth():
    client = TestClient(app)
    response = client.get("/leaderboard")
    assert response.status_code == 401
    body = response.json()
    assert "entries" not in body
    assert "store" not in body


def test_leaderboard_200_ready_shape(client, user_id):
    tc, _session = client
    with patch("webx5.core.leaderboard.leaderboard_service") as svc:
        svc.get_snapshot.return_value = _ready_snapshot(user_id)
        response = tc.get("/leaderboard", headers={"Authorization": "Bearer x"})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["store"]["name"] == "Пятёрочка, d_03"
    assert body["me"]["rank"] == 1
    assert body["me"]["savings_percent"] == 10
    assert len(body["entries"]) >= 1
    assert "user_id" not in body
    assert "user_id" not in body["entries"][0]
    assert "address" not in body["store"]


def test_leaderboard_200_no_home_store(client, user_id):
    tc, _session = client
    empty = {
        "status": "no_home_store",
        "period": {"year": 2026, "month": 9, "timezone": "Europe/Moscow"},
        "store": None,
        "participant_count": 0,
        "me": None,
        "entries": [],
        "solo": False,
    }
    with patch("webx5.core.leaderboard.leaderboard_service") as svc:
        svc.get_snapshot.return_value = empty
        response = tc.get("/leaderboard", headers={"Authorization": "Bearer x"})
    assert response.status_code == 200
    assert response.json()["status"] == "no_home_store"
    assert response.json()["me"] is None


def test_openapi_documents_leaderboard_without_user_id():
    schema = app.openapi()
    assert "/leaderboard" in schema["paths"]
    get_op = schema["paths"]["/leaderboard"]["get"]
    assert "200" in get_op["responses"]
    models = schema["components"]["schemas"]
    assert "LeaderboardOut" in models
    assert "LeaderboardMeOut" in models
    assert "user_id" not in models["LeaderboardOut"].get("properties", {})
    assert "user_id" not in models["LeaderboardEntryOut"].get("properties", {})
    assert "address" not in models["LeaderboardStoreOut"].get("properties", {})
