"""Pujari assigned bookings — list + detail (B-BOOKINGS / P-LAUNCH-PUJARI-BOOKING)."""
from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status as http
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import Principal, require_pujari
from app.db.engine import get_db, get_db_txn
from app.schemas.common import decode_cursor, encode_cursor
from app.schemas.pujari_booking import (
    PujariBookingAddress,
    PujariBookingDetail,
    PujariBookingListResponse,
    PujariBookingSummary,
)
from app.schemas.pujari_reconfirm import PujariReconfirmResponse
from app.schemas.relationship_manager import RelationshipManagerPublic
from app.services.pujari_reconfirm import pujari_reconfirm_booking
from app.services.pricing import BOOKING_FEE_LABEL
from app.services.relationship_manager import fetch_rm_public, status_exposes_rm

router = APIRouter(prefix="/pujari/bookings", tags=["pujari-bookings"])

_STATUSES_LIST = frozenset(
    {"confirmed", "in_progress", "completed", "disputed", "cancelled"}
)
_STATUSES_DETAIL = frozenset(
    {"confirmed", "in_progress", "completed", "disputed", "cancelled"}
)


def _reconfirm_pending(
    *,
    status: str,
    booking_class: str,
    ping_sent_at: dt.datetime | None,
    pujari_confirmed_at: dt.datetime | None,
) -> bool:
    return (
        status == "confirmed"
        and booking_class == "advance"
        and ping_sent_at is not None
        and pujari_confirmed_at is None
    )


async def _pujari_id(db: AsyncSession, user_id: uuid.UUID) -> uuid.UUID:
    pid = (
        await db.execute(
            text("SELECT id FROM pujaris WHERE user_id = :uid"),
            {"uid": str(user_id)},
        )
    ).scalar_one_or_none()
    if pid is None:
        raise HTTPException(http.HTTP_403_FORBIDDEN, "Not a pujari account.")
    return pid


