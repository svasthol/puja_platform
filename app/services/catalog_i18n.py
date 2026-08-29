"""Catalogue locale helpers — te/en only (matches panchangam)."""
from __future__ import annotations

SUPPORTED_LOCALES: frozenset[str] = frozenset({"te", "en"})
DEFAULT_LOCALE = "te"


def normalize_locale(locale: str | None) -> str:
    if isinstance(locale, str) and locale.lower() in SUPPORTED_LOCALES:
        return locale.lower()
    return DEFAULT_LOCALE


def locale_fallback_chain(requested: str) -> tuple[str, ...]:
    """Resolution order for missing translation rows."""
    if requested == "te":
        return ("te", "en")
    return ("en", "te")
