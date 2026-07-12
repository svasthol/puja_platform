"""Shared Pydantic v2 schema helpers + cursor pagination (C-PAGINATION).

Cursor format: base64url of the keyset values joined by '|'. Opaque to clients;
every list endpoint returns `next_cursor` (null when exhausted) per
API_CONTRACTS.md intro (`?cursor=&limit=20`, max 50).
"""
from __future__ import annotations

import base64
import binascii

from fastapi import HTTPException, status as http
from pydantic import BaseModel, ConfigDict


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Page(ORMModel):
    next_cursor: str | None = None


def encode_cursor(*parts: object) -> str:
    raw = "|".join(str(p) for p in parts)
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def decode_cursor(cursor: str, expected_parts: int) -> list[str]:
    """Decode an opaque cursor; 422 on anything malformed (client bug or tamper)."""
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        raw = base64.urlsafe_b64decode(padded.encode()).decode()
    except (binascii.Error, UnicodeDecodeError):
        raise HTTPException(http.HTTP_422_UNPROCESSABLE_ENTITY, "Invalid cursor.")
    parts = raw.split("|")
    if len(parts) != expected_parts:
        raise HTTPException(http.HTTP_422_UNPROCESSABLE_ENTITY, "Invalid cursor.")
    return parts
