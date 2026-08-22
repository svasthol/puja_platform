"""KYC vendor registry tests."""
from __future__ import annotations

import pytest

from app.services.kyc_types import KycVendor
from app.services.kyc_vendor import get_kyc_vendor
from app.services.setu_digilocker_client import SetuDigiLockerClient


def test_get_kyc_vendor_returns_setu_by_default():
    vendor = get_kyc_vendor()
    assert isinstance(vendor, SetuDigiLockerClient)
    assert vendor.vendor_name == "setu_digilocker"


def test_setu_client_implements_protocol():
    client = SetuDigiLockerClient()
    assert isinstance(client, KycVendor)
