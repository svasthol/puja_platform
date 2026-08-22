"""Partner KYC onboarding request/response schemas (Pydantic v2)."""
from __future__ import annotations

import datetime as dt
import uuid

from pydantic import BaseModel, ConfigDict, Field


class PartnerRegisterRequest(BaseModel):
    bio: str | None = Field(default=None, max_length=2000)
    years_experience: int | None = Field(default=None, ge=0, le=80)


class PartnerRegisterResponse(BaseModel):
    pujari_id: uuid.UUID
    verification_status: str
    created: bool


class DigilockerStartResponse(BaseModel):
    request_id: uuid.UUID
    url: str
    expires_at: dt.datetime


class KycRequestStatusResponse(BaseModel):
    request_id: uuid.UUID
    status: str
    scope: str | None = None
    doc_types_created: list[str] = Field(default_factory=list)
    error_code: str | None = None
    error_message: str | None = None
    review_flags: list[str] = Field(default_factory=list)


class KycDocRequirement(BaseModel):
    doc_type: str
    status: str | None = None
    document_id: uuid.UUID | None = None


class PartnerKycStatusResponse(BaseModel):
    verification_status: str
    required: list[KycDocRequirement]


class SelfiePresignRequest(BaseModel):
    content_type: str = Field(default="image/jpeg", pattern=r"^image/(jpeg|jpg|png|webp)$")
    content_length: int = Field(ge=1, le=5_242_880)


class SelfiePresignResponse(BaseModel):
    document_id: uuid.UUID
    upload_url: str
    upload_url_expires_in: int
    file_url: str


class SelfieConfirmResponse(BaseModel):
    document_id: uuid.UUID
    doc_type: str = "photo"
    status: str
    file_url: str


class IdentityDenyRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    denied_reason: str = Field(min_length=3, max_length=500)
    digilocker_id_hash: str | None = Field(default=None, max_length=128)
    pujari_id: uuid.UUID | None = None


class IdentityDenyResponse(BaseModel):
    registry_id: uuid.UUID
    digilocker_id_hash: str
    state: str
