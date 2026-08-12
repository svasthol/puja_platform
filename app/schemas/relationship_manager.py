"""Relationship manager schemas — admin CRUD + public booking block (§21.4)."""
from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import Page


class RelationshipManagerPublic(BaseModel):
    """Exposed to customer/pujari after booking confirm — name + phone only."""

    id: uuid.UUID
    name: str
    phone: str


class RelationshipManagerOut(BaseModel):
    id: uuid.UUID
    name: str
    phone: str
    city: str | None
    is_active: bool
    is_default: bool = False


class RelationshipManagerListResponse(Page):
    items: list[RelationshipManagerOut]


class RelationshipManagerCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=150)
    phone: str = Field(min_length=10, max_length=15)
    city: str | None = Field(default=None, max_length=80)
    is_active: bool = True
    set_as_default: bool = False


class RelationshipManagerUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str | None = Field(default=None, min_length=1, max_length=150)
    phone: str | None = Field(default=None, min_length=10, max_length=15)
    city: str | None = Field(default=None, max_length=80)
    is_active: bool | None = None
    set_as_default: bool | None = None
    change_reason: str | None = Field(default=None, max_length=300)


class DefaultRelationshipManagerResponse(BaseModel):
    relationship_manager_id: uuid.UUID | None
    name: str | None = None
    phone: str | None = None


class DefaultRelationshipManagerUpdate(BaseModel):
    relationship_manager_id: uuid.UUID | None = None
    change_reason: str | None = Field(default=None, max_length=300)
