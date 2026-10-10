"""Admin booking search + 360° detail (Sprint 4C — A-SEARCH, A-BOOKING-DETAIL)."""
from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import Principal, require_admin
from app.db.engine import get_db_txn
from app.schemas.admin_bookings import (
    AdminBookingAddress,
    AdminBookingAssignment,
    AdminBookingCustomer,
    AdminBookingDetail,
    AdminBookingDispatch,
    AdminBookingListResponse,
    AdminBookingPayment,
    AdminBookingPujari,
    AdminBookingRefund,
    AdminBookingStatusEvent,
    AdminBookingSummary,
    AdminReassignRequest,
    AdminReassignResponse,
)
from app.schemas.admin_dispute import AdminDisputeRequest, AdminDisputeResponse
from app.schemas.admin_booking_tds import AdminBookingTdsResponse
from app.schemas.admin_money import AdminBookingMoneyResponse
from app.services.admin_booking_tds import fetch_booking_tds_snapshot
from app.schemas.common import decode_cursor, encode_cursor
from app.schemas.relationship_manager import RelationshipManagerPublic
from app.services.admin_dispute import open_dispute
from app.services.admin_money import fetch_booking_money
from app.services.audit import record_admin_action
from app.services.admin_reassign import manual_reassign
from app.services.relationship_manager import fetch_rm_public, status_exposes_rm

router = APIRouter(prefix="/admin/bookings", tags=["admin-bookings"])

_VALID_STATUSES = frozenset(
    {
        "payment_pending",
        "requested",
        "confirmed",
        "in_progress",
        "completed",
        "cancelled",
        "disputed",
        "failed_no_pujari",
        "abandoned",
    }
)


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


async def _audit_booking_read(
    db: AsyncSession,
    *,
    actor: Principal,
    request: Request,
    booking_id: uuid.UUID | None = None,
    filters: dict | None = None,
) -> None:
    """PII-read audit for search and detail (A-AUDIT-LOG 4C tail)."""
    await record_admin_action(
        db,
        actor_user_id=actor.user_id,
        action="read",
        entity_type="booking",
        entity_id=str(booking_id) if booking_id else None,
        after=filters,
        ip=_client_ip(request),
    )


