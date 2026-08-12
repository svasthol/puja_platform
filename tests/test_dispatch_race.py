"""Launch-gate: the double-accept race is resolved by trigger 3 (DB-serialized)."""
from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

pytestmark = pytest.mark.asyncio


async def _make_booking_with_two_offers(session, uniq):
    bid, a1, a2 = uniq.id(), uniq.id(), uniq.id()
    p1, p2 = (
        await session.execute(
            text(
                "SELECT id FROM pujaris WHERE user_id IN "
                "('bbbbbbbb-0000-0000-0000-000000000001', 'bbbbbbbb-0000-0000-0000-000000000002') "
                "ORDER BY user_id"
            )
        )
    ).scalars().all()
    await session.execute(text(
        "INSERT INTO bookings (id,user_id,puja_id,address_id,status_id,cancellation_policy_id,"
        "scheduled_date,scheduled_time,duration_minutes,total_amount,amount_due_online,"
        "amount_due_offline,payment_mode,paid_at,dispatch_mode,booking_class,created_at,updated_at) VALUES (:bid,"
        "'aaaaaaaa-0000-0000-0000-000000000001','11111111-1111-1111-1111-111111111111',"
        "'dddddddd-0000-0000-0000-000000000001',"
        "(SELECT id FROM status_types WHERE domain='booking' AND code='requested'),"
        "(SELECT id FROM cancellation_policies WHERE name='standard'),"
        ":d,'10:00',90,2100,2100,0,'full_online',now(),'broadcast','advance',now(),now())"),
        {"bid": bid, "d": uniq.date})
    for aid, pj in [(a1, p1), (a2, p2)]:
        await session.execute(text(
            "INSERT INTO booking_assignments (id,booking_id,pujari_id,status_id,offered_at,expires_at) "
            "VALUES (:aid,:bid,:pid,"
            "(SELECT id FROM status_types WHERE domain='assignment' AND code='offered'),"
            "now(),now()+interval '2 min')"), {"aid": aid, "bid": bid, "pid": str(pj)})
    await session.commit()
    return bid, a1, a2


async def test_first_accept_wins_second_rejected(session, seed, uniq):
    bid, a1, a2 = await _make_booking_with_two_offers(session, uniq)
    await session.execute(text(
        "UPDATE booking_assignments SET status_id="
        "(SELECT id FROM status_types WHERE domain='assignment' AND code='accepted'),"
        "responded_at=now() WHERE id=:aid"), {"aid": a1})
    await session.commit()
    row = (await session.execute(text(
        "SELECT pujari_id, (SELECT code FROM status_types WHERE id=status_id) "
        "FROM bookings WHERE id=:bid"), {"bid": bid})).first()
    assert row[0] is not None and row[1] == "confirmed"

    with pytest.raises(DBAPIError):
        await session.execute(text(
            "UPDATE booking_assignments SET status_id="
            "(SELECT id FROM status_types WHERE domain='assignment' AND code='accepted'),"
            "responded_at=now() WHERE id=:aid"), {"aid": a2})
        await session.commit()
