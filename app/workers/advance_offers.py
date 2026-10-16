"""
Advance offer TTL refresh — separate beat task (§21.6.D).

Extends `expires_at` in place for live advance offers on active requested bookings.
Never INSERTs (would trip ux_booking_assignments_one_live).
"""
from __future__ import annotations

import structlog

from app.services.dispatch_launch import load_dispatch_settings
from app.workers.sweep import get_connection

log = structlog.get_logger("advance_offers")

REFRESH_LOCK_TTL_SECONDS = 280  # beat cadence 5m; release before next tick


def refresh_advance_offers(conn) -> int:
    """In-place TTL extension for carved-out advance offers (§21.6.D)."""
    with conn.cursor() as cur:
        settings = load_dispatch_settings(cur)
        ttl_hours = settings.advance_offer_ttl_hours
        cur.execute(
            f"""
            UPDATE booking_assignments ba
            SET expires_at = now() + interval '{ttl_hours} hours'
            FROM bookings b
            JOIN booking_dispatch_state bds ON bds.booking_id = b.id
            JOIN status_types bst ON bst.id = b.status_id
            WHERE ba.booking_id = b.id
              AND ba.responded_at IS NULL
              AND ba.status_id = (
                  SELECT id FROM status_types
                  WHERE domain = 'assignment' AND code = 'offered'
              )
              AND b.booking_class = 'advance'
              AND bst.domain = 'booking'
              AND bst.code = 'requested'
              AND b.cancelled_at IS NULL
              AND bds.urgency_escalated_at IS NULL
              AND (bds.dispatch_deadline IS NULL OR bds.dispatch_deadline > now())
            """,
        )
        refreshed = cur.rowcount
    conn.commit()
    if refreshed:
        log.info("advance_offers_refreshed", count=refreshed)
    return refreshed


try:
    from app.workers.celery_app import celery_app

    from app.workers.redis_sync import (
        acquire_lock,
        get_sync_redis,
        namespaced_key,
        new_lock_token,
        release_lock,
    )

    @celery_app.task(name="app.workers.advance_offers.refresh_advance_offers_task")
    def refresh_advance_offers_task() -> dict:
        lock_key = namespaced_key("refresh_advance_offers_lock")
        lock_token = new_lock_token()
        r = get_sync_redis()
        if not acquire_lock(r, lock_key, lock_token, ttl_seconds=REFRESH_LOCK_TTL_SECONDS):
            log.info("refresh_advance_offers_skipped_locked")
            return {"skipped": "locked"}

        conn = get_connection()
        try:
            count = refresh_advance_offers(conn)
            return {"refreshed": count}
        finally:
            conn.close()
            release_lock(r, lock_key, lock_token)

except ImportError:
    pass
