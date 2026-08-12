"""Phase 1 tests — addresses/geom, availability, booking list keyset, promo cap.

Same integration style as Phase 0: the DB enforces the invariants, so tests hit
live PostgreSQL (conftest DATABASE_URL).
"""
from __future__ import annotations

import datetime as _dt

import pytest
from sqlalchemy import text

from app.schemas.common import decode_cursor, encode_cursor

CUSTOMER = "aaaaaaaa-0000-0000-0000-000000000001"
PUJARI = "cccccccc-0000-0000-0000-000000000001"
PUJA = "11111111-1111-1111-1111-111111111111"


def test_cursor_roundtrip():
    cur = encode_cursor("2026-07-12T10:00:00+00:00", "abc-id")
    assert decode_cursor(cur, 2) == ["2026-07-12T10:00:00+00:00", "abc-id"]


@pytest.mark.asyncio
async def test_address_insert_trigger_sets_geom(session, seed, uniq):
    """C-ADDR invariant: writing lat/lng populates geom via trg_addresses_geom_sync."""
    area_id = (
        await session.execute(
            text(
                "SELECT id FROM service_areas WHERE city='Hyderabad' AND zone_name='Test Zone'"
            )
        )
    ).scalar_one()
    aid = uniq.id()
    await session.execute(
        text(
            "INSERT INTO addresses (id, user_id, line1, city, latitude, longitude, service_area_id) "
            "VALUES (:id, :uid, 'L1', 'Hyd', 17.40, 78.40, :aid)"
        ),
        {"id": aid, "uid": CUSTOMER, "aid": area_id},
    )
    await session.commit()
    has_geom = (
        await session.execute(
            text("SELECT geom IS NOT NULL FROM addresses WHERE id = :id"), {"id": aid}
        )
    ).scalar_one()
    assert has_geom is True

    # PUT with new coordinates recomputes geom (trigger fires on UPDATE too)
    await session.execute(
        text("UPDATE addresses SET latitude = 17.50, longitude = 78.50 WHERE id = :id"),
        {"id": aid},
    )
    await session.commit()
    lng = (
        await session.execute(
            text("SELECT ST_X(geom::geometry) FROM addresses WHERE id = :id"), {"id": aid}
        )
    ).scalar_one()
    assert abs(float(lng) - 78.50) < 1e-6


@pytest.mark.asyncio
async def test_availability_replace_all(session, seed):
    """B-AVAIL: replace-all delete+insert leaves exactly the new windows."""
    await session.execute(
        text("DELETE FROM pujari_availability WHERE pujari_id = :pid"), {"pid": PUJARI}
    )
    for dow, st, et in [(0, "09:00", "12:00"), (0, "14:00", "18:00"), (5, "08:00", "20:00")]:
        await session.execute(
            text(
                "INSERT INTO pujari_availability (pujari_id, day_of_week, start_time, end_time) "
                "VALUES (:pid, :dow, :st, :et)"
            ),
            {"pid": PUJARI, "dow": dow, "st": st, "et": et},
        )
    await session.commit()
    n = (
        await session.execute(
            text("SELECT count(*) FROM pujari_availability WHERE pujari_id = :pid"),
            {"pid": PUJARI},
        )
    ).scalar_one()
    assert n == 3


@pytest.mark.asyncio
async def test_booking_list_keyset_newest_first(session, seed, uniq):
    """C-LIST: (created_at, id) keyset returns strictly older rows on page 2."""
    ids = []
    base = _dt.datetime.now(_dt.UTC)
    for i in range(3):
        bid = uniq.id()
        ids.append(bid)
        await session.execute(
            text(
                """
                INSERT INTO bookings (
                    id, user_id, puja_id, address_id, status_id, cancellation_policy_id,
                    scheduled_date, scheduled_time, duration_minutes, total_amount,
                    amount_due_online, amount_due_offline, payment_mode, paid_at,
                    dispatch_mode, created_at, updated_at
                ) VALUES (
                    :bid, :uid, :puja, 'dddddddd-0000-0000-0000-000000000001',
                    (SELECT id FROM status_types WHERE domain='booking' AND code='requested'),
                    (SELECT id FROM cancellation_policies WHERE name='standard'),
                    :d, :t, 90, 2100, 2100, 0, 'full_online', now(),
                    'broadcast', :ca, :ca
                )
                """
            ),
            {
                "bid": bid,
                "uid": CUSTOMER,
                "puja": PUJA,
                "d": uniq.date,
                "t": f"{10 + i}:00",
                "ca": base + _dt.timedelta(seconds=i),
            },
        )
    await session.commit()

    page1 = (
        await session.execute(
            text(
                "SELECT id, created_at FROM bookings WHERE user_id = :uid "
                "ORDER BY created_at DESC, id DESC LIMIT 2"
            ),
            {"uid": CUSTOMER},
        )
    ).mappings().all()
    assert len(page1) == 2
    last = page1[-1]
    page2 = (
        await session.execute(
            text(
                "SELECT id, created_at FROM bookings WHERE user_id = :uid "
                "AND (created_at, id) < (:c_dt, :c_id) "
                "ORDER BY created_at DESC, id DESC LIMIT 2"
            ),
            {"uid": CUSTOMER, "c_dt": last["created_at"], "c_id": last["id"]},
        )
    ).mappings().all()
    page1_keys = {str(r["id"]) for r in page1}
    assert all(str(r["id"]) not in page1_keys for r in page2)
    assert all(
        (r["created_at"], str(r["id"])) < (last["created_at"], str(last["id"]))
        for r in page2
    )


@pytest.mark.asyncio
async def test_promo_usage_counter_blocks_over_limit(session, seed, uniq):
    """C-PROMO: guarded upsert returns a row up to max_uses, then no row."""
    pid = uniq.id()
    await session.execute(
        text(
            "INSERT INTO promo_codes (id, code, discount_pct, max_uses_per_user, "
            "valid_from, valid_until, is_active) "
            "VALUES (:id, :code, 10, 1, now() - interval '1 day', now() + interval '1 day', true)"
        ),
        {"id": pid, "code": f"T{uniq.id()[:8]}"},
    )
    await session.commit()

    upsert = text(
        "INSERT INTO promo_usage_counters (promo_code_id, user_id, redemption_count) "
        "VALUES (:pid, :uid, 1) "
        "ON CONFLICT (promo_code_id, user_id) DO UPDATE "
        "SET redemption_count = promo_usage_counters.redemption_count + 1 "
        "WHERE promo_usage_counters.redemption_count < :max "
        "RETURNING redemption_count"
    )
    first = (
        await session.execute(upsert, {"pid": pid, "uid": CUSTOMER, "max": 1})
    ).scalar_one_or_none()
    assert first == 1
    await session.commit()

    second = (
        await session.execute(upsert, {"pid": pid, "uid": CUSTOMER, "max": 1})
    ).scalar_one_or_none()
    assert second is None
    await session.commit()
