"""Razorpay webhook — signature verify + one-transaction flow. Always 200 once recorded."""
from __future__ import annotations

import uuid

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status as http
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import verify_razorpay_signature
from app.db.engine import get_db_txn
from app.monitoring import AlertType, emit_instant_alert
from app.services import webhook_service

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
log = structlog.get_logger()


async def _resolve_booking_id(db: AsyncSession, payload: dict) -> uuid.UUID | None:
    """Map webhook payload to booking_id.

    Razorpay copies order notes to payment inconsistently — fall back to
  `bookings.razorpay_order_id` lookup via payment.order_id (spec IDEMPOTENT_BOOKING).
    """
    root = payload.get("payload") or {}
    payment_entity = (root.get("payment") or {}).get("entity") or {}
    order_entity = (root.get("order") or {}).get("entity") or {}

    for notes_src in (payment_entity.get("notes"), order_entity.get("notes")):
        if isinstance(notes_src, dict):
            raw = notes_src.get("booking_id")
            if raw:
                try:
                    return uuid.UUID(str(raw))
                except ValueError:
                    log.warning("webhook_invalid_booking_id_note", booking_id=raw)

    order_id = payment_entity.get("order_id") or order_entity.get("id")
    if order_id:
        row = (
            await db.execute(
                text("SELECT id FROM bookings WHERE razorpay_order_id = :oid"),
                {"oid": str(order_id)},
            )
        ).scalar_one_or_none()
        if row is not None:
            return row

    return None


@router.post("/razorpay")
async def razorpay_webhook(
    request: Request,
    x_razorpay_signature: str = Header(default=""),
    db: AsyncSession = Depends(get_db_txn),
):
    body = await request.body()
    if not verify_razorpay_signature(body, x_razorpay_signature):
        emit_instant_alert(
            AlertType.WEBHOOK_SIGNATURE_INVALID,
            provider="razorpay",
            payload={"path": str(request.url.path)},
        )
        raise HTTPException(http.HTTP_400_BAD_REQUEST, "Invalid signature")

    payload = await request.json()
    event = payload.get("event", "")
    if event not in ("payment.captured", "order.paid"):
        return {"status": "ignored", "event": event}

    payment_entity = (payload.get("payload") or {}).get("payment", {}).get("entity", {})
    order_entity = (payload.get("payload") or {}).get("order", {}).get("entity", {})
    entity = payment_entity or order_entity

    booking_id = await _resolve_booking_id(db, payload)
    if booking_id is None:
        log.error("webhook_missing_booking_id", event=event)
        return {"status": "no_booking_ref"}

    result = await webhook_service.handle_payment_captured(
        db,
        booking_id=booking_id,
        gateway_txn_id=entity.get("id", ""),
        idempotency_key=entity.get("id", ""),
        amount_paise=int(entity.get("amount", 0)),
    )

    # enqueue dispatch AFTER commit is handled by the app; expose the id here.
    if result.get("enqueue_direct"):
        from app.workers.celery_app import celery_app

        celery_app.send_task(
            "app.workers.dispatch.direct_dispatch", args=[result["enqueue_direct"]]
        )
    elif result.get("enqueue_broadcast"):
        from app.workers.celery_app import celery_app

        celery_app.send_task(
            "app.workers.dispatch.broadcast_booking", args=[result["enqueue_broadcast"]]
        )
    return {"status": "ok", "result": result.get("status")}
