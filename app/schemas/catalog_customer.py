"""Customer-facing catalogue schemas (Sprint 4B Wave 4 — C-PUJAS)."""
from __future__ import annotations

import uuid
from decimal import Decimal

from pydantic import BaseModel, Field

from app.schemas.common import Page


class CustomerCategory(BaseModel):
    id: int
    name: str
    slug: str
    description: str | None = None
    display_order: int
    image_url: str | None = None


class CustomerPujaSummary(BaseModel):
    id: uuid.UUID
    category_id: int
    name: str
    slug: str
    tagline: str | None = None
    duration_minutes: int | None = None
    default_price: Decimal
    price_from: Decimal
    price_to: Decimal
    display_order: int
    hero_image_url: str | None = None
    is_muhurat_bound: bool = False


class CustomerPujaListResponse(Page):
    categories: list[CustomerCategory]
    pujas: list[CustomerPujaSummary]


class CustomerContentBlock(BaseModel):
    kind: str
    items: list[str]


class CustomerAddon(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None = None
    price: Decimal
    display_order: int
    image_url: str | None = None


class CustomerGalleryImage(BaseModel):
    url: str
    alt_text: str | None = None
    position: int


class CustomerPujaDetail(BaseModel):
    id: uuid.UUID
    category_id: int
    name: str
    slug: str
    tagline: str | None = None
    description: str | None = None
    duration_minutes: int | None = None
    default_price: Decimal
    price_from: Decimal
    price_to: Decimal
    display_order: int
    hero_image_url: str | None = None
    content: list[CustomerContentBlock] = Field(default_factory=list)
    addons: list[CustomerAddon] = Field(default_factory=list)
    gallery: list[CustomerGalleryImage] = Field(default_factory=list)
    is_muhurat_bound: bool = False


class CustomerPujari(BaseModel):
    id: uuid.UUID
    rating_avg: Decimal
    rating_count: int
    years_experience: int | None = None
    unit_price: Decimal


class CustomerPujariListResponse(Page):
    pujaris: list[CustomerPujari]
