"""Route test for GET /challenges/current.

Uses FastAPI dependency_overrides to swap out DB session + auth dependency;
core challenge_service is patched to return deterministic fixtures.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg2://postgres:password@localhost:5432/x5hack_test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("SYNTH_CONFIG_PATH", "/dev/null")  # avoid yaml load in tests
os.environ.setdefault("OPENROUTER_API_KEY", "")

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch

from webx5.core.server import app  # noqa: E402
from webx5.dependencies.auth import _get_current_user_id  # noqa: E402


@pytest.fixture()
def user_id():
    return uuid.uuid4()


@pytest.fixture()
def client(user_id):
    fake_session = MagicMock()
    app.dependency_overrides[_get_current_user_id] = lambda: user_id
    # SessionDep is Annotated[Session, Depends(db.get_db)] — override by walking down to db.get_db.
    from webx5.core.db import db
    app.dependency_overrides[db.get_db] = lambda: iter([fake_session])
    yield TestClient(app), fake_session
    app.dependency_overrides.clear()


def _make_task(user_id: uuid.UUID):
    from webx5.entities.task import Task
    t = Task()
    t.id = uuid.uuid4()
    t.loyalty_card_id = user_id
    t.title = "Скидка 15%"
    t.description = "Купи молоко"
    t.mechanic = "порог трат + скидка на любимый товар"
    t.reward_rub = Decimal("45.00")
    t.criterion_type = "product"
    t.criterion_entity_id = uuid.uuid4()
    t.quantity_target = 1
    t.quantity_current = 0
    t.deadline = datetime.now(timezone.utc)
    return t


def test_get_current_returns_active_tasks(client, user_id):
    tc, session = client
    task = _make_task(user_id)

    with patch("webx5.core.challenges.challenge_service.get_current", return_value=([task, task, task, task], "none")):
        resp = tc.get("/challenges/current", headers={"Authorization": "Bearer fake"})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["items"]) == 4
    assert body["empty_reason"] == "none"


def test_get_current_empty_no_history(client, user_id):
    tc, session = client
    with patch("webx5.core.challenges.challenge_service.get_current", return_value=([], "no_history")):
        resp = tc.get("/challenges/current", headers={"Authorization": "Bearer fake"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["items"] == []
    assert body["empty_reason"] == "no_history"


def test_get_current_401_without_bearer():
    """No dependency override — real auth kicks in → 401."""
    tc = TestClient(app)
    resp = tc.get("/challenges/current")
    assert resp.status_code == 401 or resp.status_code == 403