@router.get("", response_model=AdminBookingListResponse)
async def search_bookings(
    request: Request,
    phone: str | None = Query(None, max_length=20, description="Customer phone"),
    booking_id: uuid.UUID | None = None,
    booking_status: str | None = Query(None, alias="status", description="Booking status code"),
    booking_class: str | None = Query(None, description="instant or advance"),
    date_from: dt.date | None = None,
    date_to: dt.date | None = None,
    cursor: str | None = None,
    limit: int = Query(20, ge=1, le=50),
    p: Principal = Depends(require_admin),
    db: AsyncSession = Depends(get_db_txn),
):
    """Search bookings for ops — phone, id, status, scheduled date range."""
    if booking_status is not None and booking_status not in _VALID_STATUSES:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"status must be one of: {', '.join(sorted(_VALID_STATUSES))}.",
        )
    if booking_class is not None and booking_class not in ("instant", "advance"):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "booking_class must be instant or advance.",
        )
    if date_from is not None and date_to is not None and date_from > date_to:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "date_from must be on or before date_to.",
        )

    params: dict = {"lim": limit + 1}
    filters_sql = "WHERE 1=1 "
    if phone:
        params["phone"] = f"%{phone.strip()}%"
        filters_sql += "AND u.phone ILIKE :phone "
    if booking_id is not None:
        params["bid"] = str(booking_id)
        filters_sql += "AND b.id = :bid "
    if booking_status:
        params["status"] = booking_status
        filters_sql += "AND st.code = :status "
    if booking_class:
        params["booking_class"] = booking_class
        filters_sql += "AND b.booking_class = :booking_class "
    if date_from is not None:
        params["date_from"] = date_from
        filters_sql += "AND b.scheduled_date >= :date_from "
    if date_to is not None:
        params["date_to"] = date_to
        filters_sql += "AND b.scheduled_date <= :date_to "

    cursor_pred = ""
    if cursor:
        created_str, id_str = decode_cursor(cursor, 2)
        try:
            params["c_created"] = dt.datetime.fromisoformat(created_str)
            params["c_id"] = uuid.UUID(id_str)
        except ValueError:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Invalid cursor.")
        cursor_pred = "AND (b.created_at, b.id) < (:c_created, :c_id) "

    rows = (
        await db.execute(
            text(
                f"""
                SELECT
                    b.id,
                    st.code AS status,
                    u.phone AS customer_phone,
                    u.full_name AS customer_name,
                    pu.name AS puja_name,
                    b.scheduled_date,
                    b.scheduled_time,
                    b.total_amount,
                    b.amount_due_online,
                    b.payment_mode,
                    b.paid_at,
                    b.created_at,
                    sa.zone_name AS area_label,
                    pj_user.full_name AS assigned_pujari_name
                FROM bookings b
                JOIN status_types st ON st.id = b.status_id
                JOIN users u ON u.id = b.user_id
                JOIN pujas pu ON pu.id = b.puja_id
                JOIN addresses a ON a.id = b.address_id
                LEFT JOIN service_areas sa ON sa.id = a.service_area_id
                LEFT JOIN pujaris pj ON pj.id = b.pujari_id
                LEFT JOIN users pj_user ON pj_user.id = pj.user_id
                {filters_sql}
                {cursor_pred}
                ORDER BY b.created_at DESC, b.id DESC
                LIMIT :lim
                """
            ),
            params,
        )
    ).mappings().all()

    next_cursor = None
    if len(rows) > limit:
        rows = rows[:limit]
        last = rows[-1]
        next_cursor = encode_cursor(last["created_at"].isoformat(), last["id"])

    audit_filters = {
        k: v
        for k, v in {
            "phone": phone,
            "booking_id": str(booking_id) if booking_id else None,
            "status": booking_status,
            "booking_class": booking_class,
            "date_from": date_from.isoformat() if date_from else None,
            "date_to": date_to.isoformat() if date_to else None,
        }.items()
        if v is not None
    }
    await _audit_booking_read(
        db, actor=p, request=request, filters=audit_filters or {"scope": "list"}
    )

    bookings = [
        AdminBookingSummary(
            id=row["id"],
            status=row["status"],
            customer_phone=row["customer_phone"],
            customer_name=row["customer_name"],
            puja_name=row["puja_name"],
            scheduled_date=row["scheduled_date"],
            scheduled_time=row["scheduled_time"],
            total_amount=Decimal(str(row["total_amount"])),
            amount_due_online=Decimal(str(row["amount_due_online"])),
            payment_mode=row["payment_mode"],
            paid_at=row["paid_at"],
            assigned_pujari_name=row["assigned_pujari_name"],
            area_label=row["area_label"],
            created_at=row["created_at"],
        )
        for row in rows
    ]
    return AdminBookingListResponse(bookings=bookings, next_cursor=next_cursor)


