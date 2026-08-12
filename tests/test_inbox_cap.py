"""DV2-INBOX-CAP — G1 live advance-offer cap at broadcast build (§21.6.G)."""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from app.services.dispatch_launch import filter_candidates_inbox_cap
from app.workers.dispatch import broadcast_booking
from app.workers.sweep import get_connection

CUSTOMER = "aaaaaaaa-0000-0000-0000-000000000001"
PUJARI_USER1 = "bbbbbbbb-0000-0000-0000-000000000001"
PUJARI_USER2 = "bbbbbbbb-0000-0000-0000-000000000002"
PUJA = "11111111-1111-1111-1111-111111111111"
ADDRESS = "dddddddd-0000-0000-0000-000000000001"


async def _clear_pujari_live_offers(session, *pujari_ids: str) -> None:
    """Resolve stale live offers so inbox-cap tests start from a clean slate."""
    if not pujari_ids:
        return
    await session.execute(
        text(
            """
            UPDATE booking_assignments ba
            SET responded_at = now(),
                status_id = (
                    SELECT id FROM status_types
                    WHERE domain = 'assignment' AND code = 'expired'
                )
            WHERE ba.pujari_id = ANY(:pids)
              AND ba.responded_at IS NULL
            """
        ),
        {"pids": list(pujari_ids)},
    )


async def _pujari_ids(session) -> tuple[str, str]:
    p1 = (
        await session.execute(
            text("SELECT id::text FROM pujaris WHERE user_id = :u"),
            {"u": PUJARI_USER1},
        )
    ).scalar_one()
    p2 = (
        await session.execute(
            text("SELECT id::text FROM pujaris WHERE user_id = :u"),
            {"u": PUJARI_USER2},
        )
    ).scalar_one()
    return p1, p2


async def _require_migration_014(session) -> None:
    row = (
        await session.execute(
            text(
                """
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'bookings'
                  AND column_name = 'booking_class'
                """
            )
        )
    ).scalar_one_or_none()
    if row is None:
        pytest.skip("migration_014 not applied — run: python scripts/apply_migration_014.py")


def _unique_slot_time(uniq) -> str:
    h = (int(uniq.id().replace("-", "")[:4], 16) % 12) + 8
    m = int(uniq.id().replace("-", "")[4:8], 16) % 60
    return f"{h:02d}:{m:02d}:00"


async def _ensure_pujari_dispatch_ready(session) -> tuple[str, str]:
    """Pricing, service area, and availability required for launch eligibility."""
    p1, p2 = await _pujari_ids(session)
    await session.execute(
        text(
            """
            INSERT INTO pujari_pricing (id, pujari_id, puja_id, base_price)
            SELECT gen_random_uuid(), p.id, :puja, 2100
            FROM pujaris p
            WHERE p.id IN (:p1, :p2)
            ON CONFLICT (pujari_id, puja_id) DO NOTHING
            """
        ),
        {"puja": PUJA, "p1": p1, "p2": p2},
    )
    await session.execute(
        text(
            """
            INSERT INTO pujari_service_areas (pujari_id, service_area_id)
            SELECT p.id, sa.id
            FROM pujaris p
            CROSS JOIN service_areas sa
            WHERE p.id IN (:p1, :p2)
              AND sa.city = 'Hyderabad' AND sa.zone_name = 'Test Zone'
            ON CONFLICT DO NOTHING
            """
        ),
        {"p1": p1, "p2": p2},
    )
    for dow in range(7):
        await session.execute(
            text(
                """
                INSERT INTO pujari_availability (id, pujari_id, day_of_week, start_time, end_time)
                SELECT gen_random_uuid(), p.id, :dow, '06:00', '23:59'
                FROM pujaris p
                WHERE p.id IN (:p1, :p2)
                  AND NOT EXISTS (
                      SELECT 1 FROM pujari_availability pa
                      WHERE pa.pujari_id = p.id AND pa.day_of_week = :dow
                  )
                """
            ),
            {"p1": p1, "p2": p2, "dow": dow},
        )
    return p1, p2


