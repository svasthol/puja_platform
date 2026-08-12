"""Slug helpers for catalogue entities (SPEC_AMENDMENTS §20.4 — immutable after create)."""
from __future__ import annotations

import re
import uuid


def slugify_name(name: str, *, suffix: str = "") -> str:
    base = re.sub(r"[^a-zA-Z0-9]+", "-", name.strip().lower()).strip("-")
    if not base:
        base = "item"
    if suffix:
        base = f"{base}-{suffix}"
    return base[:120]


def unique_slug(base: str, *, salt: str | None = None) -> str:
    """Append a short salt when the base slug collides."""
    token = salt or uuid.uuid4().hex[:8]
    trimmed = base[: max(1, 120 - len(token) - 1)]
    return f"{trimmed}-{token}"
