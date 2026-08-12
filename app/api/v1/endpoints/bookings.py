"""Booking + hold + checkout + cancel endpoints (customer app)."""
from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status as http
from fastapi.responses import ORJSONResponse
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import Principal, require_customer
from app.core.exceptions import DuplicateBookingSubmit, StaleBookingState
from app.db.engine import get_db, get_db_txn
from app.models.booking import SlotHold
from app.models.catalog import Puja, PujaAddon
from app.models.lookups import PlatformSetting
from app.schemas.booking import (
    BalanceCollected,
    BookingCreate,
    BookingCreateResponse,
    CheckoutQuote,
    DispatchChoice,
    GateWarning,
    QuotePaymentOption,
    SlotHoldRequest,
    SlotHoldResponse,
)
from app.schemas.common import decode_cursor, encode_cursor
from app.services import booking_service, cancellation_service
from app.services.razorpay_client import RazorpayError
from app.services.booking_gate import (
    evaluate_booking_gate,
    gate_warning_payload,
    load_booking_gate_settings,
    night_gate_error_code,
)
from app.services.launch_policy import DIRECT_BOOKING_ENABLED, reject_direct_booking
from app.services.relationship_manager import fetch_rm_public, status_exposes_rm
from app.services.status import status_id

router = APIRouter(tags=["bookings"])
log = structlog.get_logger()


@router.get("/checkout/quote", response_model=CheckoutQuote)
async def checkout_quote(
    puja_id: uuid.UUID,
    pujari_id: uuid.UUID | None = None,
    addon_ids: list[uuid.UUID] = Query(default_factory=list),
    _p: Principal = Depends(require_customer),
    db: AsyncSession = Depends(get_db),
):
    if pujari_id is not None:
        reject_direct_booking()
    from app.services.pricing_resolver import resolve_puja_unit_price

    puja = (await db.execute(select(Puja).where(Puja.id == puja_id))).scalar_one_or_none()
    if puja is None or not puja.is_active:
        raise HTTPException(http.HTTP_404_NOT_FOUND, "Puja not found.")
    unit_price = await resolve_puja_unit_price(db, puja_id, pujari_id)
    addon_total = Decimal("0")
    if addon_ids:
        prices = (
            await db.execute(
                select(PujaAddon.price).where(
                    PujaAddon.id.in_(addon_ids), PujaAddon.puja_id == puja_id
                )
            )
        ).scalars().all()
        addon_total = sum((Decimal(str(p)) for p in prices), Decimal("0"))
    total = unit_price + addon_total

    setting = (
        await db.execute(
            select(PlatformSetting.value_json).where(
                PlatformSetting.key == "advance_booking_amount"
            )
        )
    ).scalar_one()
    advance = Decimal(str(setting["amount"]))
    online = min(advance, total)
    return CheckoutQuote(
        total_amount=total,
        advance_amount=advance,
        full_online=QuotePaymentOption(
            amount_due_online=total, amount_due_offline=Decimal("0"),
            label="Pay full amount now (UPI / card)",
        ),
        advance_balance=QuotePaymentOption(
            amount_due_online=online, amount_due_offline=total - online,
            label=f"Pay ₹{online:.0f} now, rest ₹{total - online:.0f} to pujari at service",
        ),
    )


@router.post("/slot-holds", response_model=SlotHoldResponse, status_code=http.HTTP_201_CREATED)
async def create_slot_hold(
    payload: SlotHoldRequest,
    p: Principal = Depends(require_customer),
    db: AsyncSession = Depends(get_db_txn),
):
    if payload.pujari_id is not None:
        reject_direct_booking()
    now = dt.datetime.now(dt.UTC)
    hold = SlotHold(
        id=uuid.uuid4(),
        user_id=p.user_id,
        pujari_id=None,
        slot_date=payload.date,
        slot_time=payload.time,
        held_at=now,
        expires_at=now + dt.timedelta(minutes=5),
        released_at=None,
    )
    db.add(hold)
    await db.flush()  # ux_slot_holds_active -> 409 via shared handler if taken
    gate_settings = await load_booking_gate_settings(db)
    gate = evaluate_booking_gate(payload.date, payload.time, gate_settings, now=now)
    warnings: list[GateWarning] = []
    code = night_gate_error_code(
        gate.booking_class, gate.is_night, gate_settings.night_bookings_enabled
    )
    if code is not None:
        payload_dict = gate_warning_payload(code)
        warnings.append(GateWarning(**payload_dict))
    return SlotHoldResponse(
        hold_id=hold.id,
        expires_at=hold.expires_at,
        pujari_id=hold.pujari_id,
        server_time=now,
        advisory_booking_class=gate.booking_class,
        gate_warnings=warnings,
    )