async def _insert_advance_live_offer(
    session,
    *,
    pujari_id: str,
    slot_date: str,
    slot_time: str,
) -> str:
    """Booking + unresolved offered assignment on an advance booking."""
    bid = str(uuid.uuid4())
    await session.execute(
        text(
            """
            INSERT INTO bookings (
                id, user_id, puja_id, address_id, status_id, cancellation_policy_id,
                scheduled_date, scheduled_time, duration_minutes, total_amount,
                amount_due_online, amount_due_offline, payment_mode, paid_at,
                dispatch_mode, booking_class, created_at, updated_at
            ) VALUES (
                :bid, :uid, :puja, :addr,
                (SELECT id FROM status_types WHERE domain='booking' AND code='requested'),
                (SELECT id FROM cancellation_policies WHERE name='standard'),
                :sd, CAST(:st AS time), 90, 2100, 2100, 0, 'full_online', now(),
                'broadcast', 'advance', now(), now()
            )
            """
        ),
        {
            "bid": bid,
            "uid": CUSTOMER,
            "puja": PUJA,
            "addr": ADDRESS,
            "sd": slot_date,
            "st": slot_time,
        },
    )
    await session.execute(
        text(
            """
            INSERT INTO booking_assignments (
                id, booking_id, pujari_id, status_id, offered_at, expires_at
            ) VALUES (
                gen_random_uuid(), :bid, :pid,
                (SELECT id FROM status_types WHERE domain='assignment' AND code='offered'),
                now(), now() + interval '24 hours'
            )
            """
        ),
        {"bid": bid, "pid": pujari_id},
    )
    return bid


async def _insert_broadcast_target(
    session,
    *,
    booking_id: str,
    slot_date: str,
    slot_time: str,
    booking_class: str,
) -> None:
    await session.execute(
        text(
            """
            INSERT INTO bookings (
                id, user_id, puja_id, address_id, status_id, cancellation_policy_id,
                scheduled_date, scheduled_time, duration_minutes, total_amount,
                amount_due_online, amount_due_offline, payment_mode, paid_at,
                dispatch_mode, booking_class, created_at, updated_at
            ) VALUES (
                :bid, :uid, :puja, :addr,
                (SELECT id FROM status_types WHERE domain='booking' AND code='requested'),
                (SELECT id FROM cancellation_policies WHERE name='standard'),
                :sd, CAST(:st AS time), 90, 2100, 2100, 0, 'full_online', now(),
                'broadcast', :cls, now(), now()
            )
            """
        ),
        {
            "bid": booking_id,
            "uid": CUSTOMER,
            "puja": PUJA,
            "addr": ADDRESS,
            "sd": slot_date,
            "st": slot_time,
            "cls": booking_class,
        },
    )


def _set_presence(*pujari_ids: str) -> None:
    import redis as redis_lib

    from app.core.config import get_settings

    r = redis_lib.from_url(str(get_settings().REDIS_URL))
    for pid in pujari_ids:
        r.set(f"presence:{pid}", "1", ex=120)


def _clear_presence(*pujari_ids: str) -> None:
    import redis as redis_lib

    from app.core.config import get_settings

    r = redis_lib.from_url(str(get_settings().REDIS_URL))
    for pid in pujari_ids:
        r.delete(f"presence:{pid}")


def _clear_pujari_live_offers_sync(cur, *pujari_ids: str) -> None:
    if not pujari_ids:
        return
    cur.execute(
        """
        UPDATE booking_assignments ba
        SET responded_at = now(),
            status_id = (
                SELECT id FROM status_types
                WHERE domain = 'assignment' AND code = 'expired'
            )
        WHERE ba.pujari_id = ANY(%s)
          AND ba.responded_at IS NULL
        """,
        (list(pujari_ids),),
    )


