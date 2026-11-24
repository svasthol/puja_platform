"""
Advance→escalated urgency flip — separate beat task (§21.6.E).

Uses `urgency_escalation_lead_hours`, B5 flip clamp, B11 quiet delivery,
morning wake, and expand_booking after commit.
"""
from __future__ import annotations

import datetime as dt
import os
import zoneinfo

import structlog

from app.core.config import get_settings
from app.services.booking_gate import compute_lead_hours
from app.services.dispatch_launch import (
    load_dispatch_settings,
    load_quiet_hours,
    slot_datetime,
)
from app.services.escalated_delivery import (
    effective_flip_at,
    escalated_delivery_policy,
)
from app.workers.sweep import get_connection

log = structlog.get_logger("urgency_flip")

URGENCY_LOCK_KEY = "urgency_lock"
URGENCY_LOCK_TTL_SECONDS = 110
_TZ = zoneinfo.ZoneInfo(get_settings().PLATFORM_TIMEZONE)
_FLIP_BATCH_CAP = int(os.environ.get("URGENCY_FLIP_MAX_BOOKINGS_PER_TICK", "50"))


def _now_local(conn) -> dt.datetime:
    with conn.cursor() as cur:
        cur.execute("SELECT now()")
        now_db = cur.fetchone()[0]
    if now_db.tzinfo is None:
        return now_db.replace(tzinfo=dt.UTC).astimezone(_TZ)
    return now_db.astimezone(_TZ)


def _shorten_holders(cur, booking_id: str, ttl_seconds: int) -> None:
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


def escalate_urgency_on_threshold(conn) -> list[str]:
    """Flip advance bookings inside escalation lead (effective flip time passed)."""
    with conn.cursor() as cur:
        settings = load_dispatch_settings(cur)
        escalation_lead = settings.urgency_escalation_lead_hours
        ttl_seconds = settings.escalated_offer_ttl_seconds
        quiet_start, quiet_end = load_quiet_hours(cur)
        now_local = _now_local(conn)

        cur.execute(
            """
            SELECT b.id, b.scheduled_date, b.scheduled_time, bds.dispatch_deadline,
                   bds.urgency_escalated_at
            FROM bookings b
            JOIN booking_dispatch_state bds ON bds.booking_id = b.id
            JOIN status_types st ON st.id = b.status_id
            WHERE b.booking_class = 'advance'
              AND st.domain = 'booking'
              AND st.code = 'requested'
              AND b.pujari_id IS NULL
              AND b.cancelled_at IS NULL
              AND bds.urgency_escalated_at IS NULL
              AND (b.scheduled_date + b.scheduled_time) > now()
            FOR UPDATE OF bds SKIP LOCKED
            """
        )
        rows = cur.fetchall()
        booking_ids: list[str] = []
        for booking_id, sched_d, sched_t, deadline, _ in rows[: _FLIP_BATCH_CAP]:
            lead = compute_lead_hours(sched_d, sched_t, now=now_local.astimezone(dt.UTC))
            if lead > escalation_lead:
                continue
            slot_local = slot_datetime(sched_d, sched_t)
            flip_at = effective_flip_at(slot_local, escalation_lead, quiet_start, quiet_end)
            if now_local < flip_at:
                continue
            policy = escalated_delivery_policy(
                now_local,
                quiet_start=quiet_start,
                quiet_end=quiet_end,
                dispatch_deadline=deadline,
            )
            cur.execute(
                """
                UPDATE booking_dispatch_state
                SET urgency_escalated_at = now()
                WHERE booking_id = %s AND urgency_escalated_at IS NULL
                RETURNING booking_id
                """,
                (str(booking_id),),
            )
            if cur.rowcount == 0:
                continue
            bid = str(booking_id)
            booking_ids.append(bid)
            if policy.allow_holder_shorten:
                _shorten_holders(cur, bid, ttl_seconds)
            else:
                cur.execute(
                    """
                    UPDATE booking_dispatch_state
                    SET escalated_holders_shortened_at = NULL
                    WHERE booking_id = %s
                    """,
                    (bid,),
                )

    conn.commit()
    if booking_ids:
        log.info("urgency_flipped", count=len(booking_ids), booking_ids=booking_ids)
    return booking_ids


