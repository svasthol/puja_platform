"""Admin booking money read-only (A-MONEY-READ)."""
from __future__ import annotations

import uuid
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.admin_money import (
    SETTLEMENT_PENDING_LABEL,
    AdminBookingMoneyResponse,
    AdminMoneyPayment,
    AdminMoneyPaymentSplit,
    AdminMoneyRefund,
)


async def fetch_booking_money(
    db: AsyncSession,
    *,
    booking_id: uuid.UUID,
) -> AdminBookingMoneyResponse:
    booking = (
        await db.execute(
            text(
                """
                SELECT
                    b.payment_mode,
                    b.total_amount,
                    b.amount_due_online,
                    b.amount_due_offline,
                    b.booking_fee,
                    b.balance_collected_at,
                    b.balance_collected_amount
                FROM bookings b
                WHERE b.id = :bid
                """
            ),
            {"bid": str(booking_id)},
        )
    ).mappings().first()
    if booking is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Booking not found.")

    payment_rows = (
        await db.execute(
            text(
                """
                SELECT
                    p.id,
                    p.amount,
                    p.status,
                    p.gateway_txn_id,
                    p.created_at,
                    ps.platform_fee,
                    ps.gst_amount,
                    ps.net_pujari_amount
                FROM payments p
                LEFT JOIN payment_splits ps ON ps.payment_id = p.id
                WHERE p.booking_id = :bid
                ORDER BY p.created_at ASC
                """
            ),
            {"bid": str(booking_id)},
        )
    ).mappings().all()

    refund_rows = (
        await db.execute(
            text(
                """
                SELECT id, payment_id, amount, status, reason, gateway_refund_id, created_at
                FROM refunds
                WHERE booking_id = :bid
                ORDER BY created_at ASC
                """
            ),
            {"bid": str(booking_id)},
        )
    ).mappings().all()

    payments: list[AdminMoneyPayment] = []
    total_paid_online = Decimal("0")
    for row in payment_rows:
        amount = Decimal(str(row["amount"]))
        if row["status"] == "success":
            total_paid_online += amount
        split = None
        if row["platform_fee"] is not None:
            split = AdminMoneyPaymentSplit(
                platform_fee=Decimal(str(row["platform_fee"])),
                gst_amount=Decimal(str(row["gst_amount"])),
                net_pujari_amount=Decimal(str(row["net_pujari_amount"])),
            )
        payments.append(
            AdminMoneyPayment(
                id=row["id"],
                amount=amount,
                status=row["status"],
                gateway_txn_id=row["gateway_txn_id"],
                created_at=row["created_at"],
                settlement_label=SETTLEMENT_PENDING_LABEL,
                split=split,
            )
        )

    refunds: list[AdminMoneyRefund] = []
    total_refunded_online = Decimal("0")
    for row in refund_rows:
        amount = Decimal(str(row["amount"]))
        if row["status"] == "succeeded":
            total_refunded_online += amount
        refunds.append(
            AdminMoneyRefund(
                id=row["id"],
                payment_id=row["payment_id"],
                amount=amount,
                status=row["status"],
                reason=row["reason"],
                gateway_refund_id=row["gateway_refund_id"],
                created_at=row["created_at"],
            )
        )

    offline_due = Decimal(str(booking["amount_due_offline"] or 0))
    booking_fee = Decimal(str(booking.get("booking_fee") or 0))
    offline_note: str | None = None
    if booking["payment_mode"] in ("advance_balance", "booking_fee") and offline_due > 0:
        offline_note = (
            f"Offline balance (₹{offline_due}) is collected directly by the pujari — "
            "not processed or refunded through the platform."
        )

    refundable_remaining = max(total_paid_online - total_refunded_online, Decimal("0"))
    if booking["payment_mode"] == "booking_fee" and booking_fee > 0:
        refundable_remaining = min(refundable_remaining, booking_fee)

    return AdminBookingMoneyResponse(
        booking_id=booking_id,
        payment_mode=booking["payment_mode"],
        total_amount=Decimal(str(booking["total_amount"])),
        amount_due_online=Decimal(str(booking["amount_due_online"])),
        amount_due_offline=offline_due,
        balance_collected_at=booking["balance_collected_at"],
        online_settlement_label=SETTLEMENT_PENDING_LABEL,
        offline_balance_note=offline_note,
        total_paid_online=total_paid_online,
        total_refunded_online=total_refunded_online,
        refundable_remaining_online=refundable_remaining,
        booking_fee=booking_fee if booking["payment_mode"] == "booking_fee" else None,
        payments=payments,
        refunds=refunds,
    )
