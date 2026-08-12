"""
Sweep worker — psycopg3 (sync), v3 spec (all 5 steps).

Scheduled by Celery Beat every 30s (see celery_app.py beat_schedule).
Core logic is plain functions taking a psycopg3 connection, so it is testable
with psycopg alone, no broker required.

Spec: DISPATCH_FLOW.md "Expiry, abandonment, and re-broadcast (sweep worker)".
Steps:
  1. Release expired slot_holds.
  2. Flip payment_pending bookings >15min to 'abandoned' + cancelled_at, and
     release ONLY the hold linked to each abandoned booking (bookings.hold_id).
  3. Flip 'offered' assignments past expiry to 'expired' + responded_at
     (carve-out: advance offers on active requested bookings inside dispatch
     window are refreshed by refresh_advance_offers beat instead — §21.6.D).
  4. Independently scan stranded bookings -> enqueue rebroadcast.
  5. Lazily sync pujaris.is_online from Redis presence keys (analytics only).
  6. Advance reconfirmation pings + RM escalation (§21.7).
  7. Stuck-state ops monitor (P-MONITOR) — payment_pending, no-show, refund stall.

FIX (was a latent bug): step 2 previously released ALL of a user's active holds
(WHERE user_id IN ...). It now releases only the hold tied to the abandoned
booking via bookings.hold_id, so an unrelated live hold on another slot survives.

Safety:
  - Redis "sweep_lock" NX EX 25 prevents overlapping beat ticks stacking.
  - FOR UPDATE SKIP LOCKED throughout.
  - Every step commits independently; step 4 re-scans from scratch (self-healing).
"""
from __future__ import annotations

import os

import psycopg
import structlog
from psycopg.rows import tuple_row

log = structlog.get_logger("sweep")


def _normalize_db_url(url: str) -> str:
    """psycopg.connect() wants a libpq URL, not a SQLAlchemy driver URL."""
    return url.replace("postgresql+psycopg://", "postgresql://").replace(
        "postgresql+psycopg2://", "postgresql://"
    )


def _database_url() -> str:
    try:
        from app.core.config import get_settings

        raw = str(get_settings().DATABASE_URL)
    except Exception:
        raw = os.environ.get("DATABASE_URL", "postgresql://postgres@localhost:5432/mana_guruji")
    return _normalize_db_url(raw)


def get_connection() -> psycopg.Connection:
    return psycopg.connect(_database_url(), row_factory=tuple_row)


# --------------------------------------------------------------------------- #
# Step 1 — release expired slot holds
# --------------------------------------------------------------------------- #
def release_expired_slot_holds(conn: psycopg.Connection) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            WITH expired AS (
                SELECT id FROM slot_holds
                WHERE released_at IS NULL AND expires_at <= now()
                FOR UPDATE SKIP LOCKED
            )
            UPDATE slot_holds sh SET released_at = now()
            FROM expired WHERE sh.id = expired.id
            RETURNING sh.id
            """
        )
        n = cur.rowcount
    conn.commit()
    if n:
        log.info("holds_released", count=n)
    return n


# --------------------------------------------------------------------------- #
# Step 2 — abandon stale payment_pending bookings (+ cancelled_at + history +
#          release the LINKED hold only)
# --------------------------------------------------------------------------- #
def abandon_stale_payment_pending(conn: psycopg.Connection, ttl_minutes: int = 15) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            WITH pending AS (
                SELECT b.id, b.hold_id
                FROM bookings b
                JOIN status_types st ON st.id = b.status_id
                WHERE st.domain = 'booking' AND st.code = 'payment_pending'
                  AND b.cancelled_at IS NULL
                  AND b.created_at <= now() - make_interval(mins => %s)
                FOR UPDATE OF b SKIP LOCKED
            ),
            flipped AS (
                UPDATE bookings b
                SET status_id = (SELECT id FROM status_types
                                 WHERE domain='booking' AND code='abandoned'),
                    cancelled_at = now(),
                    updated_at = now()
                FROM pending
                WHERE b.id = pending.id
                RETURNING b.id, b.status_id, pending.hold_id
            ),
            hist AS (
                INSERT INTO booking_status_history (booking_id, status_id, changed_by)
                SELECT id, status_id, NULL FROM flipped
            ),
            rel AS (
                -- Release ONLY the hold linked to each abandoned booking.
                UPDATE slot_holds sh SET released_at = now()
                FROM flipped
                WHERE sh.id = flipped.hold_id AND sh.released_at IS NULL
            )
            SELECT id FROM flipped
            """,
            (ttl_minutes,),
        )
        booking_ids = [r[0] for r in cur.fetchall()]
    conn.commit()
    if booking_ids:
        log.info("bookings_abandoned", count=len(booking_ids))
    return len(booking_ids)


