"""
Dispatch worker — broadcast_booking / rebroadcast_booking / direct_dispatch
(spec DISPATCH_FLOW — launch: citywide + deferred windows + status-aware re-offer).

Idempotency, layered:
  1. Redis dispatch lock: SET dispatch_lock:{booking_id} 1 NX EX 60. Not acquired
     -> another worker owns this booking; exit.
  2. fresh=True reset runs UNDER the lock, before round CAS.
  3. DB compare-and-set on booking_dispatch_state.round. Zero rows -> this round
     already ran (duplicate task delivery); exit.
  4. ux_booking_assignments_one_live makes duplicate live offers impossible.

Launch exhaustion is time-based (dispatch_deadline), not round-count based.
"""
from __future__ import annotations

import structlog

from app.services.dispatch_launch import (
    ensure_dispatch_windows,
    filter_candidates_inbox_cap,
    launch_eligibility_sql,
    load_dispatch_settings,
    offer_expires_interval,
)
from app.workers.celery_app import celery_app
from app.workers.redis_sync import get_sync_redis, namespaced_key, new_lock_token, release_lock
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
    from app.workers.redis_sync import get_sync_redis

    return get_sync_redis()


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


def exhaust_booking_no_pujari(cur, conn, booking_id: str) -> dict:
    """Past dispatch_deadline or manual exhaustion -> failed_no_pujari + refund."""
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
    from app.monitoring.emit import AlertCandidate, record_ops_alert_sync
    from app.monitoring.registry import AlertType

    record_ops_alert_sync(
        conn,
        AlertCandidate(
            alert_type=AlertType.DISPATCH_EXHAUSTED,
            subject_id=booking_id,
            payload={"booking_id": booking_id, "status": "failed_no_pujari"},
        ),
    )
    celery_app.send_task("app.workers.notifications.notify_no_pujari", args=[booking_id])
    return {"status": "failed_no_pujari"}


def _dispatch_round(booking_id: str, *, fresh: bool = False) -> dict:
    r = _redis()
    lock_key = namespaced_key(f"dispatch_lock:{booking_id}")
    lock_token = new_lock_token()
    if not r.set(lock_key, lock_token, nx=True, ex=60):
        log.info("dispatch_skipped_locked", booking_id=booking_id)
        return {"skipped": "locked"}

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            settings = load_dispatch_settings(cur)
            _ensure_dispatch_state(cur, booking_id)
            _reset_dispatch_state_if_fresh(cur, booking_id, fresh=fresh)
            starts_at, deadline, _, _, booking_class = ensure_dispatch_windows(
                cur, booking_id, settings
            )
            conn.commit()

            cur.execute("SELECT now()")
            now_db = cur.fetchone()[0]
            if starts_at > now_db:
                log.info("dispatch_deferred", booking_id=booking_id, starts_at=str(starts_at))
                return {"skipped": "deferred", "dispatch_starts_at": str(starts_at)}
            if deadline <= now_db:
                return exhaust_booking_no_pujari(cur, conn, booking_id)

            cur.execute(
                "SELECT round, max_rounds FROM booking_dispatch_state WHERE booking_id=%s",
                (booking_id,),
            )
            row = cur.fetchone()
            if row is None:
                return {"error": "no_dispatch_state"}
            expected, max_rounds = row[0], row[1]
            if expected >= max_rounds:
                log.info(
                    "dispatch_round_cap_reached",
                    booking_id=booking_id,
                    round=expected,
                    max_rounds=max_rounds,
                )
                return exhaust_booking_no_pujari(cur, conn, booking_id)

            next_round = expected + 1
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
            eligibility = launch_eligibility_sql(settings)
            cur.execute(eligibility, (booking_id,))
            candidates = [c[0] for c in cur.fetchall()]

            inbox_capped = 0
            if booking_class == "advance":
                candidates, inbox_capped = filter_candidates_inbox_cap(
                    cur,
                    candidates,
                    settings.max_live_advance_offers_per_pujari,
                )

            live = []
            if candidates:
                keys = [f"presence:{c}" for c in candidates]
                vals = r.mget(keys)
                live = [c for c, v in zip(candidates, vals) if v is not None]

            inserted = 0
            offer_ttl = offer_expires_interval(booking_class, settings)
            for pujari_id in live:
                try:
                    cur.execute("SAVEPOINT dispatch_offer_insert")
                    cur.execute(
                        "INSERT INTO booking_assignments "
                        "(id, booking_id, pujari_id, status_id, offered_at, expires_at) "
                        f"VALUES (gen_random_uuid(), %s, %s, %s, now(), now() + interval '{offer_ttl}')",
                        (booking_id, pujari_id, offered_id),
                    )
                    cur.execute("RELEASE SAVEPOINT dispatch_offer_insert")
                    inserted += 1
                except Exception:
                    cur.execute("ROLLBACK TO SAVEPOINT dispatch_offer_insert")
                    continue
            conn.commit()
            log.info(
                "dispatch_round_done",
                booking_id=booking_id,
                round=next_round,
                offers=inserted,
                candidates=len(candidates),
                live=len(live),
                fresh=fresh,
                inbox_capped=inbox_capped,
            )

            if inserted:
                celery_app.send_task(
                    "app.workers.notifications.notify_offers", args=[booking_id]
                )
            return {"round": next_round, "offers": inserted}
    finally:
        conn.close()
        release_lock(r, lock_key, lock_token)


def _direct_dispatch(booking_id: str) -> dict:
    """Single offer to intended_pujari_id, 10 min expiry (direct dispatch mode)."""
    r = _redis()
    lock_key = namespaced_key(f"dispatch_lock:{booking_id}")
    lock_token = new_lock_token()
    if not r.set(lock_key, lock_token, nx=True, ex=60):
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
        release_lock(r, lock_key, lock_token)
def broadcast_booking(booking_id: str) -> dict:
    return _dispatch_round(booking_id, fresh=False)


@celery_app.task(name="app.workers.dispatch.rebroadcast_booking")
def rebroadcast_booking(booking_id: str, fresh: bool = False) -> dict:
    return _dispatch_round(booking_id, fresh=fresh)


@celery_app.task(name="app.workers.dispatch.direct_dispatch")
def direct_dispatch(booking_id: str) -> dict:
    return _direct_dispatch(booking_id)
