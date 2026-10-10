"""Load public app config from platform_settings (§23.2)."""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.schemas.app_config import AppConfigResponse
from app.services.booking_gate import load_booking_gate_settings
from app.services.pricing import BOOKING_FEE_LABEL, load_booking_fee_setting
from app.services.relationship_manager import fetch_default_rm_public

_settings = get_settings()


async def load_app_config(db: AsyncSession) -> AppConfigResponse:
    gate = await load_booking_gate_settings(db)
    advance_row = (
        await db.execute(
            text(
                "SELECT value_json FROM platform_settings "
                "WHERE key = 'advance_booking_amount'"
            )
        )
    ).scalar_one_or_none()
    if advance_row is None:
        advance = Decimal(str(_settings.DEFAULT_ADVANCE_BOOKING_AMOUNT))
    else:
        advance = Decimal(str(advance_row.get("amount", _settings.DEFAULT_ADVANCE_BOOKING_AMOUNT)))

    booking_fee, fee_label = await load_booking_fee_setting(db)
    key_id = (_settings.RAZORPAY_KEY_ID or "").strip()
    payments_enabled = key_id.startswith("rzp_")
    muhurat_help = await fetch_default_rm_public(db)
    pan_product = (_settings.KYC_SETU_PAN_PRODUCT_ID or "").strip()
    return AppConfigResponse(
        night_bookings_enabled=gate.night_bookings_enabled,
        instant_lead_hours=gate.instant_lead_hours,
        advance_booking_amount=advance,
        booking_fee=booking_fee,
        booking_fee_label=fee_label or BOOKING_FEE_LABEL,
        full_online_enabled=_settings.FULL_ONLINE_ENABLED,
        razorpay_key_id=key_id if payments_enabled else None,
        payments_enabled=payments_enabled,
        muhurat_help_contact=muhurat_help,
        tds_accrual_enabled=_settings.TDS_ACCRUAL_ENABLED,
        pan_accept_gate_enabled=_settings.PAN_ACCEPT_GATE_ENABLED,
        pujari_tax_profile_required_for_accept=_settings.PUJARI_TAX_PROFILE_REQUIRED_FOR_ACCEPT,
        pujari_fy_pan_gate_enabled=_settings.PUJARI_FY_PAN_GATE_ENABLED,
        setu_pan_verify_configured=bool(pan_product),
    )
