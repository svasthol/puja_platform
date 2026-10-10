"""Launch-gate: idempotent duplicate submit on POST /v1/bookings (SAVEPOINT + 409)."""
from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.core.exceptions import DuplicateBookingSubmit
from app.schemas.booking import BookingCreate
from app.services import booking_service, razorpay_client

pytestmark = pytest.mark.asyncio

FEE = Decimal("61.00")


async def test_duplicate_booking_submit_savepoint_lookup(session, seed, uniq, monkeypatch):
    """Second create for the same active slot raises DuplicateBookingSubmit with existing row."""
    user_id = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001")
    puja_id = uuid.UUID("11111111-1111-1111-1111-111111111111")
    address_id = uuid.UUID("dddddddd-0000-0000-0000-000000000001")
    slot_date = dt.date.fromisoformat(uniq.date)
    slot_time = dt.time(11, 0)
    existing_id = uuid.uuid4()
    hold_id = uuid.uuid4()
    order_id = f"order_{uniq.id()}"

    async with session.begin():
        await session.execute(
            text("""
                INSERT INTO platform_settings (key, value_json) VALUES
                ('booking_fee', '{"amount": 61.00, "currency": "INR", "label": "Muhurat & Slot Lock Token"}')
                ON CONFLICT (key) DO NOTHING
            """)
        )
        pending_id = (
            await session.execute(
                text(
                    "SELECT id FROM status_types WHERE domain='booking' AND code='payment_pending'"
                )
            )
        ).scalar_one()
        policy_id = (
            await session.execute(
                text("SELECT id FROM cancellation_policies WHERE name='standard'")
            )
        ).scalar_one()
        now = dt.datetime.now(dt.UTC)
        await session.execute(
            text("""
                INSERT INTO slot_holds (
                    id, user_id, pujari_id, slot_date, slot_time, held_at, expires_at
                ) VALUES (
                    :hid, :uid, NULL, :sd, :st, :now, :now + interval '5 min'
                )
            """),
            {
                "hid": str(hold_id),
                "uid": str(user_id),
                "sd": slot_date,
                "st": slot_time,
                "now": now,
            },
        )
        await session.execute(
            text("""
                INSERT INTO bookings (
                    id, user_id, puja_id, address_id, status_id, cancellation_policy_id,
                    scheduled_date, scheduled_time, duration_minutes, total_amount,
                    amount_due_online, amount_due_offline, booking_fee, payment_mode, hold_id,
                    booking_class, razorpay_order_id, created_at, updated_at
                ) VALUES (
                    :bid, :uid, :pid, :aid, :sid, :cpid,
                    :sd, :st, 90, 2100, 0, 2100, 61, 'booking_fee', :hid,
                    'advance', :oid, :now, :now
                )
            """),
            {
                "bid": str(existing_id),
                "uid": str(user_id),
                "pid": str(puja_id),
                "aid": str(address_id),
                "sid": pending_id,
                "cpid": policy_id,
                "sd": slot_date,
                "st": slot_time,
                "hid": str(hold_id),
                "oid": order_id,
                "now": now,
            },
        )

    async def _fake_order(**_kwargs: object) -> str:
        return "order_should_not_be_called"

    monkeypatch.setattr(razorpay_client, "create_order", _fake_order)

    payload = BookingCreate(
        hold_id=hold_id,
        puja_id=puja_id,
        address_id=address_id,
        payment_mode="booking_fee",
    )

    with pytest.raises(DuplicateBookingSubmit) as exc_info:
        async with session.begin():
            await booking_service.create_booking(session, user_id=user_id, payload=payload)

    dup = exc_info.value.response
    assert dup.idempotent is True
    assert dup.booking_id == existing_id
    assert dup.razorpay_order_id == order_id
    assert dup.amount_due_online == Decimal("0")
    assert dup.booking_fee == FEE
    assert dup.razorpay_amount == FEE
