"""
Dispatch worker — broadcast_booking / rebroadcast_booking / direct_dispatch
(spec DISPATCH_FLOW "Dispatch rounds" + direct mode).

Idempotency, layered:
  1. Redis dispatch lock: SET dispatch_lock:{booking_id} 1 NX EX 60. Not acquired
     -> another worker owns this booking; exit.
  2. fresh=True reset runs UNDER the lock, before round CAS.
  3. DB compare-and-set on booking_dispatch_state.round. Zero rows -> this round
     already ran (duplicate task delivery); exit.
  4. ux_booking_assignments_one_live makes duplicate live offers impossible.
"""
from __future__ import annotations

import structlog

from app.workers.celery_app import celery_app
from app.workers.sweep import get_connection

log = structlog.get_logger("dispatch")

RADIUS_SCHEDULE = {1: 3.0, 2: 6.0, 3: 10.0, 4: 15.0}


def _status_id(cur, domain: str, code: str) -> int:
    cur.execute(
        "SELECT id FROM status_types WHERE domain=%s AND code=%s", (domain, code)
    )
    row = cur.fetchone()
    if row is None:
        raise RuntimeError(f"Seed data missing: status_types({domain},{code})")
    return row[0]


def _redis():
    import redis as redis_lib

    from app.core.config import get_settings

    return redis_lib.from_url(str(get_settings().REDIS_URL))


def _ensure_dispatch_state(cur, booking_id: str) -> None:
    cur.execute(
        "INSERT INTO booking_dispatch_state (booking_id) VALUES (%s) "
        "ON CONFLICT (booking_id) DO NOTHING",
        (booking_id,),
    )


def _reset_dispatch_state_if_fresh(cur, booking_id: str, *, fresh: bool) -> None:
    if not fresh:
        return
    cur.execute(
        "UPDATE booking_dispatch_state "
        "SET round=0, radius_km=3.0, exhausted_at=NULL, last_dispatched=NULL "
        "WHERE booking_id=%s",
        (booking_id,),
    )


def _dispatch_round(booking_id: str, *, fresh: bool = False) -> dict:
    r = _redis()
    lock_key = f"dispatch_lock:{booking_id}"
    if not r.set(lock_key, "1", nx=True, ex=60):
        log.info("dispatch_skipped_locked", booking_id=booking_id)
        return {"skipped": "locked"}

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            _ensure_dispatch_state(cur, booking_id)
            _reset_dispatch_state_if_fresh(cur, booking_id, fresh=fresh)
            conn.commit()

            cur.execute(
                "SELECT round, max_rounds FROM booking_dispatch_state WHERE booking_id=%s",
                (booking_id,),
            )
            row = cur.fetchone()
            if row is None:
                return {"error": "no_dispatch_state"}
            current_round, max_rounds = row
            expected = current_round
            next_round = current_round + 1

            if next_round > max_rounds:
                return _exhaust(cur, conn, booking_id)

            radius = RADIUS_SCHEDULE.get(next_round, 15.0)

            cur.execute(
                "UPDATE booking_dispatch_state SET round=%s, radius_km=%s, last_dispatched=now() "
                "WHERE booking_id=%s AND round=%s",
                (next_round, radius, booking_id, expected),
            )
            if cur.rowcount == 0:
                conn.rollback()
                log.info("dispatch_round_already_ran", booking_id=booking_id, round=next_round)
                return {"skipped": "round_cas"}

            offered_id = _status_id(cur, "assignment", "offered")

            cur.execute(
                """
                SELECT pj.id
                FROM bookings b
                JOIN addresses a ON a.id = b.address_id
                JOIN pujaris pj ON pj.verification_status = 'verified'
                JOIN pujari_pricing pp ON pp.pujari_id = pj.id AND pp.puja_id = b.puja_id
                JOIN pujari_live_location loc ON loc.pujari_id = pj.id
                JOIN pujari_service_areas psa ON psa.pujari_id = pj.id
                JOIN service_areas sa ON sa.id = psa.service_area_id AND sa.is_active
                WHERE b.id = %s
                  AND ST_DWithin(loc.geom, a.geom, %s)
                  AND NOT EXISTS (
                    SELECT 1 FROM pujari_unavailability pu
                    WHERE pu.pujari_id = pj.id AND pu.unavailable_date = b.scheduled_date)
                  AND NOT EXISTS (
                    SELECT 1 FROM bookings b2
                    WHERE b2.pujari_id = pj.id AND b2.cancelled_at IS NULL
                      AND tsrange(b2.scheduled_date + b2.scheduled_time,
                                  b2.scheduled_date + b2.scheduled_time
                                  + make_interval(mins => b2.duration_minutes))
                          && tsrange(b.scheduled_date + b.scheduled_time,
                                     b.scheduled_date + b.scheduled_time
                                     + make_interval(mins => b.duration_minutes)))
                  AND NOT EXISTS (
                    SELECT 1 FROM bookings b3
                    WHERE b3.intended_pujari_id = pj.id AND b3.paid_at IS NOT NULL
                      AND b3.cancelled_at IS NULL
                      AND tsrange(b3.scheduled_date + b3.scheduled_time,
                                  b3.scheduled_date + b3.scheduled_time
                                  + make_interval(mins => b3.duration_minutes))
                          && tsrange(b.scheduled_date + b.scheduled_time,
                                     b.scheduled_date + b.scheduled_time
                                     + make_interval(mins => b.duration_minutes)))
                  AND NOT EXISTS (
                    SELECT 1 FROM booking_assignments ba
                    WHERE ba.booking_id = b.id AND ba.pujari_id = pj.id)
                """,
                (booking_id, radius * 1000),
            )
            candidates = [c[0] for c in cur.fetchall()]

            live = []
            if candidates:
                keys = [f"presence:{c}" for c in candidates]
                vals = r.mget(keys)
                live = [c for c, v in zip(candidates, vals) if v is not None]

            inserted = 0
            for pujari_id in live:
                try:
                    cur.execute(
                        "INSERT INTO booking_assignments "
                        "(id, booking_id, pujari_id, status_id, offered_at, expires_at) "
                        "VALUES (gen_random_uuid(), %s, %s, %s, now(), now() + interval '2 minutes')",
                        (booking_id, pujari_id, offered_id),
                    )
                    inserted += 1
                except Exception:
                    conn.rollback()
                    continue
            conn.commit()
            log.info(
                "dispatch_round_done",
                booking_id=booking_id,
                round=next_round,
                radius_km=radius,
                offers=inserted,
                fresh=fresh,
            )

            if inserted:
                celery_app.send_task(
                    "app.workers.notifications.notify_offers", args=[booking_id]
                )
            return {"round": next_round, "offers": inserted}
    finally:
        conn.close()
        r.delete(lock_key)


