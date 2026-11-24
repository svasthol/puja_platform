"""GET /v1/offers — partner_net_amount (Track C+)."""
from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.api.v1.endpoints import offers as offers_ep
from app.core.dependencies import Principal

CUSTOMER = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001")
PUJARI_USER = uuid.UUID("bbbbbbbb-0000-0000-0000-000000000001")
PUJA = "11111111-1111-1111-1111-111111111111"
ADDRESS = "dddddddd-0000-0000-0000-000000000001"
FEE = Decimal("61")


def _pujari() -> Principal:
    return Principal(user_id=PUJARI_USER, app_context="pujari", roles=())


def _unique_slot_time(uniq) -> str:
    h = (int(uniq.id().replace("-", "")[:4], 16) % 12) + 8
    m = int(uniq.id().replace("-", "")[4:8], 16) % 60
    return f"{h:02d}:{m:02d}:00"


@pytest.mark.asyncio
async def test_list_offers_partner_net_booking_fee_plus_offline(session, seed, uniq):
    """Launch mode: net from split (often 0 on fee) + amount_due_offline."""
    bid, aid = uniq.id(), uniq.id()
    slot_time = _unique_slot_time(uniq)
    pujari_id = (
        await session.execute(
            text("SELECT id::text FROM pujaris WHERE user_id = :u"),
            {"u": str(PUJARI_USER)},
        )
    ).scalar_one()
    total = Decimal("2100.00")
    offline = total
    await session.execute(
        text(
            """
            INSERT INTO bookings (
                id, user_id, puja_id, address_id, status_id, cancellation_policy_id,
                scheduled_date, scheduled_time, duration_minutes, total_amount,
                amount_due_online, amount_due_offline, booking_fee, payment_mode, paid_at,
                dispatch_mode, booking_class, created_at, updated_at
            ) VALUES (
                :bid, :uid, :puja, :addr,
                (SELECT id FROM status_types WHERE domain='booking' AND code='requested'),
                (SELECT id FROM cancellation_policies WHERE name='standard'),
                :d, CAST(:t AS time), 90, :total, 0, :offline, :fee, 'booking_fee', now(),
                'broadcast', 'advance', now(), now()
            )
            """
        ),
        {
            "bid": bid,
            "uid": str(CUSTOMER),
            "puja": PUJA,
            "addr": ADDRESS,
            "d": uniq.date,
            "t": slot_time,
            "total": str(total),
            "offline": str(offline),
            "fee": str(FEE),
        },
    )
    pay_id = uniq.id()
    await session.execute(
        text(
            """
            INSERT INTO payments (id, booking_id, amount, idempotency_key, status, created_at)
            VALUES (:pid, :bid, :amt, :idem, 'success', now())
            """
        ),
        {"pid": pay_id, "bid": bid, "amt": str(FEE), "idem": f"idem_{uniq.id()[:12]}"},
    )
    await session.execute(
        text(
            """
            INSERT INTO payment_splits (id, payment_id, platform_fee, gst_amount)
            VALUES (gen_random_uuid(), :pid, :fee, 0)
            """
        ),
        {"pid": pay_id, "fee": str(FEE)},
    )
    await session.execute(
        text(
            """
            INSERT INTO booking_assignments (
                id, booking_id, pujari_id, status_id, offered_at, expires_at
            ) VALUES (
                :aid, :bid, :pid,
                (SELECT id FROM status_types WHERE domain='assignment' AND code='offered'),
                now(), now() + interval '2 hours'
            )
            """
        ),
        {"aid": aid, "bid": bid, "pid": pujari_id},
    )
    await session.commit()

    result = await offers_ep.list_offers(limit=50, p=_pujari(), db=session)
    offer = next(o for o in result.offers if str(o.booking_id) == bid)
    assert offer.partner_net_amount == offline
    assert offer.amount_due_offline == offline