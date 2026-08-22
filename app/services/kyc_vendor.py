"""KYC vendor registry — mirrors sms_router provider selection."""
from __future__ import annotations

from app.core.config import get_settings
from app.services.kyc_types import KycVendor
from app.services.setu_digilocker_client import SetuDigiLockerClient

_VENDOR_CACHE: dict[str, KycVendor] = {}


def get_kyc_vendor() -> KycVendor:
    settings = get_settings()
    name = (settings.KYC_VENDOR or "setu_digilocker").strip().lower()
    cached = _VENDOR_CACHE.get(name)
    if cached is not None:
        return cached
    if name == "setu_digilocker":
        client: KycVendor = SetuDigiLockerClient()
        _VENDOR_CACHE[name] = client
        return client
    raise ValueError(f"Unknown KYC_VENDOR: {name}")
