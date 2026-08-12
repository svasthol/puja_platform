"""Admin schemas."""
from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class AdvanceAmountResponse(BaseModel):
    amount: Decimal
    currency: str
    updated_at: str | None = None


class AdvanceAmountUpdate(BaseModel):
    amount: Decimal = Field(ge=1, le=10000)
    change_reason: str | None = Field(default=None, max_length=300)


# ---- Role management (P-ADMIN-SEED) ---------------------------------------
class RoleAssignRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    role: Literal["admin", "support"]
    change_reason: str | None = Field(default=None, max_length=300)


class UserRolesResponse(BaseModel):
    user_id: uuid.UUID
    roles: list[str]


class AdminMeResponse(BaseModel):
    """Session identity for the admin shell (A-ADMIN-UI role-gated nav)."""

    user_id: uuid.UUID
    phone: str
    roles: list[str]
    is_admin: bool = False
    is_support: bool = False


# ---- TOTP credential provisioning (P-ADMIN-AUTH) --------------------------
class CredentialProvisionResponse(BaseModel):
    """Returned ONCE at provisioning — the URI/secret are never retrievable again."""

    user_id: uuid.UUID
    provisioning_uri: str
    secret: str
    note: str = "Scan in an authenticator app now. This secret is shown only once."