# --------------------------------------------------------------------------- #
# Step 3 — expire stale 'offered' assignments (+ responded_at)
# --------------------------------------------------------------------------- #
def expire_stale_assignments(conn: psycopg.Connection) -> list[str]:
    """Expire past-TTL offers. Advance live offers are carved out (§21.6.D)."""
    with conn.cursor() as cur:
        cur.execute(
            """
            WITH stale AS (
                SELECT ba.id, ba.booking_id
                FROM booking_assignments ba
                JOIN status_types st ON st.id = ba.status_id
                JOIN bookings b ON b.id = ba.booking_id
                JOIN status_types bst ON bst.id = b.status_id
                LEFT JOIN booking_dispatch_state bds ON bds.booking_id = b.id
                WHERE st.domain = 'assignment' AND st.code = 'offered'
                  AND ba.responded_at IS NULL
                  AND ba.expires_at <= now()
                  AND NOT (
                      b.booking_class = 'advance'
                      AND bst.domain = 'booking'
                      AND bst.code = 'requested'
                      AND b.cancelled_at IS NULL
                      AND bds.urgency_escalated_at IS NULL
                      AND bds.dispatch_deadline IS NOT NULL
                      AND bds.dispatch_deadline > now()
                  )
                FOR UPDATE OF ba SKIP LOCKED
            )
            UPDATE booking_assignments ba
            SET status_id = (SELECT id FROM status_types
                             WHERE domain='assignment' AND code='expired'),
                responded_at = now()
            FROM stale WHERE ba.id = stale.id
            RETURNING stale.booking_id
            """
        )
        booking_ids = sorted({str(r[0]) for r in cur.fetchall()})
    conn.commit()
    if booking_ids:
        log.info("offers_expired", booking_count=len(booking_ids))
    return booking_ids


