"""Admin refund override + support caps (A-REFUND)."""
from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.dependencies import Principal
from app.models.payment import Refund

_CAP_KEYS = ("support_refund_cap_per_action", "support_refund_cap_daily")


async def _load_support_caps(db: AsyncSession) -> tuple[Decimal, Decimal]:
    settings = get_settings()
    per_action = Decimal(str(settings.DEFAULT_SUPPORT_REFUND_CAP_PER_ACTION))
    daily = Decimal(str(settings.DEFAULT_SUPPORT_REFUND_CAP_DAILY))
    rows = (
        await db.execute(
            text(
                "SELECT key, value_json FROM platform_settings WHERE key = ANY(:keys)"
            ),
            {"keys": list(_CAP_KEYS)},
        )
    ).all()
    for key, value_json in rows:
        if value_json is None:
            continue
        try:
            amount = Decimal(str(value_json.get("amount", value_json)))
        except (TypeError, ValueError, AttributeError):
            continue
        if key == "support_refund_cap_per_action":
            per_action = amount
        elif key == "support_refund_cap_daily":
            daily = amount
    return per_action, daily


async def _support_daily_override_total(db: AsyncSession, actor_user_id: uuid.UUID) -> Decimal:
    """Sum of refund_override amounts issued by this support actor today (IST)."""
    row = (
        await db.execute(
            text(
                """
                SELECT COALESCE(SUM((after_json->>'amount')::numeric), 0) AS total
                FROM admin_audit_log
                WHERE actor_user_id = :uid
                  AND action = 'refund_override'
                  AND entity_type = 'refund'
                  AND created_at >= (
                      date_trunc('day', now() AT TIME ZONE 'Asia/Kolkata')
                      AT TIME ZONE 'Asia/Kolkata'
                  )
                """
            ),
            {"uid": str(actor_user_id)},
        )
    ).mappings().first()
    return Decimal(str(row["total"] if row else 0))


async def _enforce_support_caps(
    db: AsyncSession,
    *,
    actor: Principal,
    amount: Decimal,
) -> None:
    if actor.has_role("admin"):
        return
    if not actor.has_role("support"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Refund override requires support or admin role.")

    per_action, daily_cap = await _load_support_caps(db)
    if amount > per_action:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"Refund amount exceeds support per-action cap (₹{per_action}).",
        )
    used_today = await _support_daily_override_total(db, actor.user_id)
    if used_today + amount > daily_cap:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"Refund would exceed support daily cap (₹{daily_cap}; ₹{used_today} used today).",
        )


async def create_refund_override(
    db: AsyncSession,
    *,
    actor: Principal,
    amount: Decimal,
    payment_id: uuid.UUID | None = None,
    booking_id: uuid.UUID | None = None,
) -> Refund:
    if payment_id is None and booking_id is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Provide payment_id or booking_id.",
        )
    if amount <= 0:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Amount must be positive.")

    await _enforce_support_caps(db, actor=actor, amount=amount)

    if payment_id is not None:
        pay_sql = "SELECT id, booking_id, amount, status FROM payments WHERE id = :pid"
        params: dict = {"pid": str(payment_id)}
    else:
        pay_sql = (
            "SELECT id, booking_id, amount, status FROM payments "
            "WHERE booking_id = :bid AND status = 'success' ORDER BY created_at DESC LIMIT 1"
        )
        params = {"bid": str(booking_id)}

    payment = (await db.execute(text(pay_sql), params)).mappings().first()
    if payment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Successful payment not found.")
    if payment["status"] != "success":
        raise HTTPException(status.HTTP_409_CONFLICT, "Payment is not in success state.")

    refunded = (
        await db.execute(
            text(
                """
                SELECT COALESCE(SUM(amount), 0) AS total
                FROM refunds
                WHERE payment_id = :pid AND status = 'succeeded'
                """
            ),
            {"pid": str(payment["id"])},
        )
    ).scalar_one()
    remaining = Decimal(str(payment["amount"])) - Decimal(str(refunded))
    if amount > remaining:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Refund amount exceeds remaining refundable balance (₹{remaining}).",
        )

    now = dt.datetime.now(dt.UTC)
    refund = Refund(
        id=uuid.uuid4(),
        payment_id=payment["id"],
        booking_id=payment["booking_id"],
        amount=amount,
        reason="admin_override",
        status="pending",
        attempt_count=0,
        next_attempt_at=now,
        created_at=now,
    )
    db.add(refund)
    return refund