@router.get("/{booking_id}", response_model=AdminBookingDetail)
async def get_booking_detail(
    booking_id: uuid.UUID,
    request: Request,
    p: Principal = Depends(require_admin),
    db: AsyncSession = Depends(get_db_txn),
):
    """Booking 360° — history, assignments, payments, refunds, dispatch, address."""
    row = (
        await db.execute(
            text(
                """
                SELECT
                    b.id,
                    st.code AS status,
                    b.scheduled_date,
                    b.scheduled_time,
                    b.duration_minutes,
                    b.payment_mode,
                    b.total_amount,
                    b.amount_due_online,
                    b.amount_due_offline,
                    b.balance_collected_at,
                    b.paid_at,
                    b.razorpay_order_id,
                    b.cancelled_at,
                    b.created_at,
                    b.updated_at,
                    b.pujari_id,
                    b.dispatch_mode,
                    b.intended_pujari_id,
                    bds.dispatch_starts_at,
                    bds.dispatch_deadline,
                    pu.name AS puja_name,
                    u.id AS customer_user_id,
                    u.full_name AS customer_name,
                    u.phone AS customer_phone,
                    a.line1,
                    a.line2,
                    a.city,
                    a.pincode,
                    a.latitude,
                    a.longitude,
                    sa.zone_name AS area_label
                FROM bookings b
                JOIN status_types st ON st.id = b.status_id
                JOIN users u ON u.id = b.user_id
                JOIN pujas pu ON pu.id = b.puja_id
                JOIN addresses a ON a.id = b.address_id
                LEFT JOIN service_areas sa ON sa.id = a.service_area_id
                LEFT JOIN booking_dispatch_state bds ON bds.booking_id = b.id
                WHERE b.id = :bid
                """
            ),
            {"bid": str(booking_id)},
        )
    ).mappings().first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Booking not found.")

    pujari: AdminBookingPujari | None = None
    if row["pujari_id"] is not None:
        pj = (
            await db.execute(
                text(
                    """
                    SELECT pj.id, u.full_name, u.phone, pj.rating_avg, pj.rating_count
                    FROM pujaris pj
                    JOIN users u ON u.id = pj.user_id
                    WHERE pj.id = :pid
                    """
                ),
                {"pid": str(row["pujari_id"])},
            )
        ).mappings().first()
        if pj:
            pujari = AdminBookingPujari(
                id=pj["id"],
                full_name=pj["full_name"],
                phone=pj["phone"],
                rating_avg=Decimal(str(pj["rating_avg"])),
                rating_count=pj["rating_count"],
            )

    history_rows = (
        await db.execute(
            text(
                """
                SELECT st.code AS status, h.changed_at, h.changed_by,
                       ch.full_name AS changed_by_name
                FROM booking_status_history h
                JOIN status_types st ON st.id = h.status_id
                LEFT JOIN users ch ON ch.id = h.changed_by
                WHERE h.booking_id = :bid
                ORDER BY h.changed_at ASC
                """
            ),
            {"bid": str(booking_id)},
        )
    ).mappings().all()

    assignment_rows = (
        await db.execute(
            text(
                """
                SELECT ba.id, ba.pujari_id, u.full_name AS pujari_name, u.phone AS pujari_phone,
                       ast.code AS status, ba.offered_at, ba.expires_at, ba.responded_at
                FROM booking_assignments ba
                JOIN status_types ast ON ast.id = ba.status_id
                JOIN pujaris pj ON pj.id = ba.pujari_id
                JOIN users u ON u.id = pj.user_id
                WHERE ba.booking_id = :bid
                ORDER BY ba.offered_at ASC
                """
            ),
            {"bid": str(booking_id)},
        )
    ).mappings().all()

    payment_rows = (
        await db.execute(
            text(
                """
                SELECT id, amount, status, gateway_txn_id, idempotency_key, created_at
                FROM payments
                WHERE booking_id = :bid
                ORDER BY created_at ASC
                """
            ),
            {"bid": str(booking_id)},
        )
    ).mappings().all()

    refund_rows = (
        await db.execute(
            text(
                """
                SELECT id, amount, status, reason, gateway_refund_id, created_at
                FROM refunds
                WHERE booking_id = :bid
                ORDER BY created_at ASC
                """
            ),
            {"bid": str(booking_id)},
        )
    ).mappings().all()

    relationship_manager: RelationshipManagerPublic | None = None
    if status_exposes_rm(row["status"]):
        relationship_manager = await fetch_rm_public(db, booking_id)

    await _audit_booking_read(db, actor=p, request=request, booking_id=booking_id)

    return AdminBookingDetail(
        id=row["id"],
        status=row["status"],
        puja_name=row["puja_name"],
        scheduled_date=row["scheduled_date"],
        scheduled_time=row["scheduled_time"],
        duration_minutes=row["duration_minutes"],
        payment_mode=row["payment_mode"],
        total_amount=Decimal(str(row["total_amount"])),
        amount_due_online=Decimal(str(row["amount_due_online"])),
        amount_due_offline=Decimal(str(row["amount_due_offline"])),
        balance_collected_at=row["balance_collected_at"],
        paid_at=row["paid_at"],
        razorpay_order_id=row["razorpay_order_id"],
        cancelled_at=row["cancelled_at"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        customer=AdminBookingCustomer(
            user_id=row["customer_user_id"],
            full_name=row["customer_name"],
            phone=row["customer_phone"],
        ),
        address=AdminBookingAddress(
            line1=row["line1"],
            line2=row["line2"],
            city=row["city"],
            pincode=row["pincode"],
            latitude=float(row["latitude"]) if row["latitude"] is not None else None,
            longitude=float(row["longitude"]) if row["longitude"] is not None else None,
            area_label=row["area_label"],
        ),
        pujari=pujari,
        dispatch=AdminBookingDispatch(
            dispatch_mode=row["dispatch_mode"],
            dispatch_starts_at=row["dispatch_starts_at"],
            dispatch_deadline=row["dispatch_deadline"],
            intended_pujari_id=row["intended_pujari_id"],
        ),
        history=[
            AdminBookingStatusEvent(
                status=h["status"],
                changed_at=h["changed_at"],
                changed_by_user_id=h["changed_by"],
                changed_by_name=h["changed_by_name"],
            )
            for h in history_rows
        ],
        assignments=[
            AdminBookingAssignment(
                id=a["id"],
                pujari_id=a["pujari_id"],
                pujari_name=a["pujari_name"],
                pujari_phone=a["pujari_phone"],
                status=a["status"],
                offered_at=a["offered_at"],
                expires_at=a["expires_at"],
                responded_at=a["responded_at"],
            )
            for a in assignment_rows
        ],
        payments=[
            AdminBookingPayment(
                id=pay["id"],
                amount=Decimal(str(pay["amount"])),
                status=pay["status"],
                gateway_txn_id=pay["gateway_txn_id"],
                idempotency_key=pay["idempotency_key"],
                created_at=pay["created_at"],
            )
            for pay in payment_rows
        ],
        refunds=[
            AdminBookingRefund(
                id=ref["id"],
                amount=Decimal(str(ref["amount"])),
                status=ref["status"],
                reason=ref["reason"],
                gateway_refund_id=ref["gateway_refund_id"],
                created_at=ref["created_at"],
            )
            for ref in refund_rows
        ],
        relationship_manager=relationship_manager,
    )


@router.post("/{booking_id}/reassign", response_model=AdminReassignResponse)
async def reassign_booking(
    booking_id: uuid.UUID,
    body: AdminReassignRequest,
    request: Request,
    p: Principal = Depends(require_admin),
    db: AsyncSession = Depends(get_db_txn),
):
    """Manual reassign — clear-revoke-insert in one transaction (A-REASSIGN)."""
    before_row = (
        await db.execute(
            text(
                """
                SELECT b.pujari_id, st.code AS status
                FROM bookings b
                JOIN status_types st ON st.id = b.status_id
                WHERE b.id = :bid
                """
            ),
            {"bid": str(booking_id)},
        )
    ).mappings().first()
    if before_row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Booking not found.")

    result = await manual_reassign(
        db,
        booking_id=booking_id,
        new_pujari_id=body.new_pujari_id,
        admin_user_id=p.user_id,
    )
    await record_admin_action(
        db,
        actor_user_id=p.user_id,
        action="reassign",
        entity_type="booking",
        entity_id=str(booking_id),
        before={
            "pujari_id": str(before_row["pujari_id"]) if before_row["pujari_id"] else None,
            "status": before_row["status"],
        },
        after={
            "pujari_id": str(result["new_pujari_id"]),
            "assignment_id": str(result["assignment_id"]),
            "status": result["status"],
        },
        change_reason=body.change_reason,
        ip=_client_ip(request),
    )
    return AdminReassignResponse(**result)


@router.get("/{booking_id}/money", response_model=AdminBookingMoneyResponse)
async def get_booking_money(
    booking_id: uuid.UUID,
    request: Request,
    p: Principal = Depends(require_admin),
    db: AsyncSession = Depends(get_db_txn),
):
    """Read-only money view — settlement pending until P-SPLITS (A-MONEY-READ)."""
    money = await fetch_booking_money(db, booking_id=booking_id)
    await _audit_booking_read(db, actor=p, request=request, booking_id=booking_id)
    return money


@router.get("/{booking_id}/tds", response_model=AdminBookingTdsResponse)
async def get_booking_tds(
    booking_id: uuid.UUID,
    request: Request,
    p: Principal = Depends(require_admin),
    db: AsyncSession = Depends(get_db_txn),
):
    """Read-only TDS + offline collection snapshot for ops (no SQL)."""
    data = await fetch_booking_tds_snapshot(db, booking_id=booking_id)
    await _audit_booking_read(db, actor=p, request=request, booking_id=booking_id)
    return AdminBookingTdsResponse.model_validate(data)


@router.post("/{booking_id}/dispute", response_model=AdminDisputeResponse)
async def dispute_booking(
    booking_id: uuid.UUID,
    body: AdminDisputeRequest,
    request: Request,
    p: Principal = Depends(require_admin),
    db: AsyncSession = Depends(get_db_txn),
):
    """Mark in_progress booking as disputed (A-DISPUTE)."""
    result = await open_dispute(
        db,
        booking_id=booking_id,
        admin_user_id=p.user_id,
        dispute_type=body.dispute_type,
    )
    await record_admin_action(
        db,
        actor_user_id=p.user_id,
        action="dispute",
        entity_type="booking",
        entity_id=str(booking_id),
        before={"status": result["previous_status"]},
        after={
            "status": result["status"],
            "dispute_type": body.dispute_type,
        },
        change_reason=body.change_reason,
        ip=_client_ip(request),
    )
    tds = result.get("tds_reversal")
    return AdminDisputeResponse(
        booking_id=result["booking_id"],
        previous_status=result["previous_status"],
        status=result["status"],
        dispute_type=result["dispute_type"],
        disputed_at=result["disputed_at"],
        offline_balance_note=result.get("offline_balance_note"),
        tds_reversal=tds,
    )
