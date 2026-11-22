"""KYC vendor registry tests."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from app.core.config import get_settings
from app.services.apisathi_kyc_client import ApiSathiKycClient
from app.services.kyc_types import KycVendor
from app.services.kyc_vendor import get_kyc_vendor
from app.services.setu_digilocker_client import SetuDigiLockerClient


def test_get_kyc_vendor_returns_setu_by_default():
    with patch.object(get_settings(), "KYC_VENDOR", "setu_digilocker"):
        vendor = get_kyc_vendor()
    assert isinstance(vendor, SetuDigiLockerClient)
    assert vendor.vendor_name == "setu_digilocker"


def test_setu_client_implements_protocol():
    client = SetuDigiLockerClient()
    assert isinstance(client, KycVendor)


def test_get_kyc_vendor_selects_apisathi_from_settings():
    with patch.object(get_settings(), "KYC_VENDOR", "apisathi"):
        vendor = get_kyc_vendor()
    assert isinstance(vendor, ApiSathiKycClient)
    assert vendor.vendor_name == "apisathi"


def test_get_kyc_vendor_by_row_vendor_name_overrides_setting():
    with patch.object(get_settings(), "KYC_VENDOR", "apisathi"):
        vendor = get_kyc_vendor("setu_digilocker")
    assert isinstance(vendor, SetuDigiLockerClient)


def test_get_kyc_vendor_unknown_raises():
    with pytest.raises(ValueError):
        get_kyc_vendor("nope")
