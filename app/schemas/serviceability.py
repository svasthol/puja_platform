"""Public service boundary probes."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ServiceabilityResponse(BaseModel):
    serviceable: bool
    code: str | None = None


class ServiceabilityProbeRequest(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)