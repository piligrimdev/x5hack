import os
import uuid
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg2://postgres:password@localhost:5432/x5hack_test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret")
os.environ.setdefault("JWT_TTL_DAYS", "7")
os.environ.setdefault("JWT_REFRESH_TTL_DAYS", "14")
os.environ.setdefault("TERMINAL_TOKEN", "test-terminal-token")

from fastapi.testclient import TestClient  # noqa: E402

from webx5.core.server import app  # noqa: E402
from webx5.entities.user import User  # noqa: E402
from webx5.utils.auth import encode_access_jwt, encode_refresh_jwt  # noqa: E402

client = TestClient(app)

PHONE = "+79001234567"
PHONE_RAW = "8 (900) 123-45-67"


def _make_user(phone: str = PHONE) -> User:
    u = User()
    u.id = uuid.uuid4()
    u.phone = phone
    return u


class TestRegister:
    def test_new_user_returns_token_pair(self):
        user = _make_user()
        with (
            patch("webx5.crud.user.UserRepository.get_by_phone", return_value=None),
            patch("webx5.crud.user.UserRepository.create", return_value=user),
        ):
            resp = client.post("/register", json={"phone": PHONE})
        assert resp.status_code == 200
        body = resp.json()
        assert "access_token" in body
        assert "refresh_token" in body

    def test_duplicate_phone_returns_409(self):
        user = _make_user()
        with patch("webx5.crud.user.UserRepository.get_by_phone", return_value=user):
            resp = client.post("/register", json={"phone": PHONE})
        assert resp.status_code == 409
        assert "already registered" in resp.json()["detail"]

    def test_invalid_phone_returns_422(self):
        resp = client.post("/register", json={"phone": "123"})
        assert resp.status_code == 422

    def test_normalized_format_works(self):
        user = _make_user()
        with (
            patch("webx5.crud.user.UserRepository.get_by_phone", return_value=None),
            patch("webx5.crud.user.UserRepository.create", return_value=user),
        ):
            resp = client.post("/register", json={"phone": PHONE_RAW})
        assert resp.status_code == 200


class TestLogin:
    def test_existing_user_returns_token_pair(self):
        user = _make_user()
        with patch("webx5.crud.user.UserRepository.get_by_phone", return_value=user):
            resp = client.post("/login", json={"phone": PHONE})
        assert resp.status_code == 200
        body = resp.json()
        assert "access_token" in body
        assert "refresh_token" in body

    def test_unknown_phone_returns_404(self):
        with patch("webx5.crud.user.UserRepository.get_by_phone", return_value=None):
            resp = client.post("/login", json={"phone": "+79999999999"})
        assert resp.status_code == 404


class TestRefresh:
    def test_valid_refresh_returns_new_pair(self):
        user = _make_user()
        refresh_token = encode_refresh_jwt(user.id)
        with patch("webx5.services.auth.AuthService.refresh") as mock_refresh:
            from webx5.schemas.auth import TokenPairResponse

            mock_refresh.return_value = TokenPairResponse(
                access_token=encode_access_jwt(user.id),
                refresh_token=encode_refresh_jwt(user.id),
            )
            resp = client.post("/refresh", json={"refresh_token": refresh_token})
        assert resp.status_code == 200
        body = resp.json()
        assert "access_token" in body
        assert "refresh_token" in body

    def test_access_token_as_refresh_returns_401(self):
        uid = uuid.uuid4()
        access_token = encode_access_jwt(uid)
        resp = client.post("/refresh", json={"refresh_token": access_token})
        assert resp.status_code == 401

    def test_invalid_token_returns_401(self):
        resp = client.post("/refresh", json={"refresh_token": "not-a-jwt"})
        assert resp.status_code == 401


class TestMe:
    def test_with_valid_token_returns_user_id(self):
        uid = uuid.uuid4()
        token = encode_access_jwt(uid)
        resp = client.get("/me", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.json()["user_id"] == str(uid)

    def test_without_token_returns_401(self):
        resp = client.get("/me")
        assert resp.status_code == 401

    def test_with_refresh_token_returns_401(self):
        uid = uuid.uuid4()
        refresh_token = encode_refresh_jwt(uid)
        resp = client.get("/me", headers={"Authorization": f"Bearer {refresh_token}"})
        assert resp.status_code == 401


class TestTerminalPing:
    def test_valid_token_returns_ok(self):
        resp = client.get("/terminal/ping", headers={"X-Terminal-Token": "test-terminal-token"})
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

    def test_no_token_returns_401(self):
        resp = client.get("/terminal/ping")
        assert resp.status_code == 401

    def test_wrong_token_returns_401(self):
        resp = client.get("/terminal/ping", headers={"X-Terminal-Token": "wrong"})
        assert resp.status_code == 401

    def test_user_jwt_as_terminal_token_returns_401(self):
        uid = uuid.uuid4()
        token = encode_access_jwt(uid)
        resp = client.get("/terminal/ping", headers={"X-Terminal-Token": token})
        assert resp.status_code == 401
