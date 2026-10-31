"""Shared phone normalization for SMS providers (India) and identity (users.phone)."""
from __future__ import annotations

import re


class InvalidIndiaPhoneError(ValueError):
    """Input cannot be normalized to a canonical Indian mobile."""


def _india_mobile_ten_digits(phone: str) -> str:
    """Validate and return 10-digit Indian mobile (no country code)."""
    raw = (phone or "").strip()
    if not raw:
        raise InvalidIndiaPhoneError("Phone number is required.")
    digits = re.sub(r"\D", "", raw)
    if digits.startswith("91") and len(digits) == 12:
        ten = digits[2:]
    elif len(digits) == 10:
        ten = digits
    elif digits.startswith("0") and len(digits) == 11:
        ten = digits[1:]
    else:
        raise InvalidIndiaPhoneError(
            "Enter a valid 10-digit Indian mobile number (optional +91 prefix)."
        )
    if len(ten) != 10 or not ten.isdigit():
        raise InvalidIndiaPhoneError(
            "Enter a valid 10-digit Indian mobile number (optional +91 prefix)."
        )
    if ten[0] not in "6789":
        raise InvalidIndiaPhoneError(
            "Indian mobile numbers must start with 6, 7, 8, or 9."
        )
    return ten


def canonical_user_phone(phone: str) -> str:
    """Canonical storage key for ``users.phone`` and OTP rows: ``+91XXXXXXXXXX``.

    All login paths must normalize to this form before DB read/write so
    ``9515165674`` and ``+919515165674`` resolve to one user.
    """
    return f"+91{_india_mobile_ten_digits(phone)}"


def normalize_india_mobile_e164(phone: str) -> str:
    """MSG91-style: 91XXXXXXXXXX (no '+')."""
    ten = _india_mobile_ten_digits(phone)
    return f"91{ten}"


def normalize_india_mobile_ten(phone: str) -> str:
    """FAST2SMS-style: 10-digit mobile without country code."""
    return _india_mobile_ten_digits(phone)
