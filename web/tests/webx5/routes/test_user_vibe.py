from __future__ import annotations

import os
import uuid
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+psycopg2://postgres:password@localhost:5432/x5hack_test",
)
os.environ.setdefault("JWT_SECRET_KEY", "test-secret")
os.environ.setdefault("TERMINAL_TOKEN", "test-terminal-token")

from webx5.core.server import app  # noqa: E402
from webx5.dependencies.auth import _get_current_user_id  # noqa: E402
from webx5.entities.user import User  # noqa: E402


@pytest.fixture()
def client():
    user_id = uuid.uuid4()
    fake_session = MagicMock()

    from webx5.core.db import db

    app.dependency_overrides[_get_current_user_id] = lambda: user_id
    app.dependency_overrides[db.get_db] = lambda: iter([fake_session])
    yield TestClient(app), fake_session, user_id
    app.dependency_overrides.clear()


def test_get_current_vibe(client):
    http, session, user_id = client
    vibe_id = uuid.uuid4()
    user = User(id=user_id, phone="+79000000000", vibe_type_id=vibe_id)
    session.get.return_value = user

    response = http.get("/users/me/vibe")

    assert response.status_code == 200
    assert response.json() == {"vibe_id": str(vibe_id)}
    session.get.assert_called_once_with(User, user_id)


def test_get_current_vibe_returns_null_when_not_selected(client):
    http, session, user_id = client
    session.get.return_value = User(
        id=user_id,
        phone="+79000000000",
        vibe_type_id=None,
    )

    response = http.get("/users/me/vibe")

    assert response.status_code == 200
    assert response.json() == {"vibe_id": None}


def test_get_current_vibe_returns_404_for_missing_user(client):
    http, session, _ = client
    session.get.return_value = None

    response = http.get("/users/me/vibe")

    assert response.status_code == 404
    assert response.json()["detail"] == "User not found"
