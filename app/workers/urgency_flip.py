"""
Advance→instant urgency flip — separate beat task (§21.6.E).

When a frozen advance booking's slot crosses `instant_lead_hours`, mark
`urgency_escalated_at` (idempotent), shorten live offers to instant TTL, and
enqueue high-priority `offer_instant` FCM to current holders.
"""
from __future__ import annotations

import structlog

from app.services.dispatch_launch import load_dispatch_settings
from app.workers.sweep import get_connection

log = structlog.get_logger("urgency_flip")

URGENCY_LOCK_KEY = "urgency_lock"
URGENCY_LOCK_TTL_SECONDS = 110  # beat cadence 2m; release before next tick


def escalate_urgency_on_threshold(conn) -> list[str]:
    """Flip advance bookings inside instant lead window (§21.6.E)."""
    with conn.cursor() as cur:
        settings = load_dispatch_settings(cur)
        instant_lead = settings.instant_lead_hours
        ttl_seconds = settings.instant_offer_ttl_seconds
        cur.execute(
            """
            WITH candidates AS (
                SELECT b.id AS booking_id
                FROM bookings b
                JOIN booking_dispatch_state bds ON bds.booking_id = b.id
                JOIN status_types st ON st.id = b.status_id
                WHERE b.booking_class = 'advance'
                  AND st.domain = 'booking'
                  AND st.code = 'requested'
                  AND b.pujari_id IS NULL
                  AND b.cancelled_at IS NULL
                  AND bds.urgency_escalated_at IS NULL
                  AND (b.scheduled_date + b.scheduled_time)
                      <= now() + make_interval(hours => %s)
                FOR UPDATE OF bds SKIP LOCKED
            ),
            flipped AS (
                UPDATE booking_dispatch_state bds
                SET urgency_escalated_at = now()
                FROM candidates c
                WHERE bds.booking_id = c.booking_id
                  AND bds.urgency_escalated_at IS NULL
                RETURNING bds.booking_id
            )
            SELECT booking_id FROM flipped
            """,
            (instant_lead,),
        )
        booking_ids = [str(row[0]) for row in cur.fetchall()]

        for booking_id in booking_ids:
            cur.execute(
                f"""
                UPDATE booking_assignments ba
                SET expires_at = now() + interval '{ttl_seconds} seconds'
                FROM bookings b
                WHERE ba.booking_id = b.id
                  AND b.id = %s
                  AND ba.responded_at IS NULL
                  AND ba.status_id = (
                      SELECT id FROM status_types
                      WHERE domain = 'assignment' AND code = 'offered'
                  )
                  AND ba.expires_at > now()
                """,
                (booking_id,),
            )
    conn.commit()
    if booking_ids:
        log.info("urgency_flipped", count=len(booking_ids), booking_ids=booking_ids)
    return booking_ids


try:
    from app.workers.celery_app import celery_app

    @celery_app.task(name="app.workers.urgency_flip.escalate_urgency_on_threshold_task")
    def escalate_urgency_on_threshold_task() -> dict:
        import redis as redis_lib

        from app.core.config import get_settings

        r = redis_lib.from_url(str(get_settings().REDIS_URL))
        if not r.set(URGENCY_LOCK_KEY, "1", nx=True, ex=URGENCY_LOCK_TTL_SECONDS):
            log.info("escalate_urgency_skipped_locked")
            return {"skipped": "locked"}

        conn = get_connection()
        try:
            flipped = escalate_urgency_on_threshold(conn)
            for booking_id in flipped:
                celery_app.send_task(
                    "app.workers.notifications.notify_offer_instant",
                    args=[booking_id],
                )
            return {"flipped": len(flipped), "booking_ids": flipped}
        finally:
            conn.close()
            r.delete(URGENCY_LOCK_KEY)

except ImportError:
    pass
