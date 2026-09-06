from __future__ import annotations

import os
import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+psycopg2://postgres:password@localhost:5432/x5hack_test",
)
os.environ.setdefault("JWT_SECRET_KEY", "test-secret")
os.environ.setdefault("TERMINAL_TOKEN", "test-terminal-token")

from webx5.core.server import app  # noqa: E402
from webx5.dependencies.db import get_db  # noqa: E402


@pytest.fixture()
def client():
    fake_session = MagicMock()
    app.dependency_overrides[get_db] = lambda: iter([fake_session])
    yield TestClient(app), fake_session
    app.dependency_overrides.clear()


def test_list_vibes_includes_llm_context(client):
    http, _session = client
    vibe_id = uuid.uuid4()
    vibe = MagicMock()
    vibe.id = vibe_id
    vibe.name = "Здоровье и лёгкость"
    vibe.description = "Здоровые и натуральные продукты"
    vibe.llm_context = "овощи, фрукты, мясо и птица"

    with patch("webx5.core.vibes.vibe_service") as svc:
        svc.get_all.return_value = [vibe]
        response = http.get("/vibes")

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": str(vibe_id),
            "name": "Здоровье и лёгкость",
            "description": "Здоровые и натуральные продукты",
            "llm_context": "овощи, фрукты, мясо и птица",
        }
    ]
