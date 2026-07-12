"""Launch-gate: DB errors -> correct HTTP codes (the P0 unwrap fix).

These tests would have caught the original bug where every constraint violation
became a 500 because handlers were registered on raw psycopg types instead of
the SQLAlchemy DBAPIError wrapper.
"""
from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.core.exceptions import map_db_error

pytestmark = pytest.mark.asyncio


async def test_slot_hold_conflict_maps_409(session, seed, uniq):
    async with session.begin():
        await session.execute(text(
            "INSERT INTO slot_holds (id,user_id,pujari_id,slot_date,slot_time,held_at,expires_at) "
            "VALUES (gen_random_uuid(),'aaaaaaaa-0000-0000-0000-000000000001',"
            "'cccccccc-0000-0000-0000-000000000001',:d,'10:00',now(),now()+interval '5 min')"),
            {"d": uniq.date})
    with pytest.raises(DBAPIError) as ei:
        async with session.begin():
            await session.execute(text(
                "INSERT INTO slot_holds (id,user_id,pujari_id,slot_date,slot_time,held_at,expires_at) "
                "VALUES (gen_random_uuid(),'aaaaaaaa-0000-0000-0000-000000000002',"
                "'cccccccc-0000-0000-0000-000000000001',:d,'10:00',now(),now()+interval '5 min')"),
                {"d": uniq.date})
    resp = map_db_error(ei.value.orig, "/v1/slot-holds")
    assert resp.status_code == 409


async def test_accept_cancelled_booking_maps_410(session, seed, uniq):
    bid, aid = uniq.id(), uniq.id()
    async with session.begin():
        await session.execute(text(
            "INSERT INTO bookings (id,user_id,puja_id,address_id,status_id,cancellation_policy_id,"
            "scheduled_date,scheduled_time,duration_minutes,total_amount,amount_due_online,"
            "amount_due_offline,payment_mode,cancelled_at,created_at,updated_at) VALUES (:bid,"
            "'aaaaaaaa-0000-0000-0000-000000000001','11111111-1111-1111-1111-111111111111',"
            "'dddddddd-0000-0000-0000-000000000001',"
            "(SELECT id FROM status_types WHERE domain='booking' AND code='requested'),"
            "(SELECT id FROM cancellation_policies WHERE name='standard'),"
            ":d,'10:00',90,2100,2100,0,'full_online',now(),now(),now())"),
            {"bid": bid, "d": uniq.date})
        await session.execute(text(
            "INSERT INTO booking_assignments (id,booking_id,pujari_id,status_id,offered_at,expires_at) "
            "VALUES (:aid,:bid,'cccccccc-0000-0000-0000-000000000001',"
            "(SELECT id FROM status_types WHERE domain='assignment' AND code='offered'),"
            "now(),now()+interval '2 min')"), {"aid": aid, "bid": bid})
    with pytest.raises(DBAPIError) as ei:
        async with session.begin():
            await session.execute(text(
                "UPDATE booking_assignments SET status_id="
                "(SELECT id FROM status_types WHERE domain='assignment' AND code='accepted'),"
                "responded_at=now() WHERE id=:aid"), {"aid": aid})
    resp = map_db_error(ei.value.orig, "/v1/offers/x/accept")
    assert resp.status_code == 410