def morning_wake_escalated_holders(conn) -> list[str]:
    """After quiet: shorten holders + mark wake for overnight-escalated bookings (B11)."""
    with conn.cursor() as cur:
        settings = load_dispatch_settings(cur)
        quiet_start, quiet_end = load_quiet_hours(cur)
        now_local = _now_local(conn)
        if escalated_delivery_policy(
            now_local, quiet_start=quiet_start, quiet_end=quiet_end, dispatch_deadline=None
        ).in_quiet:
            return []

        ttl_seconds = settings.escalated_offer_ttl_seconds
        cur.execute(
            """
            SELECT b.id, bds.dispatch_deadline
            FROM bookings b
            JOIN booking_dispatch_state bds ON bds.booking_id = b.id
            JOIN status_types st ON st.id = b.status_id
            WHERE b.booking_class = 'advance'
              AND st.domain = 'booking'
              AND st.code = 'requested'
              AND b.pujari_id IS NULL
              AND b.cancelled_at IS NULL
              AND bds.urgency_escalated_at IS NOT NULL
              AND bds.escalated_holders_shortened_at IS NULL
              AND bds.dispatch_deadline > now()
            FOR UPDATE OF bds SKIP LOCKED
            LIMIT %s
            """,
            (_FLIP_BATCH_CAP,),
        )
        woke: list[str] = []
        for booking_id, _deadline in cur.fetchall():
            bid = str(booking_id)
            _shorten_holders(cur, bid, ttl_seconds)
            cur.execute(
                """
                UPDATE booking_dispatch_state
                SET escalated_holders_shortened_at = now()
                WHERE booking_id = %s
                """,
                (bid,),
            )
            woke.append(bid)
    conn.commit()
    if woke:
        log.info("urgency_morning_wake", count=len(woke), booking_ids=woke)
    return woke


try:
    from app.workers.celery_app import celery_app

    @celery_app.task(name="app.workers.urgency_flip.escalate_urgency_on_threshold_task")
    def escalate_urgency_on_threshold_task() -> dict:
        import redis as redis_lib

        from app.workers.redis_sync import namespaced_key

        r = redis_lib.from_url(str(get_settings().REDIS_URL))
        lock = namespaced_key(URGENCY_LOCK_KEY)
        if not r.set(lock, "1", nx=True, ex=URGENCY_LOCK_TTL_SECONDS):
            log.info("escalate_urgency_skipped_locked")
            return {"skipped": "locked"}

        conn = get_connection()
        try:
            flipped = escalate_urgency_on_threshold(conn)
            woke = morning_wake_escalated_holders(conn)
            with conn.cursor() as cur:
                settings = load_dispatch_settings(cur)
        finally:
            conn.close()
            r.delete(lock)

        for booking_id in flipped:
            celery_app.send_task(
                "app.workers.notifications.notify_offer_escalated",
                args=[booking_id],
            )
            if settings.rebroadcast_on_urgency_flip:
                celery_app.send_task(
                    "app.workers.dispatch.expand_booking",
                    args=[booking_id, "urgency_flip"],
                )
        for booking_id in woke:
            celery_app.send_task(
                "app.workers.notifications.notify_offer_escalated",
                args=[booking_id],
            )
            if settings.rebroadcast_on_urgency_flip:
                celery_app.send_task(
                    "app.workers.dispatch.expand_booking",
                    args=[booking_id, "morning_wake"],
                )

        return {
            "flipped": len(flipped),
            "booking_ids": flipped,
            "morning_wake": len(woke),
        }

except ImportError:
    pass