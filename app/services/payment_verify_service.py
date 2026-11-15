"""Client-side payment verify after Razorpay Checkout (REL-015)."""
from __future__ import annotations

import uuid

import structlog
from fastapi import HTTPException, status as http
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import verify_razorpay_checkout_signature
from app.db import post_commit
from app.models.booking import Booking
from app.services import payment_capture
from app.services import razorpay_client
from app.services.razorpay_client import RazorpayError
from app.services.status import status_id

log = structlog.get_logger()


async def verify_booking_payment(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    booking_id: uuid.UUID,
    razorpay_payment_id: str,
    razorpay_order_id: str,
    razorpay_signature: str,
) -> tuple[dict, int]:
    """Returns (body, suggested_http_status)."""
    pay_id = (razorpay_payment_id or "").strip()
    order_id = (razorpay_order_id or "").strip()
    if not pay_id.startswith("pay_") or not order_id.startswith("order_"):
        raise HTTPException(http.HTTP_400_BAD_REQUEST, "Invalid Razorpay payment or order id.")

    booking = (
        await db.execute(select(Booking).where(Booking.id == booking_id).with_for_update())
    ).scalar_one_or_none()
    if booking is None:
        raise HTTPException(http.HTTP_404_NOT_FOUND, "Booking not found.")
    if booking.user_id != user_id:
        raise HTTPException(http.HTTP_403_FORBIDDEN, "Not your booking.")

    if not verify_razorpay_checkout_signature(
        order_id=order_id, payment_id=pay_id, signature=razorpay_signature
    ):
        raise HTTPException(http.HTTP_400_BAD_REQUEST, "Invalid payment signature.")

    if booking.razorpay_order_id and str(booking.razorpay_order_id) != order_id:
        raise HTTPException(http.HTTP_409_CONFLICT, "Payment order does not match this booking.")

    pending_id = await status_id(db, "booking", "payment_pending")
    if booking.paid_at is not None or booking.status_id != pending_id:
        code = (
            await db.execute(
                text("SELECT code FROM status_types WHERE id = :sid"),
                {"sid": booking.status_id},
            )
        ).scalar_one()
        return (
            {
                "status": "already_confirmed",
                "booking_id": str(booking_id),
                "booking_status": code,
            },
            http.HTTP_200_OK,
        )

    try:
        payment_entity = await razorpay_client.fetch_payment(pay_id)
    except RazorpayError as exc:
        log.warning("payment_verify_fetch_failed", booking_id=str(booking_id), error=str(exc))
        raise HTTPException(
            http.HTTP_503_SERVICE_UNAVAILABLE,
            "Payment gateway is temporarily unavailable. Please try again.",
        ) from exc

    gateway_order = str(payment_entity.get("order_id") or "")
    if gateway_order and gateway_order != order_id:
        raise HTTPException(http.HTTP_409_CONFLICT, "Payment order does not match this booking.")

    capture_status = str(payment_entity.get("status") or "")
    if capture_status == "authorized":
        return (
            {
                "status": "processing",
                "booking_id": str(booking_id),
                "message": "Payment authorized; confirmation pending.",
            },
            http.HTTP_202_ACCEPTED,
        )
    if capture_status != "captured":
        raise HTTPException(
            http.HTTP_409_CONFLICT,
            f"Payment not captured (status={capture_status}).",
        )

    result = await payment_capture.handle_payment_captured(
        db,
        booking_id=booking_id,
        gateway_txn_id=pay_id,
        idempotency_key=pay_id,
        amount_paise=int(payment_entity.get("amount", 0)),
    )
    status = result.get("status", "unknown")
    if result.get("enqueue_direct"):
        post_commit.enqueue_celery_task(
            db,
            task_name="app.workers.dispatch.direct_dispatch",
            args=[result["enqueue_direct"]],
        )
    elif result.get("enqueue_broadcast"):
        post_commit.enqueue_celery_task(
            db,
            task_name="app.workers.dispatch.broadcast_booking",
            args=[result["enqueue_broadcast"]],
        )

    if status == "already_processed":
        code = (
            await db.execute(
                text("SELECT code FROM status_types WHERE id = :sid"),
                {"sid": booking.status_id},
            )
        ).scalar_one()
        return (
            {
                "status": "already_confirmed",
                "booking_id": str(booking_id),
                "booking_status": code,
            },
            http.HTTP_200_OK,
        )

    return (
        {
            "status": status,
            "booking_id": str(booking_id),
            "booking_status": "requested" if status == "confirmed" else None,
        },
        http.HTTP_200_OK,
    )