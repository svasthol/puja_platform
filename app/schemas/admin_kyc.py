"""Admin KYC review schemas (Sprint 4B — A-KYC)."""
from __future__ import annotations

import datetime as dt
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

DocStatus = Literal["pending", "verified", "rejected"]
PujariVerificationStatus = Literal["pending", "verified", "rejected"]


class KycReviewRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    change_reason: str | None = Field(default=None, max_length=300)
    note: str | None = Field(default=None, max_length=500)


class KycPendingItem(BaseModel):
    id: uuid.UUID
    pujari_id: uuid.UUID
    pujari_name: str
    pujari_phone: str
    pujari_verification_status: PujariVerificationStatus
    doc_type: str
    doc_type_label: str
    version: int
    uploaded_at: dt.datetime
    view_url: str | None = None
    view_url_expires_in: int | None = None


class KycPendingListResponse(BaseModel):
    items: list[KycPendingItem]
    next_cursor: str | None = None
    required_doc_types: list[str]


class KycPujariDocSummary(BaseModel):
    doc_type: str
    doc_type_label: str
    status: DocStatus | None = None
    document_id: uuid.UUID | None = None
    version: int | None = None
    uploaded_at: dt.datetime | None = None
    view_url: str | None = None


class KycPujariStatusResponse(BaseModel):
    pujari_id: uuid.UUID
    full_name: str
    phone: str
    verification_status: PujariVerificationStatus
    required_doc_types: list[str]
    documents: list[KycPujariDocSummary]
    all_required_verified: bool


class KycReviewResponse(BaseModel):
    document_id: uuid.UUID
    document_status: DocStatus
    pujari_id: uuid.UUID
    pujari_verification_status: PujariVerificationStatus
    all_required_verified: bool