def _direct_dispatch(booking_id: str) -> dict:
    """Single offer to intended_pujari_id, 10 min expiry (direct dispatch mode)."""
    r = _redis()
    lock_key = f"dispatch_lock:{booking_id}"
    if not r.set(lock_key, "1", nx=True, ex=60):
        log.info("direct_dispatch_skipped_locked", booking_id=booking_id)
        return {"skipped": "locked"}

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT b.intended_pujari_id, b.puja_id, pj.verification_status
                FROM bookings b
                LEFT JOIN pujaris pj ON pj.id = b.intended_pujari_id
                WHERE b.id = %s AND b.cancelled_at IS NULL
                """,
                (booking_id,),
            )
            row = cur.fetchone()
            if row is None or row[0] is None:
                log.info("direct_dispatch_no_intended", booking_id=booking_id)
                return {"skipped": "no_intended_pujari"}
            intended_id, puja_id, verification = row
            if verification != "verified":
                return {"skipped": "pujari_not_verified"}

            cur.execute(
                "SELECT 1 FROM pujari_pricing WHERE pujari_id=%s AND puja_id=%s",
                (intended_id, puja_id),
            )
            if cur.fetchone() is None:
                return {"skipped": "no_pricing_row"}

            offered_id = _status_id(cur, "assignment", "offered")
            try:
                cur.execute(
                    "INSERT INTO booking_assignments "
                    "(id, booking_id, pujari_id, status_id, offered_at, expires_at) "
                    "VALUES (gen_random_uuid(), %s, %s, %s, now(), now() + interval '10 minutes')",
                    (booking_id, intended_id, offered_id),
                )
            except Exception:
                conn.rollback()
                log.info("direct_dispatch_offer_exists", booking_id=booking_id)
                return {"skipped": "offer_already_live"}
            conn.commit()
            log.info("direct_dispatch_done", booking_id=booking_id, pujari_id=str(intended_id))
            celery_app.send_task(
                "app.workers.notifications.notify_offers", args=[booking_id]
            )
            return {"status": "direct_offer", "pujari_id": str(intended_id)}
    finally:
        conn.close()
        r.delete(lock_key)


def _exhaust(cur, conn, booking_id: str) -> dict:
    """Round exhausted with zero accepts -> failed_no_pujari + cancelled_at + refund."""
    failed_id = _status_id(cur, "booking", "failed_no_pujari")
    cur.execute(
        "UPDATE bookings SET status_id=%s, cancelled_at=now(), updated_at=now() "
        "WHERE id=%s AND pujari_id IS NULL AND cancelled_at IS NULL",
        (failed_id, booking_id),
    )
    if cur.rowcount == 0:
        conn.rollback()
        return {"skipped": "already_resolved"}
    cur.execute(
        "UPDATE booking_dispatch_state SET exhausted_at=now() WHERE booking_id=%s",
        (booking_id,),
    )
    cur.execute(
        "INSERT INTO booking_status_history (id,booking_id,status_id,changed_by,changed_at) "
        "VALUES (gen_random_uuid(), %s, %s, NULL, now())",
        (booking_id, failed_id),
    )
    cur.execute(
        """
        INSERT INTO refunds (id, payment_id, booking_id, amount, reason, status,
                             attempt_count, next_attempt_at, created_at)
        SELECT gen_random_uuid(), p.id, b.id, b.amount_due_online, 'no_pujari',
               'pending', 0, now(), now()
        FROM bookings b
        JOIN payments p ON p.booking_id = b.id AND p.status = 'success'
        WHERE b.id = %s AND b.amount_due_online > 0
        ON CONFLICT DO NOTHING
        """,
        (booking_id,),
    )
    conn.commit()
    log.info("dispatch_exhausted", booking_id=booking_id)
    celery_app.send_task("app.workers.notifications.notify_no_pujari", args=[booking_id])
    return {"status": "failed_no_pujari"}


@celery_app.task(name="app.workers.dispatch.broadcast_booking")
def broadcast_booking(booking_id: str) -> dict:
    return _dispatch_round(booking_id, fresh=False)


@celery_app.task(name="app.workers.dispatch.rebroadcast_booking")
def rebroadcast_booking(booking_id: str, fresh: bool = False) -> dict:
    return _dispatch_round(booking_id, fresh=fresh)


@celery_app.task(name="app.workers.dispatch.direct_dispatch")
def direct_dispatch(booking_id: str) -> dict:
    return _direct_dispatch(booking_id)
