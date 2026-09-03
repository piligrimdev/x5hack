import os
import uuid
from datetime import datetime, timedelta, timezone

import jwt
import phonenumbers
from fastapi import HTTPException


def normalize_phone(raw: str) -> str:
    try:
        parsed = phonenumbers.parse(raw, "RU")
    except phonenumbers.NumberParseException:
        raise ValueError(f"Invalid phone number: {raw!r}")
    if not phonenumbers.is_valid_number(parsed):
        raise ValueError(f"Invalid phone number: {raw!r}")
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)


def _secret() -> str:
    return os.environ["JWT_SECRET_KEY"]


def _access_ttl() -> int:
    return int(os.environ.get("JWT_TTL_DAYS", "7"))


def _refresh_ttl() -> int:
    return int(os.environ.get("JWT_REFRESH_TTL_DAYS", "14"))


def encode_access_jwt(user_id: uuid.UUID) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "typ": "access",
        "iat": now,
        "exp": now + timedelta(days=_access_ttl()),
    }
    return jwt.encode(payload, _secret(), algorithm="HS256")


def decode_access_jwt(token: str) -> uuid.UUID:
    try:
        payload = jwt.decode(token, _secret(), algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Could not validate credentials")
    if payload.get("typ") != "access":
        raise HTTPException(status_code=401, detail="Could not validate credentials")
    return uuid.UUID(payload["sub"])


def encode_refresh_jwt(user_id: uuid.UUID) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "typ": "refresh",
        "iat": now,
        "exp": now + timedelta(days=_refresh_ttl()),
    }
    return jwt.encode(payload, _secret(), algorithm="HS256")


def decode_refresh_jwt(token: str) -> uuid.UUID:
    try:
        payload = jwt.decode(token, _secret(), algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Could not validate credentials")
    if payload.get("typ") != "refresh":
        raise HTTPException(status_code=401, detail="Could not validate credentials")
    return uuid.UUID(payload["sub"])
