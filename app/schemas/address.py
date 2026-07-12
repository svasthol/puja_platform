"""Customer address schemas (C-ADDR, API_CONTRACTS §Addresses v3.2).

latitude/longitude are REQUIRED on create: the client app resolves them
(GPS "use current location" / map pin) before calling the API. The DB trigger
trg_addresses_geom_sync (migration 005) derives `geom`; checkout 422s without it.
"""
from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import Page


class AddressCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    line1: str = Field(min_length=1, max_length=200)
    line2: str | None = Field(default=None, max_length=200)
    city: str = Field(min_length=1, max_length=80)
    state: str | None = Field(default=None, max_length=80)
    pincode: str | None = Field(default=None, max_length=10)
    latitude: Decimal = Field(ge=-90, le=90)
    longitude: Decimal = Field(ge=-180, le=180)
    is_default: bool = False


class AddressUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    line1: str | None = Field(default=None, min_length=1, max_length=200)
    line2: str | None = Field(default=None, max_length=200)
    city: str | None = Field(default=None, min_length=1, max_length=80)
    state: str | None = Field(default=None, max_length=80)
    pincode: str | None = Field(default=None, max_length=10)
    latitude: Decimal | None = Field(default=None, ge=-90, le=90)
    longitude: Decimal | None = Field(default=None, ge=-180, le=180)
    is_default: bool | None = None


class AddressOut(BaseModel):
    id: uuid.UUID
    line1: str
    line2: str | None
    city: str
    state: str | None
    pincode: str | None
    latitude: Decimal | None
    longitude: Decimal | None
    is_default: bool
    created_at: dt.datetime


class AddressPage(Page):
    addresses: list[AddressOut]