@router.post("/bookings", response_model=BookingCreateResponse, status_code=http.HTTP_201_CREATED)
async def create_booking(
    payload: BookingCreate,
    p: Principal = Depends(require_customer),
    db: AsyncSession = Depends(get_db_txn),
):
    try:
        return await booking_service.create_booking(db, user_id=p.user_id, payload=payload)
    except DuplicateBookingSubmit as dup:
        # idempotent create per API_CONTRACTS: 409 + existing checkout payload
        return ORJSONResponse(
            status_code=http.HTTP_409_CONFLICT,
            content=dup.response.model_dump(mode="json"),
        )
    except RazorpayError as exc:
        log.error("booking_razorpay_order_failed", error=str(exc))
        raise HTTPException(
            http.HTTP_503_SERVICE_UNAVAILABLE,
            "Payment gateway is temporarily unavailable. Please try again.",
        ) from exc


@router.post("/bookings/{booking_id}/cancel")
async def cancel_booking(
    booking_id: uuid.UUID,
    p: Principal = Depends(require_customer),
    db: AsyncSession = Depends(get_db_txn),
):
    result = await cancellation_service.cancel_booking(db, user_id=p.user_id, booking_id=booking_id)
    return result


@router.get("/bookings")
async def list_bookings(
    cursor: str | None = None,
    limit: int = Query(20, ge=1, le=50),
    p: Principal = Depends(require_customer),
    db: AsyncSession = Depends(get_db),
):
    """C-LIST: customer's bookings, newest first, keyset-paginated."""
    params: dict = {"uid": str(p.user_id), "lim": limit + 1}
    cursor_pred = ""
    if cursor:
        created_str, id_str = decode_cursor(cursor, 2)
        try:
            params["c_dt"] = dt.datetime.fromisoformat(created_str)
            params["c_id"] = uuid.UUID(id_str)
        except ValueError:
            raise HTTPException(http.HTTP_422_UNPROCESSABLE_ENTITY, "Invalid cursor.")
        cursor_pred = "AND (b.created_at, b.id) < (:c_dt, :c_id) "
    rows = (
        await db.execute(
            text(
                "SELECT b.id, st.code AS status, b.booking_class, pj.name AS puja_name, "
                "b.scheduled_date, b.scheduled_time, b.payment_mode, b.total_amount, "
                "b.amount_due_online, b.amount_due_offline, b.pujari_id, "
                "pu.full_name AS pujari_name, b.created_at "
                "FROM bookings b "
                "JOIN status_types st ON st.id = b.status_id "
                "JOIN pujas pj ON pj.id = b.puja_id "
                "LEFT JOIN pujaris pr ON pr.id = b.pujari_id "
                "LEFT JOIN users pu ON pu.id = pr.user_id "
                "WHERE b.user_id = :uid "
                + cursor_pred
                + "ORDER BY b.created_at DESC, b.id DESC LIMIT :lim"
            ),
            params,
        )
    ).mappings().all()
    next_cursor = None
    if len(rows) > limit:
        rows = rows[:limit]
        last = rows[-1]
        next_cursor = encode_cursor(last["created_at"].isoformat(), last["id"])
    return {"bookings": [dict(r) for r in rows], "next_cursor": next_cursor}