def test_filter_candidates_inbox_cap_excludes_at_limit(uniq):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id FROM pujaris
                WHERE user_id IN (%s, %s)
                ORDER BY user_id
                """,
                (PUJARI_USER1, PUJARI_USER2),
            )
            rows = cur.fetchall()
            if len(rows) < 2:
                pytest.skip("seed pujaris missing")
            p1, p2 = str(rows[0][0]), str(rows[1][0])
            p3 = str(uuid.uuid4())
            cap = 2
            _clear_pujari_live_offers_sync(cur, p1, p2)
            cur.execute(
                "SELECT id FROM status_types WHERE domain='assignment' AND code='offered'"
            )
            offered_id = cur.fetchone()[0]
            cur.execute(
                "SELECT id FROM cancellation_policies WHERE name='standard' LIMIT 1"
            )
            policy_id = cur.fetchone()[0]
            cur.execute(
                "SELECT id FROM status_types WHERE domain='booking' AND code='requested'"
            )
            requested_id = cur.fetchone()[0]

            for i, pid in enumerate((p1, p1, p2)):
                bid = str(uuid.uuid4())
                cur.execute(
                    """
                    INSERT INTO bookings (
                        id, user_id, puja_id, address_id, status_id, cancellation_policy_id,
                        scheduled_date, scheduled_time, duration_minutes, total_amount,
                        amount_due_online, amount_due_offline, payment_mode, paid_at,
                        dispatch_mode, booking_class, created_at, updated_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s,
                        %s, %s::time, 90, 2100, 2100, 0, 'full_online', now(),
                        'broadcast', 'advance', now(), now()
                    )
                    """,
                    (
                        bid,
                        CUSTOMER,
                        PUJA,
                        ADDRESS,
                        requested_id,
                        policy_id,
                        uniq.date,
                        f"{10 + i:02d}:00:00",
                    ),
                )
                cur.execute(
                    """
                    INSERT INTO booking_assignments (
                        id, booking_id, pujari_id, status_id, offered_at, expires_at
                    ) VALUES (gen_random_uuid(), %s, %s, %s, now(), now() + interval '24 hours')
                    """,
                    (bid, pid, offered_id),
                )
            conn.commit()

            filtered, capped = filter_candidates_inbox_cap(cur, [p1, p2, p3], cap)
            assert capped == 1
            assert p1 not in filtered
            assert p2 in filtered
            assert p3 in filtered
    finally:
        conn.close()


@pytest.mark.asyncio
async def test_advance_broadcast_skips_inbox_capped_pujari(session, seed, uniq):
    """At cap, advance broadcast must not insert another live offer for that pujari."""
    await _require_migration_014(session)
    pujari1, pujari2 = await _pujari_ids(session)
    await _clear_pujari_live_offers(session, pujari1, pujari2)
    pujari1, pujari2 = await _ensure_pujari_dispatch_ready(session)
    await session.execute(
        text(
            """
            INSERT INTO platform_settings (key, value_json) VALUES
            ('max_live_advance_offers_per_pujari', '2'::jsonb)
            ON CONFLICT (key) DO UPDATE SET value_json = '2'::jsonb
            """
        )
    )

    slot_time = _unique_slot_time(uniq)
    await _insert_advance_live_offer(
        session, pujari_id=pujari1, slot_date=uniq.date, slot_time="09:00:00"
    )
    await _insert_advance_live_offer(
        session, pujari_id=pujari1, slot_date=uniq.date2, slot_time="09:30:00"
    )

    target_id = uniq.id()
    await _insert_broadcast_target(
        session,
        booking_id=target_id,
        slot_date=uniq.date2,
        slot_time=slot_time,
        booking_class="advance",
    )
    await session.commit()

    _clear_presence(pujari1, pujari2)
    _set_presence(pujari1, pujari2)
    broadcast_booking(target_id)

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT pujari_id::text FROM booking_assignments WHERE booking_id = %s",
                (target_id,),
            )
            assigned = [row[0] for row in cur.fetchall()]
    finally:
        conn.close()

    assert pujari1 not in assigned
    assert len(assigned) >= 1


@pytest.mark.asyncio
async def test_instant_broadcast_ignores_inbox_cap(session, seed, uniq):
    """Instant offers are never suppressed by the advance inbox cap."""
    await _require_migration_014(session)
    pujari1, pujari2 = await _pujari_ids(session)
    await _clear_pujari_live_offers(session, pujari1, pujari2)
    pujari1, pujari2 = await _ensure_pujari_dispatch_ready(session)
    await session.execute(
        text(
            """
            INSERT INTO platform_settings (key, value_json) VALUES
            ('max_live_advance_offers_per_pujari', '2'::jsonb)
            ON CONFLICT (key) DO UPDATE SET value_json = '2'::jsonb
            """
        )
    )

    await _insert_advance_live_offer(
        session, pujari_id=pujari1, slot_date=uniq.date, slot_time="08:00:00"
    )
    await _insert_advance_live_offer(
        session, pujari_id=pujari1, slot_date=uniq.date2, slot_time="08:30:00"
    )

    target_id = uniq.id()
    await _insert_broadcast_target(
        session,
        booking_id=target_id,
        slot_date=uniq.date2,
        slot_time=_unique_slot_time(uniq),
        booking_class="instant",
    )
    await session.commit()

    _clear_presence(pujari1, pujari2)
    _set_presence(pujari1)
    broadcast_booking(target_id)

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT count(*) FROM booking_assignments
                WHERE booking_id = %s AND pujari_id = %s
                """,
                (target_id, pujari1),
            )
            count = cur.fetchone()[0]
    finally:
        conn.close()

    assert count == 1
