"""Auth request/response schemas."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class OtpRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    phone: str = Field(min_length=8, max_length=15)


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


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
