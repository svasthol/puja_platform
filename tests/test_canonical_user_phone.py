"""Tests for canonical users.phone normalization (identity)."""
from __future__ import annotations

import pytest

from app.services.sms_phone import (
    InvalidIndiaPhoneError,
    canonical_user_phone,
    normalize_india_mobile_e164,
    normalize_india_mobile_ten,
)


class TestCanonicalUserPhone:
    def test_ten_digit(self):
        assert canonical_user_phone("9515165674") == "+919515165674"

    def test_e164_plus(self):
        assert canonical_user_phone("+919515165674") == "+919515165674"

    def test_e164_no_plus(self):
        assert canonical_user_phone("919515165674") == "+919515165674"

    def test_leading_zero(self):
        assert canonical_user_phone("09515165674") == "+919515165674"

    def test_spaces(self):
        assert canonical_user_phone("  +91 95151 65674 ") == "+919515165674"

    def test_all_forms_equal(self):
        forms = ("9515165674", "+919515165674", "919515165674", "09515165674")
        canon = {canonical_user_phone(f) for f in forms}
        assert canon == {"+919515165674"}

    def test_rejects_short(self):
        with pytest.raises(InvalidIndiaPhoneError):
            canonical_user_phone("12345")

    def test_rejects_invalid_start_digit(self):
        with pytest.raises(InvalidIndiaPhoneError):
            canonical_user_phone("5123456789")

    def test_sms_helpers_stay_aligned(self):
        raw = "+919876543210"
        assert canonical_user_phone(raw) == "+919876543210"
        assert normalize_india_mobile_ten(raw) == "9876543210"
        assert normalize_india_mobile_e164(raw) == "919876543210"
