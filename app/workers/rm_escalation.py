"""
RM escalation scan — separate beat task (§21.6.F).

Idempotent markers on `booking_dispatch_state` for unaccepted advance bookings:
  Rule 1 — long-lead no-accept timeout (normal RM alert)
  Rule 2 — slot approaching within t24 band (urgent RM alert)
"""
from __future__ import annotations

import structlog

from app.services.dispatch_launch import load_dispatch_settings
from app.workers.sweep import get_connection

log = structlog.get_logger("rm_escalation")

RM_LOCK_KEY = "rm_lock"
RM_LOCK_TTL_SECONDS = 880  # beat cadence 15m; release before next tick

_ADVANCE_REQUESTED_SCOPE = """
    b.booking_class = 'advance'
    AND st.domain = 'booking'
    AND st.code = 'requested'
    AND b.pujari_id IS NULL
    AND b.cancelled_at IS NULL
"""


def scan_rm_escalations(conn) -> dict[str, list[str]]:
    """Apply Rule 1 + Rule 2 idempotent RM escalation markers (§21.6.F)."""
    with conn.cursor() as cur:
        settings = load_dispatch_settings(cur)
        no_accept_hours = settings.rm_escalation_hours_no_accept
        t24_hours = settings.rm_escalation_t24_hours
        fail_hours = settings.advance_dispatch_fail_hours

        cur.execute(
            f"""
            WITH candidates AS (
                SELECT b.id AS booking_id
                FROM bookings b
                JOIN booking_dispatch_state bds ON bds.booking_id = b.id
                JOIN status_types st ON st.id = b.status_id
                WHERE {_ADVANCE_REQUESTED_SCOPE}
                  AND b.paid_at IS NOT NULL
                  AND b.paid_at <= now() - make_interval(hours => %s)
                  AND (b.scheduled_date + b.scheduled_time)
                      > now() + make_interval(hours => %s)
                  AND bds.rm_escalated_no_accept_at IS NULL
                FOR UPDATE OF bds SKIP LOCKED
            ),
            marked AS (
                UPDATE booking_dispatch_state bds
                SET rm_escalated_no_accept_at = now()
                FROM candidates c
                WHERE bds.booking_id = c.booking_id
                  AND bds.rm_escalated_no_accept_at IS NULL
                RETURNING bds.booking_id
            )
            SELECT booking_id FROM marked
            """,
            (no_accept_hours, t24_hours),
        )
        no_accept_ids = [str(row[0]) for row in cur.fetchall()]

        cur.execute(
            f"""
            WITH candidates AS (
                SELECT b.id AS booking_id
                FROM bookings b
                JOIN booking_dispatch_state bds ON bds.booking_id = b.id
                JOIN status_types st ON st.id = b.status_id
                WHERE {_ADVANCE_REQUESTED_SCOPE}
                  AND (b.scheduled_date + b.scheduled_time)
                      <= now() + make_interval(hours => %s)
                  AND (b.scheduled_date + b.scheduled_time)
                      > now() + make_interval(hours => %s)
                  AND bds.rm_escalated_t24_at IS NULL
                FOR UPDATE OF bds SKIP LOCKED
            ),
            marked AS (
                UPDATE booking_dispatch_state bds
                SET rm_escalated_t24_at = now()
                FROM candidates c
                WHERE bds.booking_id = c.booking_id
                  AND bds.rm_escalated_t24_at IS NULL
                RETURNING bds.booking_id
            )
            SELECT booking_id FROM marked
            """,
            (t24_hours, fail_hours),
        )
        approaching_ids = [str(row[0]) for row in cur.fetchall()]

    conn.commit()
    if no_accept_ids or approaching_ids:
        log.info(
            "rm_escalations_marked",
            no_accept=len(no_accept_ids),
            approaching=len(approaching_ids),
        )
    return {"no_accept": no_accept_ids, "approaching": approaching_ids}


try:
    from app.workers.celery_app import celery_app

    @celery_app.task(name="app.workers.rm_escalation.rm_escalation_scan_task")
    def rm_escalation_scan_task() -> dict:
        import redis as redis_lib

        from app.core.config import get_settings

        r = redis_lib.from_url(str(get_settings().REDIS_URL))
        if not r.set(RM_LOCK_KEY, "1", nx=True, ex=RM_LOCK_TTL_SECONDS):
            log.info("rm_escalation_scan_skipped_locked")
            return {"skipped": "locked"}

        conn = get_connection()
        try:
            result = scan_rm_escalations(conn)
            for booking_id in result["no_accept"]:
                celery_app.send_task(
                    "app.workers.notifications.notify_rm_dispatch_escalation",
                    args=[booking_id, "no_accept"],
                )
            for booking_id in result["approaching"]:
                celery_app.send_task(
                    "app.workers.notifications.notify_rm_dispatch_escalation",
                    args=[booking_id, "approaching"],
                )
            return {
                "no_accept": len(result["no_accept"]),
                "approaching": len(result["approaching"]),
                "booking_ids": result,
            }
        finally:
            conn.close()
            r.delete(RM_LOCK_KEY)

except ImportError:
    pass
