"""Pujari service lifecycle: start, confirm-balance-collected, complete.

Time-window and balance gates per API_CONTRACTS transition matrix.
"""
from __future__ import annotations

import datetime as dt
import uuid
import zoneinfo
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status as http
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.dependencies import Principal, require_pujari
from app.core.exceptions import StaleBookingState
from app.db.engine import get_db_txn
from app.schemas.booking import (
    BalanceCollected,
    BalanceCollectedResponse,
    PujariCancelResponse,
    TdsAccrualInfo,
)
from app.services import pujari_cancel_service, tds_accrual_service
from app.services.pujari_fy_pan_gate import (
    fy_pan_gate_collection_warning,
    fy_pan_gate_status_for_pujari,
)
from app.services.status import status_id

router = APIRouter(tags=["service"])
settings = get_settings()
_TZ = zoneinfo.ZoneInfo(settings.PLATFORM_TIMEZONE)
_OFFLINE_MODES = frozenset({"advance_balance", "booking_fee"})


async def _assigned_booking(db: AsyncSession, booking_id: uuid.UUID, user_id: uuid.UUID) -> dict:
    row = (
        await db.execute(
            text(
                "SELECT b.id, st.code AS status, b.scheduled_date, b.scheduled_time, "
                "b.payment_mode, b.amount_due_offline, b.total_amount, "
                "b.balance_collected_at, b.balance_collected_amount, b.pujari_id, "
                "b.total_amount "
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


def _offline_due(b: dict) -> Decimal:
    return Decimal(str(b.get("amount_due_offline") or 0))


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


@router.post(
    "/bookings/{booking_id}/confirm-balance-collected",
    response_model=BalanceCollectedResponse,
)
async def confirm_balance(
    booking_id: uuid.UUID,
    payload: BalanceCollected,
    p: Principal = Depends(require_pujari),
    db: AsyncSession = Depends(get_db_txn),
):
    b = await _assigned_booking(db, booking_id, p.user_id)
    if b["status"] != "in_progress":
        raise HTTPException(
            http.HTTP_409_CONFLICT,
            "Start the service before recording balance collection.",
        )
    offline_due = _offline_due(b)
    if b["payment_mode"] not in _OFFLINE_MODES or offline_due <= 0:
        raise HTTPException(http.HTTP_400_BAD_REQUEST, "No offline balance to collect.")
    if b["balance_collected_at"] is not None:
        tds_info = await tds_accrual_service.tds_snapshot_for_booking(
            db, booking_id=booking_id, pujari_id=uuid.UUID(str(b["pujari_id"]))
        )
        return BalanceCollectedResponse(
            status="already_collected",
            tds=TdsAccrualInfo(**tds_info),
        )
    if settings.TDS_ACCRUAL_ENABLED:
        from app.services.tds_v3_online_charge import (
            finalize_unresolved_tds_before_offline_collection,
        )

        await finalize_unresolved_tds_before_offline_collection(
            db,
            booking_id=booking_id,
            pujari_id=uuid.UUID(str(b["pujari_id"])),
        )
        refreshed = (
            await db.execute(
                text("SELECT amount_due_offline FROM bookings WHERE id = :bid"),
                {"bid": str(booking_id)},
            )
        ).scalar_one()
        b["amount_due_offline"] = refreshed
        offline_due = _offline_due(b)
        if b["payment_mode"] not in _OFFLINE_MODES or offline_due <= 0:
            raise HTTPException(http.HTTP_400_BAD_REQUEST, "No offline balance to collect.")
    collected = payload.amount if payload.amount is not None else offline_due
    if collected <= 0:
        raise HTTPException(http.HTTP_422_UNPROCESSABLE_ENTITY, "Collected amount must be positive.")
    if collected > offline_due:
        raise HTTPException(
            http.HTTP_422_UNPROCESSABLE_ENTITY,
            "Collected amount cannot exceed the offline balance due.",
        )
    gross_for_tds = Decimal(str(b["total_amount"]))
    pujari_uuid = uuid.UUID(str(b["pujari_id"]))
    gate_status = None
    if get_settings().PUJARI_FY_PAN_GATE_ENABLED:
        gate_status = await fy_pan_gate_status_for_pujari(
            db,
            pujari_id=pujari_uuid,
            additional_collection_inr=gross_for_tds,
        )
    await db.execute(
        text(
            "UPDATE bookings SET balance_collected_at=now(), balance_collected_by=:u, "
            "balance_collection_method=:m, balance_collected_amount=:amt, updated_at=now() "
            "WHERE id=:b"
        ),
        {
            "u": str(p.user_id),
            "m": payload.method,
            "amt": str(collected),
            "b": str(booking_id),
        },
    )
    await tds_accrual_service.capture_classification_snapshot_at_collection(
        db,
        booking_id=booking_id,
        pujari_id=uuid.UUID(str(b["pujari_id"])),
    )
    collected_at = dt.datetime.now(dt.UTC)
    tds_result = await tds_accrual_service.enqueue_tds_accrual_intent(
        db,
        booking_id=booking_id,
        pujari_id=uuid.UUID(str(b["pujari_id"])),
        gross_amount=gross_for_tds,
        collected_at=collected_at,
    )
    if (
        tds_result.get("accrual_enabled")
        and tds_result.get("skipped")
        and tds_result.get("message") == "TDS accrual queued."
    ):
        from app.workers.celery_app import celery_app

        celery_app.send_task("app.workers.tds_accrual.process_tds_accrual_intents")
    if gate_status is not None and gate_status.level in ("warn", "block"):
        tds_result = {**tds_result, **fy_pan_gate_collection_warning(gate_status)}
    return BalanceCollectedResponse(
        status="collected",
        method=payload.method,
        amount=collected,
        tds=TdsAccrualInfo(**tds_result),
    )


@router.post("/bookings/{booking_id}/complete")
async def complete(booking_id: uuid.UUID, p: Principal = Depends(require_pujari), db: AsyncSession = Depends(get_db_txn)):
    b = await _assigned_booking(db, booking_id, p.user_id)
    if b["status"] != "in_progress":
        raise HTTPException(http.HTTP_409_CONFLICT, "Booking must be in progress to complete.")
    offline_due = _offline_due(b)
    if b["payment_mode"] in _OFFLINE_MODES and offline_due > 0:
        if b["balance_collected_at"] is None:
            raise HTTPException(
                http.HTTP_409_CONFLICT,
                "Record offline balance collection before completing.",
            )
        collected_amt = Decimal(str(b.get("balance_collected_amount") or 0))
        if collected_amt < offline_due:
            raise HTTPException(
                http.HTTP_409_CONFLICT,
                "Full offline balance must be collected before completing.",
            )
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
