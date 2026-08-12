"""
Reconfirmation worker — advance booking attendance ping (§21.7, P-LAUNCH-RECONFIRM).

Runs inside the sweep tick (every 30s):
  1. Ping assigned pujari 24h before slot (FCM/SMS) when lead at confirm was ≥24h.
  2. Escalate to RM/admin if no response within 4h (launch: no in-app confirm yet).

Idempotent via booking_reconfirmations timestamps.
"""
from __future__ import annotations

import datetime as dt

import psycopg
import structlog

from app.services.reconfirmation import (
    _TZ,
    bookings_needing_escalation_sql,
    bookings_needing_ping_sql,
    effective_escalation_at,
    effective_ping_at,
    load_reconfirm_settings,
)
from app.workers.notifications import (
    _notify_reconfirm_escalation_impl,
    _notify_reconfirm_ping_impl,
)

log = structlog.get_logger("reconfirmation")


def _record_ping_sent(cur, booking_id: str) -> None:
    cur.execute(
        """
        INSERT INTO booking_reconfirmations (booking_id, ping_sent_at)
        VALUES (%s, now())
        ON CONFLICT (booking_id) DO UPDATE
        SET ping_sent_at = COALESCE(booking_reconfirmations.ping_sent_at, EXCLUDED.ping_sent_at)
        """,
        (booking_id,),
    )


def _record_escalation_sent(cur, booking_id: str) -> None:
    cur.execute(
        """
        UPDATE booking_reconfirmations
        SET rm_alert_sent_at = now()
        WHERE booking_id = %s AND rm_alert_sent_at IS NULL
        """,
        (booking_id,),
    )


def process_reconfirm_pings(conn: psycopg.Connection) -> list[str]:
    """Send 24h-before-slot attendance pings; returns booking ids pinged."""
    now_local = dt.datetime.now(_TZ)
    with conn.cursor() as cur:
        settings = load_reconfirm_settings(cur)
        cur.execute(bookings_needing_ping_sql(settings))
        candidates = [(str(r[0]), r[1]) for r in cur.fetchall()]
    conn.commit()

    booking_ids = [
        bid
        for bid, slot_at in candidates
        if now_local >= effective_ping_at(slot_at.astimezone(_TZ), settings)
    ]

    pinged: list[str] = []
    for booking_id in booking_ids:
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT b.id
                    FROM bookings b
                    JOIN status_types st ON st.id = b.status_id
                    WHERE b.id = %s
                      AND st.domain = 'booking' AND st.code = 'confirmed'
                      AND b.pujari_id IS NOT NULL
                      AND b.cancelled_at IS NULL
                      AND NOT EXISTS (
                        SELECT 1 FROM booking_reconfirmations br
                        WHERE br.booking_id = b.id AND br.ping_sent_at IS NOT NULL
                      )
                    FOR UPDATE OF b
                    """,
                    (booking_id,),
                )
                if cur.fetchone() is None:
                    conn.rollback()
                    continue
            notify_result = _notify_reconfirm_ping_impl(booking_id)
            if notify_result.get("skipped"):
                conn.rollback()
                continue
            with conn.cursor() as cur:
                _record_ping_sent(cur, booking_id)
                conn.commit()
            pinged.append(booking_id)
        except Exception:
            conn.rollback()
            log.exception("reconfirm_ping_failed", booking_id=booking_id)

    if pinged:
        log.info("reconfirm_pings_sent", count=len(pinged))
    return pinged


def process_reconfirm_escalations(conn: psycopg.Connection) -> list[str]:
    """Alert RM/admin when pujari did not confirm within escalation window."""
    now_local = dt.datetime.now(_TZ)
    with conn.cursor() as cur:
        settings = load_reconfirm_settings(cur)
        cur.execute(bookings_needing_escalation_sql(settings))
        candidates = [(str(r[0]), r[1]) for r in cur.fetchall()]
    conn.commit()

    booking_ids = [
        bid
        for bid, ping_sent_at in candidates
        if now_local
        >= effective_escalation_at(ping_sent_at.astimezone(_TZ), settings)
    ]

    escalated: list[str] = []
    for booking_id in booking_ids:
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT br.booking_id
                    FROM booking_reconfirmations br
                    JOIN bookings b ON b.id = br.booking_id
                    JOIN status_types st ON st.id = b.status_id
                    WHERE br.booking_id = %s
                      AND st.domain = 'booking' AND st.code = 'confirmed'
                      AND br.ping_sent_at IS NOT NULL
                      AND br.pujari_confirmed_at IS NULL
                      AND br.rm_alert_sent_at IS NULL
                    FOR UPDATE OF br
                    """,
                    (booking_id,),
                )
                if cur.fetchone() is None:
                    conn.rollback()
                    continue
            notify_result = _notify_reconfirm_escalation_impl(booking_id)
            if notify_result.get("skipped"):
                conn.rollback()
                continue
            with conn.cursor() as cur:
                _record_escalation_sent(cur, booking_id)
                conn.commit()
            escalated.append(booking_id)
        except Exception:
            conn.rollback()
            log.exception("reconfirm_escalation_failed", booking_id=booking_id)

    if escalated:
        log.info("reconfirm_escalations_sent", count=len(escalated))
    return escalated


def run_reconfirmation(conn: psycopg.Connection) -> dict:
    return {
        "reconfirm_pings": process_reconfirm_pings(conn),
        "reconfirm_escalations": process_reconfirm_escalations(conn),
    }
