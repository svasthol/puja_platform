"""Partner advance reconfirm ack (§23.5, P-RECONFIRM-API)."""
from __future__ import annotations

import datetime as dt
import uuid

from fastapi import HTTPException, status as http
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def pujari_reconfirm_booking(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    booking_id: uuid.UUID,
) -> dict:
    """Set booking_reconfirmations.pujari_confirmed_at idempotently."""
    now = dt.datetime.now(dt.UTC)
    row = (
        await db.execute(
            text(
                """
                SELECT b.id, st.code AS status, b.booking_class,
                       pj.user_id AS pujari_user_id,
                       br.ping_sent_at, br.pujari_confirmed_at
                FROM bookings b
                JOIN status_types st ON st.id = b.status_id
                JOIN pujaris pj ON pj.id = b.pujari_id
                LEFT JOIN booking_reconfirmations br ON br.booking_id = b.id
                WHERE b.id = :bid
                FOR UPDATE OF b
                """
            ),
            {"bid": str(booking_id)},
        )
    ).mappings().first()

    if row is None:
        raise HTTPException(http.HTTP_404_NOT_FOUND, "Booking not found.")
    if str(row["pujari_user_id"]) != str(user_id):
        raise HTTPException(
            http.HTTP_409_CONFLICT,
            "Not the assigned pujari for this booking.",
        )
    if row["status"] != "confirmed":
        raise HTTPException(
            http.HTTP_409_CONFLICT,
            "Booking must be confirmed to reconfirm attendance.",
        )
    if row["booking_class"] != "advance":
        raise HTTPException(
            http.HTTP_409_CONFLICT,
            "Reconfirm applies to advance bookings only.",
        )
    if row["ping_sent_at"] is None:
        raise HTTPException(
            http.HTTP_409_CONFLICT,
            "Reconfirm is not available until the attendance ping is sent.",
        )

    existing = row["pujari_confirmed_at"]
    if existing is not None:
        return {
            "booking_id": booking_id,
            "pujari_confirmed_at": existing,
            "already_confirmed": True,
        }

    await db.execute(
        text(
            """
            INSERT INTO booking_reconfirmations (booking_id, pujari_confirmed_at)
            VALUES (:bid, :now)
            ON CONFLICT (booking_id) DO UPDATE
            SET pujari_confirmed_at = COALESCE(
                booking_reconfirmations.pujari_confirmed_at, EXCLUDED.pujari_confirmed_at
            )
            """
        ),
        {"bid": str(booking_id), "now": now},
    )
    confirmed_at = (
        await db.execute(
            text(
                "SELECT pujari_confirmed_at FROM booking_reconfirmations "
                "WHERE booking_id = :bid"
            ),
            {"bid": str(booking_id)},
        )
    ).scalar_one()
    return {
        "booking_id": booking_id,
        "pujari_confirmed_at": confirmed_at,
        "already_confirmed": False,
    }
