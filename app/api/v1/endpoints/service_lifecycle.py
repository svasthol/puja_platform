"""Pujari service lifecycle: start, confirm-balance-collected, complete.

Time-window and balance gates per API_CONTRACTS transition matrix.
"""
from __future__ import annotations

import datetime as dt
import uuid
import zoneinfo

from fastapi import APIRouter, Depends, HTTPException, status as http
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.dependencies import Principal, require_pujari
from app.core.exceptions import StaleBookingState
from app.db.engine import get_db_txn
from app.schemas.booking import BalanceCollected, PujariCancelResponse
from app.services import pujari_cancel_service
from app.services.status import status_id

router = APIRouter(tags=["service"])
settings = get_settings()
_TZ = zoneinfo.ZoneInfo(settings.PLATFORM_TIMEZONE)


async def _assigned_booking(db: AsyncSession, booking_id: uuid.UUID, user_id: uuid.UUID) -> dict:
    row = (
        await db.execute(
            text(
                "SELECT b.id, st.code AS status, b.scheduled_date, b.scheduled_time, "
                "b.payment_mode, b.amount_due_offline, b.balance_collected_at, b.pujari_id "
                "FROM bookings b JOIN status_types st ON st.id=b.status_id "
                "JOIN pujaris pj ON pj.id = b.pujari_id "
                "WHERE b.id = :bid AND pj.user_id = :uid FOR UPDATE OF b"
            ),
            {"bid": str(booking_id), "uid": str(user_id)},
        )
    ).mappings().first()
    if row is None:
        raise HTTPException(http.HTTP_403_FORBIDDEN, "Not the assigned pujari for this booking.")
    return dict(row)


@router.post("/bookings/{booking_id}/pujari-cancel", response_model=PujariCancelResponse)
async def pujari_cancel(
    booking_id: uuid.UUID,
    p: Principal = Depends(require_pujari),
    db: AsyncSession = Depends(get_db_txn),
):
    result = await pujari_cancel_service.pujari_cancel_booking(
        db, user_id=p.user_id, booking_id=booking_id
    )
    if result.get("enqueue_rebroadcast"):
        from app.workers.celery_app import celery_app

        celery_app.send_task(
            "app.workers.dispatch.rebroadcast_booking",
            args=[result["enqueue_rebroadcast"], True],
        )
    return PujariCancelResponse(
        booking_id=booking_id,
        status=result["status"],
    )


@router.post("/bookings/{booking_id}/start")
async def start(booking_id: uuid.UUID, p: Principal = Depends(require_pujari), db: AsyncSession = Depends(get_db_txn)):
    b = await _assigned_booking(db, booking_id, p.user_id)
    if b["status"] != "confirmed":
        raise HTTPException(http.HTTP_409_CONFLICT, "Booking must be confirmed to start.")
    scheduled = dt.datetime.combine(b["scheduled_date"], b["scheduled_time"], tzinfo=_TZ)
    delta_min = abs((dt.datetime.now(dt.UTC).astimezone(_TZ) - scheduled).total_seconds()) / 60
    if delta_min > 60:
        raise HTTPException(http.HTTP_409_CONFLICT, "Can only start within ±60 min of scheduled time.")
    in_progress = await status_id(db, "booking", "in_progress")
    confirmed_id = await status_id(db, "booking", "confirmed")
    result = await db.execute(
        text(
            "UPDATE bookings SET status_id=:new, updated_at=now() "
            "WHERE id=:b AND status_id=:expected"
        ),
        {"new": in_progress, "b": str(booking_id), "expected": confirmed_id},
    )
    if result.rowcount == 0:
        raise StaleBookingState()
    await db.execute(
        text("INSERT INTO booking_status_history (id,booking_id,status_id,changed_by,changed_at) VALUES (gen_random_uuid(),:b,:s,:u,now())"),
        {"b": str(booking_id), "s": in_progress, "u": str(p.user_id)},
    )
    return {"status": "in_progress"}


@router.post("/bookings/{booking_id}/confirm-balance-collected")
async def confirm_balance(booking_id: uuid.UUID, payload: BalanceCollected, p: Principal = Depends(require_pujari), db: AsyncSession = Depends(get_db_txn)):
    b = await _assigned_booking(db, booking_id, p.user_id)
    if b["payment_mode"] != "advance_balance" or (b["amount_due_offline"] or 0) <= 0:
        raise HTTPException(http.HTTP_400_BAD_REQUEST, "No offline balance to collect.")
    if b["balance_collected_at"] is not None:
        return {"status": "already_collected"}  # idempotent
    await db.execute(
        text(
            "UPDATE bookings SET balance_collected_at=now(), balance_collected_by=:u, "
            "balance_collection_method=:m, updated_at=now() WHERE id=:b"
        ),
        {"u": str(p.user_id), "m": payload.method, "b": str(booking_id)},
    )
    return {"status": "collected", "method": payload.method}


@router.post("/bookings/{booking_id}/complete")
async def complete(booking_id: uuid.UUID, p: Principal = Depends(require_pujari), db: AsyncSession = Depends(get_db_txn)):
    b = await _assigned_booking(db, booking_id, p.user_id)
    if b["status"] != "in_progress":
        raise HTTPException(http.HTTP_409_CONFLICT, "Booking must be in progress to complete.")
    if b["payment_mode"] == "advance_balance" and (b["amount_due_offline"] or 0) > 0 and b["balance_collected_at"] is None:
        raise HTTPException(http.HTTP_409_CONFLICT, "Record offline balance collection before completing.")
    completed = await status_id(db, "booking", "completed")
    in_progress_id = await status_id(db, "booking", "in_progress")
    result = await db.execute(
        text(
            "UPDATE bookings SET status_id=:new, updated_at=now() "
            "WHERE id=:b AND status_id=:expected"
        ),
        {"new": completed, "b": str(booking_id), "expected": in_progress_id},
    )
    if result.rowcount == 0:
        raise StaleBookingState()
    await db.execute(
        text("INSERT INTO booking_status_history (id,booking_id,status_id,changed_by,changed_at) VALUES (gen_random_uuid(),:b,:s,:u,now())"),
        {"b": str(booking_id), "s": completed, "u": str(p.user_id)},
    )
    return {"status": "completed"}
