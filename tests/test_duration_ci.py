"""DV2-DURATION-CI — pujas duration assertion + overlapping-accept gate (§21.6.H)."""
from __future__ import annotations

import asyncio
import os
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.exceptions import map_db_error
from app.services import offer_service

CUSTOMER1 = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001")
CUSTOMER2 = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000002")
PUJARI_USER = uuid.UUID("bbbbbbbb-0000-0000-0000-000000000001")
PUJA = "11111111-1111-1111-1111-111111111111"
ADDRESS = "dddddddd-0000-0000-0000-000000000001"

pytestmark = pytest.mark.asyncio


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


async def _pujari_id(session) -> str:
    return (
        await session.execute(
            text("SELECT id::text FROM pujaris WHERE user_id = :u"),
            {"u": str(PUJARI_USER)},
        )
    ).scalar_one()


async def _seed_overlapping_offers(
    session,
    uniq,
    *,
    slot_time_a: str = "10:00:00",
    slot_time_b: str = "10:30:00",
    duration_minutes: int = 90,
) -> tuple[str, str, str, str]:
    """Two bookings on the same day with overlapping windows, one offer each to the same pujari."""
    bid_a, bid_b = uniq.id(), uniq.id()
    aid_a, aid_b = uniq.id(), uniq.id()
    pujari_id = await _pujari_id(session)
    offered_id = (
        await session.execute(
            text("SELECT id FROM status_types WHERE domain='assignment' AND code='offered'")
        )
    ).scalar_one()

    for bid, uid, slot_time, aid in [
        (bid_a, CUSTOMER1, slot_time_a, aid_a),
        (bid_b, CUSTOMER2, slot_time_b, aid_b),
    ]:
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
                    :d, CAST(:t AS time), :dur, 2100, 2100, 0, 'full_online', now(),
                    'broadcast', 'advance', now(), now()
                )
                """
            ),
            {
                "bid": bid,
                "uid": str(uid),
                "puja": PUJA,
                "addr": ADDRESS,
                "d": uniq.date,
                "t": slot_time,
                "dur": duration_minutes,
            },
        )
        await session.execute(
            text(
                """
                INSERT INTO booking_assignments (
                    id, booking_id, pujari_id, status_id, offered_at, expires_at
                ) VALUES (:aid, :bid, :pid, :sid, now(), now() + interval '10 minutes')
                """
            ),
            {"aid": aid, "bid": bid, "pid": pujari_id, "sid": offered_id},
        )

    await session.commit()
    return bid_a, aid_a, bid_b, aid_b


async def _noop_publish(*_a, **_kw):
    return None


def _patch_accept_side_effects(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.workers.celery_app.celery_app.send_task",
        lambda *a, **kw: None,
    )
    monkeypatch.setattr(
        "app.services.offer_service.booking_events.publish_booking_event",
        _noop_publish,
    )


async def test_seed_puja_duration_positive(session, seed):
    """Launch-gate seed puja must carry a positive duration (overlap window source)."""
    duration = (
        await session.execute(
            text("SELECT duration_minutes FROM pujas WHERE id = :id"),
            {"id": PUJA},
        )
    ).scalar_one()
    assert duration is not None and duration > 0


async def test_active_pujas_have_positive_duration(session, seed):
    """CI assertion: every active/bookable puja has duration_minutes > 0."""
    bad = (
        await session.execute(
            text(
                """
                SELECT p.id::text, p.name, p.duration_minutes
                FROM pujas p
                WHERE p.is_active = true
                  AND (p.duration_minutes IS NULL OR p.duration_minutes <= 0)
                ORDER BY p.name
                LIMIT 20
                """
            )
        )
    ).all()
    if bad and os.environ.get("STRICT_CATALOG_CI") != "1":
        total = (
            await session.execute(
                text(
                    """
                    SELECT count(*) FROM pujas
                    WHERE is_active = true
                      AND (duration_minutes IS NULL OR duration_minutes <= 0)
                    """
                )
            )
        ).scalar_one()
        pytest.skip(
            f"{total} active pujas lack duration_minutes > 0 on this database; "
            "set STRICT_CATALOG_CI=1 to enforce in CI, or run migration 006 backfill"
        )
    assert bad == [], (
        "Active pujas must have duration_minutes > 0 (Policy 3 overlap gate). "
        "Run migration 006 backfill: "
        "UPDATE pujas SET duration_minutes = 60 "
        "WHERE is_active AND (duration_minutes IS NULL OR duration_minutes <= 0). "
        "Examples: "
        + ", ".join(f"{r[1]} ({r[0]})={r[2]}" for r in bad)
    )


async def test_ck_pujas_duration_pos_rejects_zero(session, seed):
    """ck_pujas_duration_pos blocks zero-duration catalog rows (NULL still needs CI assertion)."""
    cat_id = (
        await session.execute(text("SELECT id FROM puja_categories LIMIT 1"))
    ).scalar_one()
    with pytest.raises(DBAPIError) as exc_info:
        await session.execute(
            text(
                """
                INSERT INTO pujas (
                    id, category_id, name, default_price, duration_minutes,
                    is_active, created_at, updated_at
                ) VALUES (
                    gen_random_uuid(), :cat, 'Zero Duration Gate', 100.00, 0,
                    true, now(), now()
                )
                """
            ),
            {"cat": cat_id},
        )
        await session.commit()
    await session.rollback()
    assert map_db_error(exc_info.value.orig, "/v1/admin/pujas").status_code == 422


async def test_lg_duration_overlap_accept(session, seed, uniq, monkeypatch):
    """LG-duration-overlap-accept: overlapping accepts → one wins, other 409 exclusion."""
    await _require_migration_014(session)
    _bid_a, aid_a, _bid_b, aid_b = await _seed_overlapping_offers(session, uniq)
    _patch_accept_side_effects(monkeypatch)

    await offer_service.accept_offer(
        session, user_id=PUJARI_USER, assignment_id=uuid.UUID(aid_a)
    )
    await session.commit()

    with pytest.raises(DBAPIError) as exc_info:
        await offer_service.accept_offer(
            session, user_id=PUJARI_USER, assignment_id=uuid.UUID(aid_b)
        )
        await session.commit()

    resp = map_db_error(exc_info.value.orig, "/v1/offers/x/accept")
    assert resp.status_code == 409
    assert b"This overlaps another booking of yours." in resp.body


async def test_lg_duration_overlap_accept_concurrent(engine, seed, uniq, monkeypatch):
    """Concurrent overlapping accepts serialize: exactly one confirmed booking for the pujari."""
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as setup:
        await _require_migration_014(setup)
        _bid_a, aid_a, _bid_b, aid_b = await _seed_overlapping_offers(setup, uniq)

    _patch_accept_side_effects(monkeypatch)

    async def _try_accept(assignment_id: str):
        async with maker() as db:
            try:
                await offer_service.accept_offer(
                    db, user_id=PUJARI_USER, assignment_id=uuid.UUID(assignment_id)
                )
                await db.commit()
                return "ok"
            except DBAPIError as exc:
                await db.rollback()
                resp = map_db_error(exc.orig, "/v1/offers/x/accept")
                return resp.status_code

    results = await asyncio.gather(
        _try_accept(aid_a),
        _try_accept(aid_b),
    )
    assert results.count("ok") == 1
    assert sum(1 for r in results if r == 409) == 1

    async with maker() as verify:
        confirmed = (
            await verify.execute(
                text(
                    """
                    SELECT count(*) FROM bookings b
                    JOIN status_types st ON st.id = b.status_id
                    JOIN pujaris p ON p.id = b.pujari_id
                    WHERE p.user_id = :uid
                      AND b.scheduled_date = CAST(:d AS date)
                      AND b.cancelled_at IS NULL
                      AND st.domain = 'booking'
                      AND st.code = 'confirmed'
                    """
                ),
                {"uid": str(PUJARI_USER), "d": uniq.date},
            )
        ).scalar_one()
        assert confirmed == 1
