"""Auth request/response schemas."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.services.sms_phone import InvalidIndiaPhoneError, canonical_user_phone


def _validate_canonical_phone(v: str) -> str:
    try:
        return canonical_user_phone(v)
    except InvalidIndiaPhoneError as exc:
        raise ValueError(str(exc)) from exc


class OtpRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    phone: str = Field(min_length=8, max_length=15)

    @field_validator("phone")
    @classmethod
    def _phone_canonical(cls, v: str) -> str:
        return _validate_canonical_phone(v)


class OtpVerify(BaseModel):
    """P-ADMIN-AUTH-FIX: app_context is a BODY field and structurally cannot be
    'admin' — the SMS OTP path never mints admin tokens (422 at the schema
    layer, before any handler code runs). Admin staff log in via TOTP
    (P-ADMIN-AUTH). It was previously a bare query parameter, which let any
    phone that passed OTP request `?app_context=admin` with no role check."""

    model_config = ConfigDict(str_strip_whitespace=True)
    phone: str = Field(min_length=8, max_length=15)
    otp: str = Field(min_length=4, max_length=8)
    app_context: Literal["customer", "pujari"] = "customer"

    @field_validator("phone")
    @classmethod
    def _phone_canonical(cls, v: str) -> str:
        return _validate_canonical_phone(v)


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
