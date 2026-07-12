"""Launch-gate: sweep step 2 releases ONLY the hold linked to the abandoned booking."""
from __future__ import annotations

import pytest
from sqlalchemy import text

from app.workers.sweep import abandon_stale_payment_pending, get_connection

pytestmark = pytest.mark.asyncio


async def test_only_linked_hold_released(session, seed, uniq):
    h1, h2, bk = uniq.id(), uniq.id(), uniq.id()
    async with session.begin():
        await session.execute(text(
            "INSERT INTO slot_holds (id,user_id,pujari_id,slot_date,slot_time,held_at,expires_at) VALUES "
            "(:h1,'aaaaaaaa-0000-0000-0000-000000000001','cccccccc-0000-0000-0000-000000000001',"
            ":d1,'09:00',now(),now()+interval '15 min'),"
            "(:h2,'aaaaaaaa-0000-0000-0000-000000000001','cccccccc-0000-0000-0000-000000000002',"
            ":d2,'09:00',now(),now()+interval '15 min')"),
            {"h1": h1, "h2": h2, "d1": uniq.date, "d2": uniq.date2})
        await session.execute(text(
            "INSERT INTO bookings (id,user_id,puja_id,address_id,status_id,cancellation_policy_id,"
            "scheduled_date,scheduled_time,duration_minutes,total_amount,amount_due_online,"
            "amount_due_offline,payment_mode,hold_id,created_at,updated_at) VALUES (:bk,"
            "'aaaaaaaa-0000-0000-0000-000000000001','11111111-1111-1111-1111-111111111111',"
            "'dddddddd-0000-0000-0000-000000000001',"
            "(SELECT id FROM status_types WHERE domain='booking' AND code='payment_pending'),"
            "(SELECT id FROM cancellation_policies WHERE name='standard'),:d1,'09:00',90,"
            "2100,2100,0,'full_online',:h1, now()-interval '20 min', now()-interval '20 min')"),
            {"bk": bk, "h1": h1, "d1": uniq.date})

    conn = get_connection()
    try:
        abandon_stale_payment_pending(conn)
    finally:
        conn.close()

    async with session.begin():
        rows = dict((str(r[0]), r[1]) for r in (await session.execute(text(
            "SELECT id, released_at IS NULL FROM slot_holds WHERE id IN (:h1,:h2)"),
            {"h1": h1, "h2": h2})).all())
    assert rows[h1] is False   # linked hold released
    assert rows[h2] is True    # unrelated hold survives
