"""Razorpay webhook booking_id resolution (payment notes vs order_id lookup)."""
from __future__ import annotations

import datetime as dt
import uuid

import pytest
from sqlalchemy import text

from app.api.v1.endpoints import webhooks as webhooks_ep


@pytest.mark.asyncio
async def test_resolve_booking_id_from_razorpay_order_id(session, seed, uniq):
    booking_id = uuid.uuid4()
    order_id = f"order_{uniq.id()}"
    user_id = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001")
    puja_id = uuid.UUID("11111111-1111-1111-1111-111111111111")
    address_id = uuid.UUID("dddddddd-0000-0000-0000-000000000001")
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
        text(
            """
            INSERT INTO bookings (
                id, user_id, puja_id, address_id, status_id, cancellation_policy_id,
                scheduled_date, scheduled_time, duration_minutes, total_amount,
                amount_due_online, amount_due_offline, payment_mode, booking_class,
                razorpay_order_id, created_at, updated_at
            ) VALUES (
                :bid, :uid, :pid, :aid, :sid, :cpid,
                :sd, CAST(:st AS time), 90, 2100, 2100, 0, 'full_online', 'advance',
                :oid, :now, :now
            )
            """
        ),
        {
            "bid": str(booking_id),
            "uid": str(user_id),
            "pid": str(puja_id),
            "aid": str(address_id),
            "sid": pending_id,
            "cpid": policy_id,
            "sd": dt.date.fromisoformat(uniq.date),
            "st": "10:00:00",
            "oid": order_id,
            "now": now,
        },
    )
    await session.commit()

    payload = {
        "event": "payment.captured",
        "payload": {
            "payment": {
                "entity": {
                    "id": f"pay_{uniq.id()}",
                    "order_id": order_id,
                    "amount": 210000,
                    "notes": {},
                }
            }
        },
    }

    resolved = await webhooks_ep._resolve_booking_id(session, payload)
    assert resolved == booking_id
