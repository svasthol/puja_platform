"""Admin catalogue schemas (Sprint 4B Wave 1)."""
from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ContentKind = Literal[
    "inclusion", "exclusion", "insight", "requirement", "faq_q", "faq_a"
]


# ---- Categories -------------------------------------------------------------
class PujaCategoryResponse(BaseModel):
    id: int
    name: str
    slug: str
    description: str | None = None
    display_order: int
    is_active: bool
    image_media_id: uuid.UUID | None = None


class PujaCategoryListResponse(BaseModel):
    categories: list[PujaCategoryResponse]


class PujaCategoryCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=2000)
    change_reason: str | None = Field(default=None, max_length=300)


class PujaCategoryUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = None
    is_active: bool | None = None
    image_media_id: uuid.UUID | None = None
    change_reason: str | None = Field(default=None, max_length=300)


class ReorderRequest(BaseModel):
    ordered_ids: list[int] = Field(min_length=1)
    change_reason: str | None = Field(default=None, max_length=300)


# ---- Pujas ------------------------------------------------------------------
class PujaResponse(BaseModel):
    id: uuid.UUID
    category_id: int
    name: str
    slug: str
    tagline: str | None = None
    description: str | None = None
    duration_minutes: int | None = None
    default_price: Decimal
    price_max: Decimal | None = None
    display_order: int
    is_active: bool
    hero_media_id: uuid.UUID | None = None


class PujaListResponse(BaseModel):
    pujas: list[PujaResponse]


class PujaCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    category_id: int
    name: str = Field(min_length=1, max_length=150)
    tagline: str | None = Field(default=None, max_length=200)
    description: str | None = None
    duration_minutes: int | None = Field(default=None, ge=1, le=24 * 60)
    default_price: Decimal = Field(ge=0)
    price_max: Decimal | None = Field(default=None, ge=0)
    change_reason: str | None = Field(default=None, max_length=300)


class PujaUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    category_id: int | None = None
    name: str | None = Field(default=None, min_length=1, max_length=150)
    tagline: str | None = Field(default=None, max_length=200)
    description: str | None = None
    duration_minutes: int | None = Field(default=None, ge=1, le=24 * 60)
    default_price: Decimal | None = Field(default=None, ge=0)
    price_max: Decimal | None = None
    is_active: bool | None = None
    hero_media_id: uuid.UUID | None = None
    change_reason: str | None = Field(default=None, max_length=300)


class PujaReorderRequest(BaseModel):
    category_id: int
    ordered_ids: list[uuid.UUID] = Field(min_length=1)
    change_reason: str | None = Field(default=None, max_length=300)


class PujaImpactResponse(BaseModel):
    puja_id: uuid.UUID
    active_future_bookings: int
    active_holds_unscoped: int
    note: str = (
        "Holds are not puja-scoped until booking; counts are future non-cancelled bookings. "
        "Price/duration changes may affect live quote window (§20.4)."
    )


# ---- Content ----------------------------------------------------------------
class ContentItemInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    text: str = Field(min_length=1, max_length=4000)
    position: int = Field(ge=0, le=999)


class ContentItemResponse(BaseModel):
    id: uuid.UUID
    kind: ContentKind
    position: int
    text: str
    is_active: bool


class ContentReplaceRequest(BaseModel):
    kind: ContentKind
    items: list[ContentItemInput]
    change_reason: str | None = Field(default=None, max_length=300)


class ContentListResponse(BaseModel):
    kind: ContentKind
    items: list[ContentItemResponse]


# ---- Addons -----------------------------------------------------------------
class PujaAddonResponse(BaseModel):
    id: uuid.UUID
    puja_id: uuid.UUID
    name: str
    description: str | None = None
    price: Decimal
    display_order: int
    is_active: bool


class PujaAddonListResponse(BaseModel):
    addons: list[PujaAddonResponse]


class PujaAddonCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=1000)
    price: Decimal = Field(ge=0)
    change_reason: str | None = Field(default=None, max_length=300)


class PujaAddonUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = None
    price: Decimal | None = Field(default=None, ge=0)
    is_active: bool | None = None
    change_reason: str | None = Field(default=None, max_length=300)


# ---- Media (Wave 2 — §20.2) -------------------------------------------------
MediaEntityType = Literal["puja", "category", "gallery"]


class MediaPresignRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    entity_type: MediaEntityType
    entity_id: uuid.UUID
    content_type: Literal["image/jpeg", "image/png", "image/webp"]
    content_length: int = Field(ge=1, le=5_242_880)
    alt_text: str | None = Field(default=None, max_length=200)
    position: int = Field(default=0, ge=0, le=999)
    change_reason: str | None = Field(default=None, max_length=300)


class MediaPresignResponse(BaseModel):
    media_id: uuid.UUID
    upload_url: str
    upload_method: Literal["PUT"] = "PUT"
    upload_headers: dict[str, str]
    expires_in: int
    s3_key: str


class MediaResponse(BaseModel):
    id: uuid.UUID
    entity_type: MediaEntityType
    entity_id: uuid.UUID
    s3_key: str
    alt_text: str | None = None
    position: int
    upload_status: Literal["pending", "ready", "failed"]
    is_active: bool
    public_url: str | None = None
    created_at: dt.datetime
    confirmed_at: dt.datetime | None = None


class MediaListResponse(BaseModel):
    items: list[MediaResponse]
