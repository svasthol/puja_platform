"""Load public app config from platform_settings (§23.2)."""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.schemas.app_config import AppConfigResponse
from app.services.booking_gate import load_booking_gate_settings
from app.services.relationship_manager import fetch_default_rm_public

_settings = get_settings()


async def load_app_config(db: AsyncSession) -> AppConfigResponse:
    gate = await load_booking_gate_settings(db)
    row = (
        await db.execute(
            text(
                "SELECT value_json FROM platform_settings "
                "WHERE key = 'advance_booking_amount'"
            )
        )
    ).scalar_one_or_none()
    if row is None:
        amount = Decimal(str(_settings.DEFAULT_ADVANCE_BOOKING_AMOUNT))
    else:
        amount = Decimal(str(row.get("amount", _settings.DEFAULT_ADVANCE_BOOKING_AMOUNT)))
    key_id = (_settings.RAZORPAY_KEY_ID or "").strip()
    payments_enabled = key_id.startswith("rzp_")
    muhurat_help = await fetch_default_rm_public(db)
    return AppConfigResponse(
        night_bookings_enabled=gate.night_bookings_enabled,
        instant_lead_hours=gate.instant_lead_hours,
        advance_booking_amount=amount,
        razorpay_key_id=key_id if payments_enabled else None,
        payments_enabled=payments_enabled,
        muhurat_help_contact=muhurat_help,
    )
