"""Pujari tax compliance fields for TDS accrual (pan_hash, entity_type)."""
from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import re
import uuid

import structlog
from fastapi import HTTPException, status as http
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.services.kyc_types import KycVendorError
from app.core.redis_client import redis_set_nx
from app.services.kyc_vendor import active_kyc_vendor_name, get_kyc_vendor
from app.services.pricing import ALLOWED_ENTITY_TYPES

log = structlog.get_logger()

_PAN_RE = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")


def hash_pan(pan: str) -> str:
    """HMAC-SHA256 of normalized PAN (pepper from KYC_IDENTITY_PEPPER)."""
    settings = get_settings()
    pepper = settings.KYC_IDENTITY_PEPPER or settings.SECRET_KEY
    normalized = pan.strip().upper()
    return hmac.new(pepper.encode(), normalized.encode(), hashlib.sha256).hexdigest()


def validate_pan(pan: str) -> str:
    normalized = pan.strip().upper()
    if not _PAN_RE.match(normalized):
        raise HTTPException(http.HTTP_422_UNPROCESSABLE_ENTITY, "Invalid PAN format.")
    return normalized


async def _verify_pan_with_vendor(
    vendor,
    *,
    pan: str,
    consent: bool,
    reason: str,
):
    """One immediate retry on transient vendor failures (vendor-agnostic)."""
    last: KycVendorError | None = None
    for attempt in range(2):
        try:
            return await vendor.verify_pan(pan=pan, consent=consent, reason=reason)
        except KycVendorError as exc:
            last = exc
            if attempt == 0 and exc.retryable:
                log.warning(
                    "pan_verify_retry",
                    vendor=vendor.vendor_name,
                    error_code=exc.code,
                )
                continue
            raise
    assert last is not None
    raise last


def _map_kyc_vendor_error(exc: KycVendorError, *, vendor_name: str) -> HTTPException:
    if exc.code == "pan_not_found":
        settings = get_settings()
        base = (settings.KYC_SETU_BASE_URL or "").lower()
        setu_sandbox = vendor_name == "setu_digilocker" and (
            "sandbox" in base or settings.APP_ENV != "production"
        )
        if setu_sandbox:
            detail = (
                "Setu sandbox does not verify real PANs against Income Tax. "
                "For local/staging tests use sandbox PAN ABCDE1234A (ABCDE1234B = invalid). "
                "Your PAN format may be correct; switch to production Setu only when going live."
            )
        else:
            detail = str(exc)
        return HTTPException(http.HTTP_422_UNPROCESSABLE_ENTITY, detail)
    if exc.code in ("consent_required", "reason_too_short"):
        return HTTPException(http.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    if exc.code == "vendor_config":
        return HTTPException(http.HTTP_503_SERVICE_UNAVAILABLE, str(exc))
    if exc.code in ("vendor_auth", "insufficient_balance", "product_retired"):
        log.error("pan_vendor_unavailable", vendor=vendor_name, error_code=exc.code)
        return HTTPException(
            http.HTTP_503_SERVICE_UNAVAILABLE,
            "PAN verification is temporarily unavailable. Contact support.",
        )
    if exc.retryable:
        return HTTPException(
            http.HTTP_502_BAD_GATEWAY,
            "PAN verification is temporarily unavailable. Wait a minute and try again.",
        )
    return HTTPException(http.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))