@router.get("/bookings/{booking_id}")
async def get_booking(
    booking_id: uuid.UUID,
    p: Principal = Depends(require_customer),
    db: AsyncSession = Depends(get_db),
):
    """C-GET: status + payment breakdown + assigned pujari + history + refund."""
    row = (
        await db.execute(
            text(
                "SELECT b.id, st.code AS status, b.booking_class, b.payment_mode, b.total_amount, "
                "b.amount_due_online, b.amount_due_offline, b.balance_collected_at, "
                "b.pujari_id, b.user_id, b.dispatch_mode, b.scheduled_date, "
                "b.scheduled_time, b.duration_minutes, b.created_at, b.cancelled_at, "
                "b.razorpay_order_id, "
                "pj.name AS puja_name, "
                "a.line1 AS address_line1, a.city AS address_city "
                "FROM bookings b "
                "JOIN status_types st ON st.id = b.status_id "
                "JOIN pujas pj ON pj.id = b.puja_id "
                "JOIN addresses a ON a.id = b.address_id "
                "WHERE b.id = :bid"
            ),
            {"bid": str(booking_id)},
        )
    ).mappings().first()
    if row is None:
        raise HTTPException(http.HTTP_404_NOT_FOUND, "Booking not found.")
    if str(row["user_id"]) != str(p.user_id):
        raise HTTPException(http.HTTP_403_FORBIDDEN, "Not your booking.")

    detail = dict(row)

    pujari = None
    if row["pujari_id"] is not None:
        pujari = (
            await db.execute(
                text(
                    "SELECT p.id, u.full_name, p.rating_avg, p.rating_count, p.years_experience "
                    "FROM pujaris p JOIN users u ON u.id = p.user_id WHERE p.id = :pid"
                ),
                {"pid": str(row["pujari_id"])},
            )
        ).mappings().first()
    detail["pujari"] = dict(pujari) if pujari else None

    history = (
        await db.execute(
            text(
                "SELECT st.code AS status, h.changed_at "
                "FROM booking_status_history h JOIN status_types st ON st.id = h.status_id "
                "WHERE h.booking_id = :bid ORDER BY h.changed_at"
            ),
            {"bid": str(booking_id)},
        )
    ).mappings().all()
    detail["history"] = [dict(h) for h in history]

    refund = (
        await db.execute(
            text(
                "SELECT amount, status, created_at FROM refunds "
                "WHERE booking_id = :bid ORDER BY created_at DESC LIMIT 1"
            ),
            {"bid": str(booking_id)},
        )
    ).mappings().first()
    detail["refund"] = dict(refund) if refund else None

    if status_exposes_rm(row["status"]):
        rm = await fetch_rm_public(db, booking_id)
        detail["relationship_manager"] = rm.model_dump() if rm else None
    else:
        detail["relationship_manager"] = None

    return detail


@router.post("/bookings/{booking_id}/dispatch-choice")
async def dispatch_choice(
    booking_id: uuid.UUID,
    payload: DispatchChoice,
    p: Principal = Depends(require_customer),
    db: AsyncSession = Depends(get_db_txn),
):
    if not DIRECT_BOOKING_ENABLED:
        reject_direct_booking()
    return await _dispatch_choice_enabled(
        booking_id, payload, p, db
    )


async def _dispatch_choice_enabled(
    booking_id: uuid.UUID,
    payload: DispatchChoice,
    p: Principal,
    db: AsyncSession,
):
    """Phase 2 direct-booking fallback — broadcast or cancel when intended pujari unavailable."""
    row = (
        await db.execute(
            text("SELECT user_id, dispatch_mode FROM bookings WHERE id = :bid FOR UPDATE"),
            {"bid": str(booking_id)},
        )
    ).mappings().first()
    if row is None:
        raise HTTPException(http.HTTP_404_NOT_FOUND, "Booking not found.")
    if str(row["user_id"]) != str(p.user_id):
        raise HTTPException(http.HTTP_403_FORBIDDEN, "Not your booking.")
    if payload.action == "cancel":
        return await cancellation_service.cancel_booking(db, user_id=p.user_id, booking_id=booking_id)

    requested_id = await status_id(db, "booking", "requested")
    result = await db.execute(
        text(
            "UPDATE bookings "
            "SET intended_pujari_id = NULL, dispatch_mode = 'broadcast', updated_at = now() "
            "WHERE id = :bid AND status_id = :sid AND dispatch_mode = 'direct' AND pujari_id IS NULL"
        ),
        {"bid": str(booking_id), "sid": requested_id},
    )
    if result.rowcount == 0:
        raise StaleBookingState()

    from app.workers.celery_app import celery_app

    celery_app.send_task(
        "app.workers.dispatch.broadcast_booking", args=[str(booking_id)]
    )
    return {"status": "broadcasting", "booking_id": str(booking_id)}
