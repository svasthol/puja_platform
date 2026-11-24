"""Admin service boundary settings."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ServiceBoundarySettingsResponse(BaseModel):
    service_boundary_enabled: bool
    updated_at: str | None = None


class ServiceBoundarySettingsUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    service_boundary_enabled: bool
    change_reason: str = Field(min_length=3, max_length=500)


class ServiceBoundaryStatusResponse(BaseModel):
    loaded: bool
    service_boundary_enabled: bool
    etag: str | None = None
    version: str | None = None
    vertex_count: int = 0
    bbox: dict[str, float] | None = None
    source_path: str | None = None
    load_error: str | None = None


class ServiceBoundaryProbeResponse(BaseModel):
    serviceable: bool
    code: str | None = None