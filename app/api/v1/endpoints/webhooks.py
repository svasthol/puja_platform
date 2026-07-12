"""Razorpay webhook — signature verify + one-transaction flow. Always 200 once recorded."""
from __future__ import annotations

import uuid

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status as http
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import verify_razorpay_signature
from app.db.engine import get_db_txn
from app.services import webhook_service

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
log = structlog.get_logger()


@router.post("/razorpay")
async def razorpay_webhook(
    request: Request,
    x_razorpay_signature: str = Header(default=""),
    db: AsyncSession = Depends(get_db_txn),
):
    body = await request.body()
    if not verify_razorpay_signature(body, x_razorpay_signature):
        log.warning("razorpay_signature_invalid")
        raise HTTPException(http.HTTP_400_BAD_REQUEST, "Invalid signature")

    payload = await request.json()
    event = payload.get("event", "")
    if event not in ("payment.captured", "order.paid"):
        return {"status": "ignored", "event": event}

    entity = (
        payload.get("payload", {}).get("payment", {}).get("entity", {})
        or payload.get("payload", {}).get("order", {}).get("entity", {})
    )
    notes = entity.get("notes", {}) or {}
    booking_id = notes.get("booking_id")
    if not booking_id:
        log.error("webhook_missing_booking_id")
        return {"status": "no_booking_ref"}

    result = await webhook_service.handle_payment_captured(
        db,
        booking_id=uuid.UUID(booking_id),
        gateway_txn_id=entity.get("id", ""),
        idempotency_key=entity.get("id", ""),  # Razorpay payment id = stable dedupe key
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
