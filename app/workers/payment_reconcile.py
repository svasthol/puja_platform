"""
Payment reconciliation — recover captured Razorpay payments when webhooks are lost (REL-005).

Three phases: claim rows (short txn), fetch order payments outside DB, apply capture per hit.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import uuid

import structlog

from app.workers.celery_app import celery_app
from app.workers.sweep import get_connection

log = structlog.get_logger("payment_reconcile")

_CLAIM_BATCH = 50
_TIERS_MINUTES = (20, 120, 1440, 4320)  # 20m, 2h, 24h, 72h — then stop


def _claim_due_bookings(conn) -> list[tuple[uuid.UUID, str, int]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE bookings b
            SET reconcile_next_at = now() + interval '10 minutes'
            FROM (
                SELECT id
                FROM bookings
                WHERE reconcile_next_at IS NOT NULL
                  AND reconcile_next_at <= now()
                  AND razorpay_order_id IS NOT NULL
                ORDER BY reconcile_next_at
                FOR UPDATE SKIP LOCKED
                LIMIT %s
            ) pick
            WHERE b.id = pick.id
            RETURNING b.id, b.razorpay_order_id, b.reconcile_attempts
            """,
            (_CLAIM_BATCH,),
        )
        rows = cur.fetchall()
    conn.commit()
    return [(uuid.UUID(str(r[0])), str(r[1]), int(r[2] or 0)) for r in rows]


def _next_reconcile_at(attempts: int, *, now: dt.datetime) -> dt.datetime | None:
    if attempts >= len(_TIERS_MINUTES):
        return None
    return now + dt.timedelta(minutes=_TIERS_MINUTES[attempts])


def _bump_reconcile_schedule(conn, *, booking_id: uuid.UUID, attempts: int) -> None:
    now = dt.datetime.now(dt.UTC)
    nxt = _next_reconcile_at(attempts + 1, now=now)
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE bookings
            SET reconcile_attempts = %s,
                reconcile_next_at = %s,
                updated_at = now()
            WHERE id = %s
            """,
            (attempts + 1, nxt, booking_id),
        )
    conn.commit()


async def _apply_capture_hit(
    booking_id: uuid.UUID, *, pay_id: str, amount_paise: int
) -> dict:
    from app.db.engine import AsyncSessionLocal
    from app.services import payment_capture

    async with AsyncSessionLocal() as db:
        async with db.begin():
            return await payment_capture.handle_payment_captured(
                db,
                booking_id=booking_id,
                gateway_txn_id=pay_id,
                idempotency_key=pay_id,
                amount_paise=amount_paise,
            )


def _enqueue_dispatch(result: dict) -> None:
    bid = result.get("enqueue_broadcast") or result.get("enqueue_direct")
    if not bid:
        return
    task = (
        "app.workers.dispatch.direct_dispatch"
        if result.get("enqueue_direct")
        else "app.workers.dispatch.broadcast_booking"
    )
    celery_app.send_task(task, args=[bid])


@celery_app.task(name="app.workers.payment_reconcile.reconcile_payments")
def reconcile_payments() -> dict:
    from app.services.razorpay_client import RazorpayError, fetch_order_payments_sync

    conn = get_connection()
    claimed = _claim_due_bookings(conn)
    recovered = 0
    checked = 0
    for booking_id, order_id, attempts in claimed:
        checked += 1
        try:
            payments = fetch_order_payments_sync(order_id)
        except RazorpayError as exc:
            log.warning(
                "reconcile_fetch_failed",
                booking_id=str(booking_id),
                order_id=order_id,
                error=str(exc),
            )
            _bump_reconcile_schedule(conn, booking_id=booking_id, attempts=attempts)
            continue

        captured = [
            p
            for p in payments
            if str(p.get("status")) == "captured" and str(p.get("id", "")).startswith("pay_")
        ]
        if not captured:
            _bump_reconcile_schedule(conn, booking_id=booking_id, attempts=attempts)
            continue

        for pay in captured:
            pay_id = str(pay["id"])
            amount_paise = int(pay.get("amount", 0))
            result = asyncio.run(
                _apply_capture_hit(booking_id, pay_id=pay_id, amount_paise=amount_paise)
            )
            if result.get("status") == "confirmed":
                recovered += 1
                log.info(
                    "reconcile_payment_recovered",
                    booking_id=str(booking_id),
                    pay_id=pay_id,
                )
                _enqueue_dispatch(result)
                break
            if result.get("status") in ("already_processed", "auto_refund_initiated"):
                break
        else:
            _bump_reconcile_schedule(conn, booking_id=booking_id, attempts=attempts)

    return {"claimed": len(claimed), "checked": checked, "recovered": recovered}