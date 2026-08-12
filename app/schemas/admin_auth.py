"""Admin authentication schemas (P-ADMIN-AUTH — TOTP login, no SMS)."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class AdminLoginRequest(BaseModel):
    """Phone identifies the staff user; code is the current TOTP.

    First login against a freshly-provisioned (not-yet-activated) credential
    activates it. No password, no SMS — the authenticator app is the factor.
    """

    model_config = ConfigDict(str_strip_whitespace=True)
    phone: str = Field(min_length=8, max_length=15)
    code: str = Field(min_length=6, max_length=8)