# --------------------------------------------------------------------------- #
# Step 4a — exhaust requested bookings past dispatch_deadline (launch)
# --------------------------------------------------------------------------- #
def exhaust_past_dispatch_deadline(conn: psycopg.Connection) -> list[str]:
    from app.workers.dispatch import exhaust_booking_no_pujari

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT b.id
            FROM bookings b
            JOIN booking_dispatch_state bds ON bds.booking_id = b.id
            JOIN status_types st ON st.id = b.status_id
            WHERE st.domain = 'booking' AND st.code = 'requested'
              AND b.pujari_id IS NULL
              AND b.cancelled_at IS NULL
              AND bds.dispatch_deadline IS NOT NULL
              AND bds.dispatch_deadline <= now()
            FOR UPDATE OF b SKIP LOCKED
            """
        )
        booking_ids = [str(r[0]) for r in cur.fetchall()]
    conn.commit()

    exhausted: list[str] = []
    for booking_id in booking_ids:
        with conn.cursor() as cur:
            result = exhaust_booking_no_pujari(cur, conn, booking_id)
            if result.get("status") == "failed_no_pujari":
                exhausted.append(booking_id)
    if exhausted:
        log.info("dispatch_deadline_exhausted", count=len(exhausted))
    return exhausted


# --------------------------------------------------------------------------- #
# Step 4 — independent scan for stranded bookings needing (re)dispatch
# --------------------------------------------------------------------------- #
def bookings_needing_initial_broadcast(conn: psycopg.Connection) -> list[str]:
    """Paid requested bookings inside the dispatch window that never finished a round.

    Covers lost `broadcast_booking` tasks (no dispatch row yet) and `fresh=True`
    resets where `last_dispatched` was cleared. Does not overlap rebroadcast scan.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT b.id
            FROM bookings b
            JOIN status_types st ON st.id = b.status_id
            LEFT JOIN booking_dispatch_state bds ON bds.booking_id = b.id
            WHERE st.domain = 'booking' AND st.code = 'requested'
              AND b.pujari_id IS NULL
              AND b.cancelled_at IS NULL
              AND b.paid_at IS NOT NULL
              AND (bds.last_dispatched IS NULL)
              AND (bds.exhausted_at IS NULL)
              AND (
                  bds.booking_id IS NULL
                  OR (
                      (bds.dispatch_starts_at IS NULL OR bds.dispatch_starts_at <= now())
                      AND (bds.dispatch_deadline IS NULL OR bds.dispatch_deadline > now())
                  )
              )
            """
        )
        return [str(r[0]) for r in cur.fetchall()]


def bookings_needing_rebroadcast(conn: psycopg.Connection) -> list[str]:
    """Requested bookings that already broadcast but have zero live offers (DISPATCH_FLOW §4).

    Includes rounds that inserted `offers=0` (e.g. no online pujari) — not only bookings
    that previously had assignment rows. Retries every sweep cycle until offers land or
    dispatch_deadline exhausts the booking.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT b.id
            FROM bookings b
            JOIN status_types st ON st.id = b.status_id
            JOIN booking_dispatch_state bds ON bds.booking_id = b.id
            WHERE st.domain = 'booking' AND st.code = 'requested'
              AND b.pujari_id IS NULL
              AND b.cancelled_at IS NULL
              AND b.paid_at IS NOT NULL
              AND bds.last_dispatched IS NOT NULL
              AND bds.exhausted_at IS NULL
              AND (bds.dispatch_starts_at IS NULL OR bds.dispatch_starts_at <= now())
              AND (bds.dispatch_deadline IS NULL OR bds.dispatch_deadline > now())
              AND NOT EXISTS (
                  SELECT 1 FROM booking_assignments ba
                  JOIN status_types s2 ON s2.id = ba.status_id
                  WHERE ba.booking_id = b.id
                    AND s2.domain = 'assignment' AND s2.code = 'offered'
                    AND ba.responded_at IS NULL
                    AND ba.expires_at > now()
              )
            """
        )
        return [str(r[0]) for r in cur.fetchall()]


# --------------------------------------------------------------------------- #
# Step 5 — lazily sync pujaris.is_online from Redis presence keys (analytics)
# --------------------------------------------------------------------------- #
def sync_pujari_presence(conn: psycopg.Connection, redis_client) -> int:
    if redis_client is None:
        return 0
    with conn.cursor() as cur:
        cur.execute("SELECT id, is_online FROM pujaris")
        rows = cur.fetchall()
    changed = 0
    with conn.cursor() as cur:
        for pujari_id, is_online in rows:
            present = redis_client.exists(f"presence:{pujari_id}") == 1
            if present != is_online:
                cur.execute(
                    "UPDATE pujaris SET is_online = %s, updated_at = now() WHERE id = %s",
                    (present, pujari_id),
                )
                changed += 1
    conn.commit()
    if changed:
        log.info("presence_synced", changed=changed)
    return changed


def run_sweep(conn: psycopg.Connection, redis_client=None) -> dict:
    from app.monitoring.scanner import run_stuck_state_monitor
    from app.workers.reconfirmation import run_reconfirmation

    reconfirm_summary = run_reconfirmation(conn)
    monitor_summary = run_stuck_state_monitor(conn)
    return {
        "holds_released": release_expired_slot_holds(conn),
        "bookings_abandoned": abandon_stale_payment_pending(conn),
        "offers_expired_on": expire_stale_assignments(conn),
        "dispatch_deadline_exhausted": exhaust_past_dispatch_deadline(conn),
        "needs_initial_broadcast": bookings_needing_initial_broadcast(conn),
        "needs_rebroadcast": bookings_needing_rebroadcast(conn),
        "presence_synced": sync_pujari_presence(conn, redis_client),
        **monitor_summary,
        **reconfirm_summary,
    }


# --------------------------------------------------------------------------- #
# Celery task — thin wrapper: Redis sweep-lock + fan-out rebroadcasts
# --------------------------------------------------------------------------- #
try:
    from app.workers.celery_app import celery_app

    @celery_app.task(name="app.workers.sweep.sweep_task")
    def sweep_task():
        import redis as redis_lib

        from app.core.config import get_settings

        settings = get_settings()
        r = redis_lib.from_url(str(settings.REDIS_URL))

        if not r.set("sweep_lock", "1", nx=True, ex=25):
            log.info("sweep_skipped_locked")
            return {"skipped": "locked"}

        conn = get_connection()
        try:
            summary = run_sweep(conn, redis_client=r)
            for booking_id in summary["needs_initial_broadcast"]:
                celery_app.send_task(
                    "app.workers.dispatch.broadcast_booking", args=[str(booking_id)]
                )
            for booking_id in summary["needs_rebroadcast"]:
                celery_app.send_task(
                    "app.workers.dispatch.rebroadcast_booking", args=[str(booking_id)]
                )
            return summary
        finally:
            conn.close()
            r.delete("sweep_lock")

except ImportError:
    pass
