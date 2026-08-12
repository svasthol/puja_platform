"""Dispatch supply gate — no pujari_pricing / eligibility => 422 at checkout."""
from __future__ import annotations

import datetime as dt
import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import text

from app.schemas.booking import BookingCreate
from app.services import booking_service, razorpay_client
from app.services.dispatch_supply import NO_DISPATCH_SUPPLY_CODE, assert_dispatch_supply


async def _insert_hold(session, *, user_id, slot_date, slot_time, now) -> uuid.UUID:
    hold_id = uuid.uuid4()
    await session.execute(
        text(
            """
            INSERT INTO slot_holds (
                id, user_id, pujari_id, slot_date, slot_time, held_at, expires_at
            ) VALUES (
                :hid, :uid, NULL, :sd, :st, :now, :now + interval '5 min'
            )
            """
        ),
        {
            "hid": str(hold_id),
            "uid": str(user_id),
            "sd": slot_date,
            "st": slot_time,
            "now": now,
        },
    )
    return hold_id


@pytest.mark.asyncio
async def test_assert_dispatch_supply_blocks_puja_without_pricing(session, seed, uniq, monkeypatch):
    """Active puja with zero pujari_pricing rows must not reach Razorpay."""
    puja_id = uuid.uuid4()
    await session.execute(
        text(
            """
            INSERT INTO pujas (
                id, category_id, name, slug, duration_minutes, default_price,
                display_order, is_active, created_at, updated_at
            )
            SELECT :id, c.id, :name, :slug, 90, 1500, 9999, true, now(), now()
            FROM puja_categories c
            WHERE c.is_active
            LIMIT 1
            """
        ),
        {
            "id": str(puja_id),
            "name": f"NoSupply-{uniq.id()[:8]}",
            "slug": f"nosupply-{uniq.id()[:8]}",
        },
    )
    user_id = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001")
    addr_id = uuid.UUID("dddddddd-0000-0000-0000-000000000001")
    now = dt.datetime.now(dt.UTC)
    slot_date = (now + dt.timedelta(days=2)).date()
    slot_time = dt.time(14, 0)
    hold_id = await _insert_hold(
        session, user_id=user_id, slot_date=slot_date, slot_time=slot_time, now=now
    )

    with pytest.raises(HTTPException) as exc:
        await assert_dispatch_supply(
            session,
            puja_id=puja_id,
            scheduled_date=slot_date,
            scheduled_time=slot_time,
            duration_minutes=90,
        )
    assert exc.value.status_code == 422
    assert exc.value.detail["code"] == NO_DISPATCH_SUPPLY_CODE

    monkeypatch.setattr(
        razorpay_client,
        "create_order",
        lambda *a, **k: {"id": "order_test", "amount": 5100},
    )
    payload = BookingCreate(
        hold_id=hold_id,
        puja_id=puja_id,
        address_id=addr_id,
        payment_mode="advance_balance",
        addon_ids=[],
    )
    with pytest.raises(HTTPException) as exc2:
        await booking_service.create_booking(session, user_id=user_id, payload=payload)
    assert exc2.value.status_code == 422
    assert exc2.value.detail["code"] == NO_DISPATCH_SUPPLY_CODE


@pytest.mark.asyncio
async def test_count_dispatch_eligible_positive_for_seed_puja(session, seed):
    """Seed Test Puja has verified pujari_pricing — supply check finds candidates."""
    from app.services.dispatch_supply import count_dispatch_eligible_for_slot

    puja_id = uuid.UUID("11111111-1111-1111-1111-111111111111")
    now = dt.datetime.now(dt.UTC)
    slot_date = (now + dt.timedelta(days=3)).date()
    n = await count_dispatch_eligible_for_slot(
        session,
        puja_id=puja_id,
        scheduled_date=slot_date,
        scheduled_time=dt.time(10, 0),
        duration_minutes=90,
    )
    assert n >= 1
