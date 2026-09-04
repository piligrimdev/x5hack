import os
import uuid
from datetime import timedelta

import pytest

os.environ.setdefault("JWT_SECRET_KEY", "test-secret")
os.environ.setdefault("JWT_TTL_DAYS", "7")
os.environ.setdefault("JWT_REFRESH_TTL_DAYS", "14")

from webx5.utils.auth import (  # noqa: E402
    decode_access_jwt,
    decode_refresh_jwt,
    encode_access_jwt,
    encode_refresh_jwt,
    normalize_phone,
)


class TestNormalizePhone:
    def test_e164_passthrough(self):
        assert normalize_phone("+79161234567") == "+79161234567"

    def test_seven_prefix(self):
        assert normalize_phone("79161234567") == "+79161234567"

    def test_eight_prefix(self):
        assert normalize_phone("89161234567") == "+79161234567"

    def test_formatted_with_spaces(self):
        assert normalize_phone("+7 916 123-45-67") == "+79161234567"

    def test_formatted_with_parens(self):
        assert normalize_phone("8 (916) 123-45-67") == "+79161234567"

    def test_invalid_short(self):
        with pytest.raises(ValueError):
            normalize_phone("123")

    def test_invalid_letters(self):
        with pytest.raises(ValueError):
            normalize_phone("abc")

    def test_empty_string(self):
        with pytest.raises(ValueError):
            normalize_phone("")


class TestAccessJwt:
    def test_round_trip(self):
        uid = uuid.uuid4()
        token = encode_access_jwt(uid)
        assert decode_access_jwt(token) == uid

    def test_expired_raises_401(self):
        import jwt as pyjwt
        from datetime import datetime, timezone
        from fastapi import HTTPException

        uid = uuid.uuid4()
        payload = {
            "sub": str(uid),
            "typ": "access",
            "iat": datetime.now(timezone.utc),
            "exp": datetime.now(timezone.utc) - timedelta(seconds=1),
        }
        expired_token = pyjwt.encode(payload, os.environ["JWT_SECRET_KEY"], algorithm="HS256")
        with pytest.raises(HTTPException) as exc:
            decode_access_jwt(expired_token)
        assert exc.value.status_code == 401

    def test_refresh_token_rejected_by_access_decoder(self):
        from fastapi import HTTPException

        uid = uuid.uuid4()
        refresh_token = encode_refresh_jwt(uid)
        with pytest.raises(HTTPException) as exc:
            decode_access_jwt(refresh_token)
        assert exc.value.status_code == 401


class TestRefreshJwt:
    def test_round_trip(self):
        uid = uuid.uuid4()
        token = encode_refresh_jwt(uid)
        assert decode_refresh_jwt(token) == uid

    def test_access_token_rejected_by_refresh_decoder(self):
        from fastapi import HTTPException

        uid = uuid.uuid4()
        access_token = encode_access_jwt(uid)
        with pytest.raises(HTTPException) as exc:
            decode_refresh_jwt(access_token)
        assert exc.value.status_code == 401

    def test_expired_raises_401(self):
        import jwt as pyjwt
        from datetime import datetime, timezone
        from fastapi import HTTPException

        uid = uuid.uuid4()
        payload = {
            "sub": str(uid),
            "typ": "refresh",
            "iat": datetime.now(timezone.utc),
            "exp": datetime.now(timezone.utc) - timedelta(seconds=1),
        }
        expired_token = pyjwt.encode(payload, os.environ["JWT_SECRET_KEY"], algorithm="HS256")
        with pytest.raises(HTTPException) as exc:
            decode_refresh_jwt(expired_token)
        assert exc.value.status_code == 401
