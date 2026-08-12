"""DV2-BOOKING-GATE — frozen booking_class + night slot 422s (§21.6.A)."""
from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import text

from app.schemas.booking import BookingCreate
from app.services import booking_service, razorpay_client
from app.services.booking_gate import (
    assert_booking_gate,
    compute_booking_class,
    evaluate_booking_gate,
    gate_warning_payload,
    is_night_slot,
    load_booking_gate_settings,
    night_gate_error_code,
    BookingGateSettings,
)


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


async def _insert_hold(
    session,
    *,
    user_id: uuid.UUID,
    slot_date: dt.date,
    slot_time: dt.time,
    now: dt.datetime,
) -> uuid.UUID:
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


def test_is_night_slot_boundaries():
    assert is_night_slot(dt.time(0, 0)) is True
    assert is_night_slot(dt.time(5, 59)) is True
    assert is_night_slot(dt.time(6, 0)) is False
    assert is_night_slot(dt.time(23, 59)) is False


def test_compute_booking_class_threshold():
    assert compute_booking_class(4.0, 4) == "instant"
    assert compute_booking_class(4.1, 4) == "advance"


def test_night_gate_error_codes():
    assert night_gate_error_code("instant", True, False) == "INSTANT_NIGHT_BLOCKED"
    assert night_gate_error_code("advance", True, False) == "NIGHT_BOOKINGS_DISABLED"
    assert night_gate_error_code("advance", True, True) is None
    assert night_gate_error_code("instant", False, False) is None


def test_assert_booking_gate_instant_night_raises():
    settings = BookingGateSettings(instant_lead_hours=4, night_bookings_enabled=False)
    # 2036-06-16 02:00 IST = 2036-06-15 20:30 UTC; now 18:00 UTC -> ~2.5h lead -> instant
    now = dt.datetime(2036, 6, 15, 18, 0, tzinfo=dt.UTC)
    with pytest.raises(HTTPException) as exc:
        assert_booking_gate(dt.date(2036, 6, 16), dt.time(2, 0), settings, now=now)
    assert exc.value.detail == gate_warning_payload("INSTANT_NIGHT_BLOCKED")


def test_assert_booking_gate_advance_night_launch_raises():
    settings = BookingGateSettings(instant_lead_hours=4, night_bookings_enabled=False)
    now = dt.datetime(2036, 6, 10, 10, 0, tzinfo=dt.UTC)
    with pytest.raises(HTTPException) as exc:
        assert_booking_gate(dt.date(2036, 6, 20), dt.time(3, 0), settings, now=now)
    assert exc.value.detail == gate_warning_payload("NIGHT_BOOKINGS_DISABLED")


def test_evaluate_booking_gate_day_slot_ok():
    settings = BookingGateSettings(instant_lead_hours=4, night_bookings_enabled=False)
    now = dt.datetime(2036, 6, 15, 10, 0, tzinfo=dt.UTC)
    result = evaluate_booking_gate(dt.date(2036, 6, 15), dt.time(11, 0), settings, now=now)
    assert result.booking_class == "instant"
    assert result.is_night is False


@pytest.mark.asyncio
async def test_load_booking_gate_settings(session, seed):
    await _require_migration_014(session)
    settings = await load_booking_gate_settings(session)
    assert settings.instant_lead_hours == 4
    assert settings.night_bookings_enabled is False


@pytest.mark.asyncio
async def test_create_booking_sets_booking_class(session, seed, uniq, monkeypatch):
    """Successful checkout persists frozen booking_class before Razorpay."""
    await _require_migration_014(session)

    user_id = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001")
    puja_id = uuid.UUID("11111111-1111-1111-1111-111111111111")
    address_id = uuid.UUID("dddddddd-0000-0000-0000-000000000001")
    now = dt.datetime(2036, 6, 15, 10, 0, tzinfo=dt.UTC)
    slot_date = dt.date.fromisoformat(uniq.date2)
    slot_time = dt.time(10, 0)

    hold_id = await _insert_hold(
        session, user_id=user_id, slot_date=slot_date, slot_time=slot_time, now=now
    )
    await session.execute(
        text(
            """
            INSERT INTO platform_settings (key, value_json) VALUES
            ('advance_booking_amount', '{"amount": 250.00, "currency": "INR"}')
            ON CONFLICT (key) DO NOTHING
            """
        )
    )
    await session.commit()

    class _FixedDatetime(dt.datetime):
        @classmethod
        def now(cls, tz=None):  # noqa: ANN001
            return now if tz is None else now.astimezone(tz)

    monkeypatch.setattr(booking_service.dt, "datetime", _FixedDatetime)

    expected_order = f"order_{uniq.id()}"

    async def _fake_order(**_kwargs: object) -> str:
        return expected_order

    monkeypatch.setattr(razorpay_client, "create_order", _fake_order)

    payload = BookingCreate(
        hold_id=hold_id,
        puja_id=puja_id,
        address_id=address_id,
        payment_mode="full_online",
    )
    resp = await booking_service.create_booking(session, user_id=user_id, payload=payload)
    await session.commit()

    stored = (
        await session.execute(
            text("SELECT booking_class FROM bookings WHERE id = :bid"),
            {"bid": str(resp.booking_id)},
        )
    ).scalar_one()
    assert stored == "advance"
    assert resp.razorpay_order_id == expected_order


