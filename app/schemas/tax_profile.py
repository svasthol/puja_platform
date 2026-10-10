"""Partner tax profile schemas."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class PujariTaxProfileResponse(BaseModel):
    entity_type: str | None
    pan_on_file: bool
    pan_status: str | None = None
    tax_profile_complete: bool


class PujariTaxProfileUpdateRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    entity_type: Literal["individual", "huf", "company", "firm", "trust", "aop", "other"]


class PujariPanSubmitRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    pan: str = Field(min_length=10, max_length=10)
    entity_type: Literal["individual", "huf", "company", "firm", "trust", "aop", "other"]
    consent: bool
    reason: str = Field(min_length=20, max_length=500)


class PujariPanSubmitResponse(BaseModel):
    entity_type: str
    pan_on_file: bool
    pan_status: str
    message: str
    verified_name: str | None = None
