from __future__ import annotations

import os
import uuid
from unittest.mock import MagicMock, patch

from fastapi import HTTPException
from fastapi.testclient import TestClient

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+psycopg2://postgres:password@localhost:5432/x5hack_test",
)
os.environ.setdefault("JWT_SECRET_KEY", "test-secret")
os.environ.setdefault("JWT_TTL_DAYS", "7")
os.environ.setdefault("JWT_REFRESH_TTL_DAYS", "14")
os.environ.setdefault("TERMINAL_TOKEN", "test-terminal-token")

from webx5.core.server import app
from webx5.dependencies.db import get_db
from webx5.entities.user import User

PHONE = "+79001234567"


def _client() -> TestClient:
    def _db():
        yield MagicMock()

    app.dependency_overrides[get_db] = _db
    return TestClient(app)


def _user(phone: str = PHONE) -> User:
    u = User()
    u.id = uuid.uuid4()
    u.phone = phone
    return u


def test_register_short_code_422_does_not_create_user():
    http = _client()
    try:
        resp = http.post("/register", json={"phone": PHONE, "referral_code": "12"})
        assert resp.status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_register_without_code_still_200():
    user = _user()
    http = _client()
    try:
        with (
            patch("webx5.crud.user.UserRepository.get_by_phone", return_value=None),
            patch("webx5.crud.user.UserRepository.create", return_value=user),
        ):
            resp = http.post("/register", json={"phone": PHONE})
        assert resp.status_code == 200
    finally:
        app.dependency_overrides.clear()


def test_register_valid_code_activates():
    user = _user()
    http = _client()
    try:
        with (
            patch("webx5.crud.user.UserRepository.get_by_phone", return_value=None),
            patch("webx5.crud.user.UserRepository.add", return_value=user),
            patch("webx5.core.referral.referral_service.activate") as activate,
        ):
            resp = http.post(
                "/register", json={"phone": PHONE, "referral_code": "AbC12x"}
            )
        assert resp.status_code == 200
        activate.assert_called_once()
        assert activate.call_args.kwargs["is_new_user"] is True
    finally:
        app.dependency_overrides.clear()


def test_register_used_code_409():
    user = _user()
    http = _client()
    try:
        with (
            patch("webx5.crud.user.UserRepository.get_by_phone", return_value=None),
            patch("webx5.crud.user.UserRepository.add", return_value=user),
            patch(
                "webx5.core.referral.referral_service.activate",
                side_effect=HTTPException(status_code=409, detail="Код уже использован"),
            ),
        ):
            resp = http.post(
                "/register", json={"phone": PHONE, "referral_code": "AbC12x"}
            )
        assert resp.status_code == 409
        assert resp.json()["detail"] == "Код уже использован"
    finally:
        app.dependency_overrides.clear()


def test_login_without_code_unchanged():
    user = _user()
    http = _client()
    try:
        with patch("webx5.crud.user.UserRepository.get_by_phone", return_value=user):
            resp = http.post("/login", json={"phone": PHONE})
        assert resp.status_code == 200
    finally:
        app.dependency_overrides.clear()


def test_login_unknown_phone_with_code_404():
    http = _client()
    try:
        with patch("webx5.crud.user.UserRepository.get_by_phone", return_value=None):
            resp = http.post(
                "/login", json={"phone": "+79999999999", "referral_code": "AbC12x"}
            )
        assert resp.status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_login_recent_purchases_409_no_token():
    user = _user()
    http = _client()
    try:
        with (
            patch("webx5.crud.user.UserRepository.get_by_phone", return_value=user),
            patch(
                "webx5.core.referral.referral_service.activate",
                side_effect=HTTPException(
                    status_code=409,
                    detail="Реактивация недоступна: недавно были покупки. Войдите без кода",
                ),
            ),
        ):
            resp = http.post(
                "/login", json={"phone": PHONE, "referral_code": "AbC12x"}
            )
        assert resp.status_code == 409
        assert "access_token" not in resp.json()
        assert resp.status_code != 403
    finally:
        app.dependency_overrides.clear()
