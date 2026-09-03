import os

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg2://postgres:password@localhost:5432/x5hack_test")

from webx5.core.server import app  # noqa: E402

client = TestClient(app)


def test_health_returns_200():
    response = client.get("/health")
    assert response.status_code == 200


def test_health_returns_ok_status():
    response = client.get("/health")
    assert response.json() == {"status": "ok"}
