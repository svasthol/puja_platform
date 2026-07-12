"""Auth request/response schemas."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class OtpRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    phone: str = Field(min_length=8, max_length=15)


class OtpVerify(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    phone: str = Field(min_length=8, max_length=15)
    otp: str = Field(min_length=4, max_length=8)


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
