import re

from pydantic import BaseModel, field_validator

from webx5.utils.auth import normalize_phone

_REFERRAL_CODE_RE = re.compile(r"^[A-Za-z0-9]{6}$")


class PhoneRequest(BaseModel):
    phone: str
    referral_code: str | None = None

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        try:
            return normalize_phone(v)
        except ValueError as e:
            raise ValueError(str(e)) from e

    @field_validator("referral_code")
    @classmethod
    def validate_referral_code(cls, v: str | None) -> str | None:
        if v is None or v == "":
            return None
        if not _REFERRAL_CODE_RE.fullmatch(v):
            raise ValueError("Некорректный формат кода")
        return v


class TokenPairResponse(BaseModel):
    access_token: str
    refresh_token: str


class RefreshRequest(BaseModel):
    refresh_token: str