async def update_tax_compliance(
    db: AsyncSession,
    *,
    pujari_id: uuid.UUID,
    entity_type: str,
    pan: str | None = None,
    clear_pan: bool = False,
) -> dict:
    """Admin-set entity_type and optional PAN hash for TDS accrual."""
    if entity_type not in ALLOWED_ENTITY_TYPES:
        raise HTTPException(
            http.HTTP_422_UNPROCESSABLE_ENTITY,
            f"entity_type must be one of: {', '.join(sorted(ALLOWED_ENTITY_TYPES))}.",
        )
    pan_hash: str | None = None
    if clear_pan:
        pan_hash = None
    elif pan is not None:
        pan_hash = hash_pan(validate_pan(pan))
    else:
        existing = (
            await db.execute(
                text("SELECT pan_hash FROM pujaris WHERE id = :pid"),
                {"pid": str(pujari_id)},
            )
        ).scalar_one_or_none()
        if existing is None:
            raise HTTPException(http.HTTP_404_NOT_FOUND, "Pujari not found.")
        pan_hash = existing

    result = await db.execute(
        text(
            """
            UPDATE pujaris
            SET entity_type = :et,
                pan_hash = :ph,
                updated_at = now()
            WHERE id = :pid
            """
        ),
        {"et": entity_type, "ph": pan_hash, "pid": str(pujari_id)},
    )
    if result.rowcount == 0:
        raise HTTPException(http.HTTP_404_NOT_FOUND, "Pujari not found.")
    return {
        "pujari_id": str(pujari_id),
        "entity_type": entity_type,
        "pan_on_file": pan_hash is not None,
    }


async def submit_partner_pan(
    db: AsyncSession,
    *,
    pujari_id: uuid.UUID,
    entity_type: str,
    pan: str,
    consent: bool,
    reason: str,
) -> dict:
    """Validate PAN with the KYC vendor when configured; store hash + pan_status (never log raw PAN)."""
    if not consent:
        raise HTTPException(
            http.HTTP_422_UNPROCESSABLE_ENTITY,
            "Consent is required to store PAN for TDS.",
        )
    normalized = validate_pan(pan)
    settings = get_settings()
    pan_status = "unverified"
    verified_name: str | None = None
    user_message = "PAN recorded for tax compliance."

    vendor = get_kyc_vendor(await active_kyc_vendor_name(db))
    if vendor.pan_verification_enabled():
        pan_interval = settings.KYC_VENDOR_PAN_MIN_INTERVAL_SECONDS
        if pan_interval > 0:
            pan_slot = await redis_set_nx(
                f"kyc:pan_verify:{pujari_id}",
                "1",
                ex=pan_interval,
            )
            if not pan_slot:
                raise HTTPException(
                    http.HTTP_429_TOO_MANY_REQUESTS,
                    "PAN was just submitted. Wait a moment before trying again.",
                )
        try:
            result = await _verify_pan_with_vendor(
                vendor,
                pan=normalized,
                consent=consent,
                reason=reason,
            )
        except KycVendorError as exc:
            raise _map_kyc_vendor_error(exc, vendor_name=vendor.vendor_name) from exc
        if not result.is_success:
            raise HTTPException(
                http.HTTP_422_UNPROCESSABLE_ENTITY,
                result.message or "PAN verification failed.",
            )
        pan_status = "operative"
        verified_name = result.full_name
        user_message = result.message or "PAN verified successfully."
        log.info(
            "pan_verified",
            vendor=vendor.vendor_name,
            pujari_id=str(pujari_id)[:8],
            trace_id=result.trace_id,
            category=result.category,
        )
    elif settings.APP_ENV == "production":
        raise HTTPException(
            http.HTTP_503_SERVICE_UNAVAILABLE,
            "PAN verification is not configured. Contact support.",
        )
    else:
        log.warning(
            "pan_stored_without_vendor_verify",
            vendor=vendor.vendor_name,
            pujari_id=str(pujari_id)[:8],
            app_env=settings.APP_ENV,
        )
        user_message = (
            "PAN saved for testing. Configure the KYC vendor PAN product for operative verification."
        )

    await update_tax_compliance(
        db,
        pujari_id=pujari_id,
        entity_type=entity_type,
        pan=normalized,
    )
    await db.execute(
        text(
            """
            UPDATE pujaris
            SET pan_status = :st, updated_at = now()
            WHERE id = :pid
            """
        ),
        {"st": pan_status, "pid": str(pujari_id)},
    )
    return {
        "pujari_id": str(pujari_id),
        "entity_type": entity_type,
        "pan_on_file": True,
        "pan_status": pan_status,
        "verified_name": verified_name,
        "message": user_message,
    }
