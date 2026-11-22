"""KYC vendor registry — mirrors sms_router provider selection.

The active vendor for *new* DigiLocker/PAN calls is chosen in the admin console
(``platform_settings.kyc_vendor``) and falls back to ``KYC_VENDOR``. Credentials
always stay in env; the console only selects between configured vendors.
"""
from __future__ import annotations

import time

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.services.apisathi_kyc_client import ApiSathiKycClient
from app.services.kyc_types import KycVendor
from app.services.setu_digilocker_client import SetuDigiLockerClient

log = structlog.get_logger()

KYC_VENDOR_SETTING_KEY = "kyc_vendor"
KYC_VENDOR_LABELS = {
    "setu_digilocker": "Setu",
    "apisathi": "API Sathi",
}
# Other API workers pick up a console switch within this window.
_ACTIVE_CACHE_TTL_SECONDS = 10.0

_VENDOR_CACHE: dict[str, KycVendor] = {}
_ACTIVE_CACHE: dict[str, tuple[float, str]] = {}

_VENDOR_FACTORIES = {
    "setu_digilocker": SetuDigiLockerClient,
    "apisathi": ApiSathiKycClient,
}


def _normalize(name: str | None) -> str:
    return (name or "").strip().lower()


def is_known_kyc_vendor(name: str | None) -> bool:
    return _normalize(name) in _VENDOR_FACTORIES


def env_default_kyc_vendor() -> str:
    return _normalize(get_settings().KYC_VENDOR) or "setu_digilocker"


def kyc_vendor_configured(name: str | None) -> bool:
    """True when env holds the credentials this vendor needs for DigiLocker."""
    settings = get_settings()
    key = _normalize(name)
    if key == "setu_digilocker":
        return all(
            (value or "").strip()
            for value in (
                settings.KYC_SETU_CLIENT_ID,
                settings.KYC_SETU_CLIENT_SECRET,
                settings.KYC_SETU_DIGILOCKER_PRODUCT_ID,
            )
        )
    if key == "apisathi":
        return bool((settings.KYC_APISATHI_API_KEY or "").strip())
    return False


def get_kyc_vendor(name: str | None = None) -> KycVendor:
    """Vendor client by name; defaults to ``KYC_VENDOR``.

    Pass ``row.vendor`` for in-flight requests so a vendor switch does not strand them.
    """
    key = _normalize(name) or env_default_kyc_vendor()
    cached = _VENDOR_CACHE.get(key)
    if cached is not None:
        return cached
    factory = _VENDOR_FACTORIES.get(key)
    if factory is None:
        raise ValueError(f"Unknown KYC_VENDOR: {key}")
    client: KycVendor = factory()
    _VENDOR_CACHE[key] = client
    return client


async def read_kyc_vendor_setting(db: AsyncSession) -> tuple[str | None, str | None]:
    """Console-selected vendor and its updated_at, or (None, None) when unset."""
    row = (
        await db.execute(
            text("SELECT value_json, updated_at FROM platform_settings WHERE key = :key"),
            {"key": KYC_VENDOR_SETTING_KEY},
        )
    ).mappings().first()
    if row is None:
        return None, None
    value = row["value_json"] if isinstance(row["value_json"], dict) else {}
    vendor = _normalize(value.get("vendor")) or None
    return vendor, str(row["updated_at"]) if row["updated_at"] else None


async def active_kyc_vendor_name(db: AsyncSession) -> str:
    """Vendor for new KYC/PAN calls: console setting, else ``KYC_VENDOR``."""
    hit = _ACTIVE_CACHE.get(KYC_VENDOR_SETTING_KEY)
    if hit is not None and time.monotonic() - hit[0] < _ACTIVE_CACHE_TTL_SECONDS:
        return hit[1]
    stored, _ = await read_kyc_vendor_setting(db)
    if stored and is_known_kyc_vendor(stored):
        if kyc_vendor_configured(stored):
            name = stored
        else:
            log.error(
                "kyc_vendor_setting_not_configured",
                stored=stored,
                fallback=env_default_kyc_vendor(),
            )
            name = env_default_kyc_vendor()
    else:
        if stored:
            log.warning("kyc_vendor_setting_unknown", stored=stored)
        name = env_default_kyc_vendor()
    _ACTIVE_CACHE[KYC_VENDOR_SETTING_KEY] = (time.monotonic(), name)
    return name


def invalidate_active_kyc_vendor_cache() -> None:
    _ACTIVE_CACHE.clear()