@router.get("", response_model=PujariBookingListResponse)
async def list_pujari_bookings(
    cursor: str | None = None,
    limit: int = Query(20, ge=1, le=50),
    p: Principal = Depends(require_pujari),
    db: AsyncSession = Depends(get_db),
):
    """Assigned pujari's bookings — summary rows for Bookings tab (§21.9)."""
    pujari_id = await _pujari_id(db, p.user_id)
    params: dict = {
        "pid": str(pujari_id),
        "lim": limit + 1,
        "statuses": list(_STATUSES_LIST),
    }
    cursor_pred = ""
    if cursor:
        date_str, time_str, id_str = decode_cursor(cursor, 3)
        try:
            params["c_date"] = dt.date.fromisoformat(date_str)
            params["c_time"] = dt.time.fromisoformat(time_str)
            params["c_id"] = uuid.UUID(id_str)
        except ValueError:
            raise HTTPException(http.HTTP_422_UNPROCESSABLE_ENTITY, "Invalid cursor.")
        cursor_pred = (
            "AND (b.scheduled_date, b.scheduled_time, b.id) > "
            "(:c_date, :c_time, :c_id) "
        )

    rows = (
        await db.execute(
            text(
                f"""
                SELECT
                    b.id,
                    st.code AS status,
                    b.booking_class,
                    pu.name AS puja_name,
                    b.scheduled_date,
                    b.scheduled_time,
                    b.duration_minutes,
                    sa.zone_name AS area_label,
                    b.payment_mode,
                    b.total_amount,
                    b.amount_due_offline,
                    br.ping_sent_at AS reconfirm_ping_sent_at,
                    br.pujari_confirmed_at
                FROM bookings b
                JOIN status_types st ON st.id = b.status_id
                JOIN pujas pu ON pu.id = b.puja_id
                JOIN addresses a ON a.id = b.address_id
                LEFT JOIN service_areas sa ON sa.id = a.service_area_id
                LEFT JOIN booking_reconfirmations br ON br.booking_id = b.id
                WHERE b.pujari_id = :pid
                  AND st.code = ANY(:statuses)
                  {cursor_pred}
                ORDER BY b.scheduled_date ASC, b.scheduled_time ASC, b.id ASC
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
        next_cursor = encode_cursor(
            last["scheduled_date"].isoformat(),
            last["scheduled_time"].isoformat(),
            last["id"],
        )

    bookings = [
        PujariBookingSummary(
            id=row["id"],
            status=row["status"],
            puja_name=row["puja_name"],
            scheduled_date=row["scheduled_date"],
            scheduled_time=row["scheduled_time"],
            duration_minutes=row["duration_minutes"],
            area_label=row["area_label"],
            payment_mode=row["payment_mode"],
            total_amount=Decimal(str(row["total_amount"])),
            amount_due_offline=Decimal(str(row["amount_due_offline"])),
            reconfirm_pending=_reconfirm_pending(
                status=row["status"],
                booking_class=row["booking_class"],
                ping_sent_at=row["reconfirm_ping_sent_at"],
                pujari_confirmed_at=row["pujari_confirmed_at"],
            ),
        )
        for row in rows
    ]
    return PujariBookingListResponse(bookings=bookings, next_cursor=next_cursor)


@router.get("/{booking_id}", response_model=PujariBookingDetail)
async def get_pujari_booking(
    booking_id: uuid.UUID,
    p: Principal = Depends(require_pujari),
    db: AsyncSession = Depends(get_db),
):
    """Assigned pujari only — full address + map link + RM; no customer phone (§21.4)."""
    row = (
        await db.execute(
            text(
                """
                SELECT
                    b.id, st.code AS status, b.booking_class,
                    b.scheduled_date, b.scheduled_time,
                    b.duration_minutes, b.payment_mode, b.total_amount,
                    b.booking_fee, b.amount_due_online, b.amount_due_offline,
                    b.balance_collected_at, b.balance_collected_amount,
                    b.pujari_id, pj_user.id AS pujari_user_id,
                    pu.name AS puja_name,
                    a.line1, a.line2, a.city, a.pincode,
                    a.latitude, a.longitude,
                    sa.zone_name AS area_label,
                    br.ping_sent_at AS reconfirm_ping_sent_at,
                    br.pujari_confirmed_at
                FROM bookings b
                JOIN status_types st ON st.id = b.status_id
                JOIN pujas pu ON pu.id = b.puja_id
                JOIN addresses a ON a.id = b.address_id
                LEFT JOIN service_areas sa ON sa.id = a.service_area_id
                LEFT JOIN booking_reconfirmations br ON br.booking_id = b.id
                JOIN pujaris pj ON pj.id = b.pujari_id
                JOIN users pj_user ON pj_user.id = pj.user_id
                WHERE b.id = :bid
                """
            ),
            {"bid": str(booking_id)},
        )
    ).mappings().first()
    if row is None:
        raise HTTPException(http.HTTP_404_NOT_FOUND, "Booking not found.")
    if str(row["pujari_user_id"]) != str(p.user_id):
        raise HTTPException(http.HTTP_403_FORBIDDEN, "Not your booking.")
    if row["status"] not in _STATUSES_DETAIL:
        raise HTTPException(
            http.HTTP_409_CONFLICT,
            "Booking detail is available after assignment is confirmed.",
        )

    lat = row["latitude"]
    lng = row["longitude"]
    map_url = None
    if lat is not None and lng is not None:
        map_url = f"https://maps.google.com/?q={lat},{lng}"

    relationship_manager: RelationshipManagerPublic | None = None
    if status_exposes_rm(row["status"]):
        relationship_manager = await fetch_rm_public(db, booking_id)

    return PujariBookingDetail(
        id=row["id"],
        status=row["status"],
        booking_class=row["booking_class"],
        puja_name=row["puja_name"],
        scheduled_date=row["scheduled_date"],
        scheduled_time=row["scheduled_time"],
        duration_minutes=row["duration_minutes"],
        payment_mode=row["payment_mode"],
        total_amount=Decimal(str(row["total_amount"])),
        booking_fee=Decimal(str(row.get("booking_fee") or 0)),
        booking_fee_label=BOOKING_FEE_LABEL if row["payment_mode"] == "booking_fee" else None,
        amount_due_online=Decimal(str(row["amount_due_online"])),
        amount_due_offline=Decimal(str(row["amount_due_offline"])),
        balance_collected_at=row["balance_collected_at"],
        balance_collected_amount=(
            Decimal(str(row["balance_collected_amount"]))
            if row.get("balance_collected_amount") is not None
            else None
        ),
        area_label=row["area_label"],
        address=PujariBookingAddress(
            line1=row["line1"],
            line2=row["line2"],
            city=row["city"],
            pincode=row["pincode"],
            latitude=lat,
            longitude=lng,
        ),
        map_url=map_url,
        relationship_manager=relationship_manager,
        reconfirm_ping_sent_at=row["reconfirm_ping_sent_at"],
        pujari_confirmed_at=row["pujari_confirmed_at"],
    )


@router.post("/{booking_id}/reconfirm", response_model=PujariReconfirmResponse)
async def reconfirm_booking(
    booking_id: uuid.UUID,
    p: Principal = Depends(require_pujari),
    db: AsyncSession = Depends(get_db_txn),
):
    """Advance attendance ack — sets pujari_confirmed_at (§23.5)."""
    result = await pujari_reconfirm_booking(db, user_id=p.user_id, booking_id=booking_id)
    return PujariReconfirmResponse(**result)