@pytest.mark.asyncio
async def test_lg_night_gate_blocks_before_razorpay(session, seed, monkeypatch):
    """LG-night-gate: night advance slot -> 422 NIGHT_BOOKINGS_DISABLED, no Razorpay call."""
    await _require_migration_014(session)

    user_id = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001")
    puja_id = uuid.UUID("11111111-1111-1111-1111-111111111111")
    address_id = uuid.UUID("dddddddd-0000-0000-0000-000000000001")
    now = dt.datetime(2036, 6, 10, 10, 0, tzinfo=dt.UTC)
    slot_date = dt.date(2036, 6, 20)
    slot_time = dt.time(3, 0)

    hold_id = await _insert_hold(
        session, user_id=user_id, slot_date=slot_date, slot_time=slot_time, now=now
    )
    await session.commit()

    class _FixedDatetime(dt.datetime):
        @classmethod
        def now(cls, tz=None):  # noqa: ANN001
            return now if tz is None else now.astimezone(tz)

    monkeypatch.setattr(booking_service.dt, "datetime", _FixedDatetime)

    async def _fail_order(**_kwargs: object) -> str:
        raise AssertionError("Razorpay must not be called when night gate blocks")

    monkeypatch.setattr(razorpay_client, "create_order", _fail_order)

    payload = BookingCreate(
        hold_id=hold_id,
        puja_id=puja_id,
        address_id=address_id,
        payment_mode="full_online",
    )
    with pytest.raises(HTTPException) as exc:
        await booking_service.create_booking(session, user_id=user_id, payload=payload)

    assert exc.value.status_code == 422
    assert exc.value.detail["code"] == "NIGHT_BOOKINGS_DISABLED"

    count = (
        await session.execute(
            text(
                "SELECT count(*) FROM bookings b "
                "JOIN slot_holds sh ON sh.id = b.hold_id "
                "WHERE sh.id = :hid"
            ),
            {"hid": str(hold_id)},
        )
    ).scalar_one()
    assert count == 0


@pytest.mark.asyncio
async def test_lg_instant_night_blocked(session, seed, monkeypatch):
    """Instant-class night slot -> INSTANT_NIGHT_BLOCKED (permanent rule)."""
    await _require_migration_014(session)

    user_id = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001")
    puja_id = uuid.UUID("11111111-1111-1111-1111-111111111111")
    address_id = uuid.UUID("dddddddd-0000-0000-0000-000000000001")
    now = dt.datetime(2036, 6, 15, 18, 0, tzinfo=dt.UTC)
    slot_date = dt.date(2036, 6, 16)
    slot_time = dt.time(2, 0)

    hold_id = await _insert_hold(
        session, user_id=user_id, slot_date=slot_date, slot_time=slot_time, now=now
    )
    await session.commit()

    class _FixedDatetime(dt.datetime):
        @classmethod
        def now(cls, tz=None):  # noqa: ANN001
            return now if tz is None else now.astimezone(tz)

    monkeypatch.setattr(booking_service.dt, "datetime", _FixedDatetime)

    payload = BookingCreate(
        hold_id=hold_id,
        puja_id=puja_id,
        address_id=address_id,
        payment_mode="full_online",
    )
    with pytest.raises(HTTPException) as exc:
        await booking_service.create_booking(session, user_id=user_id, payload=payload)

    assert exc.value.detail["code"] == "INSTANT_NIGHT_BLOCKED"
