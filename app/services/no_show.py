"""Stuck confirmed / no-show detection (P-SWEEP-CONFIRMED, Option B — alert only)."""
from __future__ import annotations

import zoneinfo

from app.core.config import get_settings
from app.services.reconfirmation import slot_local_expr

_TZ = zoneinfo.ZoneInfo(get_settings().PLATFORM_TIMEZONE)
DEFAULT_GRACE_MINUTES = 90


def stuck_confirmed_sql(grace_minutes: int = DEFAULT_GRACE_MINUTES) -> str:
    """Bookings past slot + grace, still confirmed with an assigned pujari, no alert yet."""
    slot = slot_local_expr("b")
    return f"""
        SELECT b.id, {slot} AS slot_at
        FROM bookings b
        JOIN status_types st ON st.id = b.status_id
        WHERE st.domain = 'booking' AND st.code = 'confirmed'
          AND b.cancelled_at IS NULL
          AND b.pujari_id IS NOT NULL
          AND now() >= {slot} + make_interval(mins => {grace_minutes})
          AND NOT EXISTS (
            SELECT 1 FROM booking_no_show_alerts bna
            WHERE bna.booking_id = b.id
          )
        FOR UPDATE OF b SKIP LOCKED
    """
