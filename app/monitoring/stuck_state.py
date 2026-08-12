"""SQL detectors for stuck-state conditions (SPEC_AMENDMENTS §10)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.monitoring.registry import AlertType
from app.services.reconfirmation import slot_local_expr


@dataclass(frozen=True, slots=True)
class DetectedCondition:
    alert_type: AlertType
    subject_id: str
    payload: dict[str, Any]


def stuck_payment_pending_sql(payment_ttl_minutes: int, grace_minutes: int) -> str:
    threshold = payment_ttl_minutes + grace_minutes
    return f"""
        SELECT b.id::text, b.created_at, p.id::text AS payment_id
        FROM bookings b
        JOIN status_types st ON st.id = b.status_id
        JOIN payments p ON p.booking_id = b.id AND p.status = 'success'
        WHERE st.domain = 'booking' AND st.code = 'payment_pending'
          AND b.cancelled_at IS NULL
          AND b.created_at <= now() - make_interval(mins => {threshold})
        FOR UPDATE OF b SKIP LOCKED
    """


def stuck_confirmed_no_show_sql(grace_minutes: int) -> str:
    slot = slot_local_expr("b")
    return f"""
        SELECT b.id::text, {slot} AS slot_at, b.pujari_id::text
        FROM bookings b
        JOIN status_types st ON st.id = b.status_id
        WHERE st.domain = 'booking' AND st.code = 'confirmed'
          AND b.cancelled_at IS NULL
          AND b.pujari_id IS NOT NULL
          AND now() >= {slot} + make_interval(mins => {grace_minutes})
        FOR UPDATE OF b SKIP LOCKED
    """


def refund_stall_sql(min_attempts: int) -> str:
    return f"""
        SELECT r.id::text, r.booking_id::text, r.attempt_count, r.status
        FROM refunds r
        WHERE r.status IN ('pending', 'processing')
          AND r.attempt_count >= {min_attempts}
        FOR UPDATE OF r SKIP LOCKED
    """


def detect_stuck_payment_pending(
    cur, *, payment_ttl_minutes: int, grace_minutes: int
) -> list[DetectedCondition]:
    cur.execute(stuck_payment_pending_sql(payment_ttl_minutes, grace_minutes))
    return [
        DetectedCondition(
            alert_type=AlertType.STUCK_PAYMENT_PENDING,
            subject_id=str(row[0]),
            payload={
                "booking_id": str(row[0]),
                "payment_id": str(row[2]),
                "created_at": row[1].isoformat() if row[1] else None,
            },
        )
        for row in cur.fetchall()
    ]


def detect_stuck_confirmed_no_show(cur, *, grace_minutes: int) -> list[DetectedCondition]:
    cur.execute(stuck_confirmed_no_show_sql(grace_minutes))
    return [
        DetectedCondition(
            alert_type=AlertType.STUCK_CONFIRMED_NO_SHOW,
            subject_id=str(row[0]),
            payload={
                "booking_id": str(row[0]),
                "slot_at": row[1].isoformat() if row[1] else None,
                "pujari_id": str(row[2]) if row[2] else None,
                "action": "admin_manual_resolution",
            },
        )
        for row in cur.fetchall()
    ]


def detect_refund_stalls(cur, *, min_attempts: int) -> list[DetectedCondition]:
    cur.execute(refund_stall_sql(min_attempts))
    return [
        DetectedCondition(
            alert_type=AlertType.REFUND_STALL,
            subject_id=str(row[0]),
            payload={
                "refund_id": str(row[0]),
                "booking_id": str(row[1]),
                "attempt_count": int(row[2]),
                "status": str(row[3]),
            },
        )
        for row in cur.fetchall()
    ]
