"""Service area schemas — customer dropdown + admin CRUD (A-AREAS, P-LAUNCH-AREA)."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import Page


class ServiceAreaPublic(BaseModel):
    """Customer dropdown row — active zones only."""

    id: int
    city: str
    zone_name: str


class ServiceAreaPublicList(BaseModel):
    areas: list[ServiceAreaPublic]


class ServiceAreaOut(BaseModel):
    id: int
    city: str
    zone_name: str
    pincode: str | None
    is_active: bool
    pujari_count: int = 0
    active_booking_count: int = 0


class ServiceAreaListResponse(Page):
    areas: list[ServiceAreaOut]


class ServiceAreaCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    city: str = Field(min_length=1, max_length=80)
    zone_name: str = Field(min_length=1, max_length=100)
    pincode: str | None = Field(default=None, max_length=10)
    is_active: bool = True


class ServiceAreaUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    city: str | None = Field(default=None, min_length=1, max_length=80)
    zone_name: str | None = Field(default=None, min_length=1, max_length=100)
    pincode: str | None = Field(default=None, max_length=10)
    is_active: bool | None = None
    force_deactivate: bool = False
    change_reason: str | None = Field(default=None, max_length=300)


class PujariServiceAreasReplace(BaseModel):
    service_area_ids: list[int] = Field(default_factory=list)
    change_reason: str | None = Field(default=None, max_length=300)
