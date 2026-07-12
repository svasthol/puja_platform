"""
Refund worker (spec DISPATCH_FLOW "Refund execution"). Sync psycopg3.

Polls refunds pending/processing past next_attempt_at (ix_refunds_worker),
FOR UPDATE SKIP LOCKED:
  - Take a 'pending' row -> flip 'processing' AND next_attempt_at = now()+30min
    (doubles as crash deadline). Commit, THEN call Razorpay (outside row lock).
  - Idempotency key SENT to Razorpay = refunds.id (stable across retries).
    Store the RETURNED id in gateway_refund_id.
  - Success -> 'succeeded'. Failure -> back to 'pending' with exp backoff.
  - A 'processing' row past next_attempt_at is a crashed worker -> requeue.
  - After 8 attempts -> 'failed_permanent' + alert.
"""
from __future__ import annotations

import structlog

from app.workers.celery_app import celery_app
from app.workers.sweep import get_connection

log = structlog.get_logger("refund")

BACKOFF_MINUTES = [1, 5, 30, 120, 720, 1440, 2880, 2880]
MAX_ATTEMPTS = 8


@celery_app.task(name="app.workers.refund.process_refunds")
def process_refunds(batch: int = 20) -> dict:
    from app.services.razorpay_client import create_refund_sync

    conn = get_connection()
    processed = 0
    try:
        with conn.cursor() as cur:
            # requeue crashed 'processing' rows, then take due rows
            cur.execute(
                """
                WITH due AS (
                    SELECT id FROM refunds
                    WHERE status IN ('pending','processing')
                      AND next_attempt_at <= now()
                    ORDER BY next_attempt_at
                    FOR UPDATE SKIP LOCKED
                    LIMIT %s
                )
                UPDATE refunds r
                SET status = 'processing',
                    next_attempt_at = now() + interval '30 minutes',
                    attempt_count = r.attempt_count + 1
                FROM due WHERE r.id = due.id
                RETURNING r.id, r.payment_id, r.booking_id, r.amount, r.attempt_count
                """,
                (batch,),
            )
            rows = cur.fetchall()
        conn.commit()

        for refund_id, payment_id, booking_id, amount, attempt in rows:
            # fetch the gateway payment id (needed for the refund call)
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT gateway_txn_id FROM payments WHERE id=%s", (payment_id,)
                )
                gw = cur.fetchone()
            gateway_payment_id = gw[0] if gw else None

            try:
                if not gateway_payment_id:
                    raise RuntimeError("missing gateway_txn_id on payment")
                gateway_refund_id = create_refund_sync(
                    payment_gateway_id=gateway_payment_id,
                    amount_paise=int(float(amount) * 100),
                    idempotency_key=str(refund_id),  # = refunds.id
                )
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE refunds SET status='succeeded', gateway_refund_id=%s, "
                        "last_error=NULL WHERE id=%s",
                        (gateway_refund_id, refund_id),
                    )
                conn.commit()
                processed += 1
                log.info("refund_succeeded", refund_id=str(refund_id))
            except Exception as exc:  # noqa: BLE001
                with conn.cursor() as cur:
                    if attempt >= MAX_ATTEMPTS:
                        cur.execute(
                            "UPDATE refunds SET status='failed_permanent', last_error=%s "
                            "WHERE id=%s",
                            (str(exc)[:500], refund_id),
                        )
                        log.error("refund_failed_permanent", refund_id=str(refund_id), error=str(exc))
                        celery_app.send_task(
                            "app.workers.notifications.alert_refund_failed",
                            args=[str(refund_id)],
                        )
                    else:
                        delay = BACKOFF_MINUTES[min(attempt, len(BACKOFF_MINUTES) - 1)]
                        cur.execute(
                            "UPDATE refunds SET status='pending', last_error=%s, "
                            "next_attempt_at = now() + make_interval(mins => %s) WHERE id=%s",
                            (str(exc)[:500], delay, refund_id),
                        )
                        log.warning("refund_retry", refund_id=str(refund_id), attempt=attempt)
                conn.commit()
        return {"processed": processed, "picked": len(rows)}
    finally:
        conn.close()
