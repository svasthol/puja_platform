"""Shared phone normalization for SMS providers (India)."""
from __future__ import annotations

import re


def normalize_india_mobile_e164(phone: str) -> str:
    """MSG91-style: 91XXXXXXXXXX (no '+')."""
    digits = re.sub(r"\D", "", phone)
    if digits.startswith("91") and len(digits) == 12:
        return digits
    if len(digits) == 10:
        return f"91{digits}"
    if digits.startswith("0") and len(digits) == 11:
        return f"91{digits[1:]}"
    return digits


def normalize_india_mobile_ten(phone: str) -> str:
    """FAST2SMS-style: 10-digit mobile without country code."""
    e164 = normalize_india_mobile_e164(phone)
    if e164.startswith("91") and len(e164) == 12:
        return e164[2:]
    return re.sub(r"\D", "", phone)[-10:]
