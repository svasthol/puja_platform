"""Puja MVP launch policy guards (SPEC_AMENDMENTS §21.1)."""
from __future__ import annotations

from fastapi import HTTPException, status as http

# Phase 2 flips this when direct booking is re-enabled.
DIRECT_BOOKING_ENABLED = False

_DIRECT_DISABLED_MSG = (
    "Direct booking is disabled at launch. All bookings use citywide broadcast."
)


def reject_direct_booking() -> None:
    """410 when a client attempts direct-booking flows at launch."""
    if not DIRECT_BOOKING_ENABLED:
        raise HTTPException(http.HTTP_410_GONE, _DIRECT_DISABLED_MSG)
