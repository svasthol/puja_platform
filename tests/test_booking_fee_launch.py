"""Sprint 1 launch-gate integration tests (booking_fee model on live PostgreSQL)."""
from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal

import pytest

pytestmark = pytest.mark.booking_fee_launch
from fastapi import HTTPException
from sqlalchemy import text

from app.schemas.booking import BookingCreate
from app.services import booking_service, cancellation_service
from app.services.pricing import (
    compute_booking_fee_amounts,
    customer_cancel_refund_amount,
    refundable_platform_amount,
    tds_on_facilitation,
)
from app.workers.dispatch import exhaust_booking_no_pujari, get_connection

CUSTOMER = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001")
PUJA = uuid.UUID("11111111-1111-1111-1111-111111111111")
ADDRESS = uuid.UUID("dddddddd-0000-0000-0000-000000000001")
FEE = Decimal("61.00")


async def _require_migration_025(session) -> None:
    row = (
        await session.execute(
            text(
                """
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'bookings'
                  AND column_name = 'booking_fee'
                """
            )
        )
    ).scalar_one_or_none()
    if row is None:
        pytest.skip("migration_025 not applied — run: python scripts/apply_migration_025.py")


async def _seed_booking_fee(session, fee: Decimal = FEE) -> None:
    await session.execute(
        text(
            """
            INSERT INTO platform_settings (key, value_json, updated_at)
            VALUES (
                'booking_fee',
                jsonb_build_object('amount', CAST(:amt AS numeric), 'currency', 'INR',
                                   'label', 'Muhurat & Slot Lock Token'),
                now()
            )
            ON CONFLICT (key) DO UPDATE SET
                value_json = jsonb_build_object(
                    'amount', CAST(:amt AS numeric), 'currency', 'INR',
                    'label', 'Muhurat & Slot Lock Token'
                ),
                updated_at = now()
            """
        ),
        {"amt": str(fee)},
    )


async def _ensure_dispatch_supply(session) -> None:
    """Pricing, service area, and availability for launch eligibility."""
    rows = (
        await session.execute(
            text("SELECT id::text FROM pujaris ORDER BY id LIMIT 2")
        )
    ).scalars().all()
    if len(rows) < 1:
        return
    p1 = rows[0]
    p2 = rows[1] if len(rows) > 1 else rows[0]
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
        {"puja": str(PUJA), "p1": p1, "p2": p2},
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


async def _insert_hold(session, uniq) -> uuid.UUID:
    hold_id = uuid.uuid4()
    now = dt.datetime.now(dt.UTC)
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
            "uid": str(CUSTOMER),
            "sd": dt.date.fromisoformat(uniq.date),
            "st": dt.time(11, 0),
            "now": now,
        },
    )
    return hold_id


def test_compute_booking_fee_amounts_pure():
    total, online, offline, fee = compute_booking_fee_amounts(Decimal("2100"), FEE)
    assert total == Decimal("2100")
    assert online == Decimal("0")
    assert offline == Decimal("2100")
    assert fee == FEE


def test_tds_null_entity_type_raises():
    with pytest.raises(ValueError, match="entity_type required"):
        tds_on_facilitation(
            entity_type=None,
            pan_on_file=True,
            fy_gross_before=Decimal("490000"),
            this_amount=Decimal("20000"),
        )


@pytest.mark.asyncio
async def test_create_booking_booking_fee_amounts(session, seed, uniq, monkeypatch):
    async def _fake_order(**_kwargs: object) -> str:
        return f"order_{uniq.id()}"

    monkeypatch.setattr("app.services.razorpay_client.create_order", _fake_order)

    async with session.begin():
        await _require_migration_025(session)
        await _seed_booking_fee(session)
        await _ensure_dispatch_supply(session)
        hold_id = await _insert_hold(session, uniq)
        payload = BookingCreate(
            hold_id=hold_id,
            puja_id=PUJA,
            address_id=ADDRESS,
            payment_mode="booking_fee",
        )
        resp = await booking_service.create_booking(
            session, user_id=CUSTOMER, payload=payload
        )
    assert resp.payment_mode == "booking_fee"
    assert resp.booking_fee == FEE
    assert resp.amount_due_online == Decimal("0")
    assert resp.amount_due_offline == Decimal("2100")
    assert resp.razorpay_amount == FEE


@pytest.mark.asyncio
async def test_full_online_rejected_at_launch(session, seed, uniq):
    with pytest.raises(HTTPException) as exc:
        async with session.begin():
            await _require_migration_025(session)
            hold_id = await _insert_hold(session, uniq)
            payload = BookingCreate(
                hold_id=hold_id,
                puja_id=PUJA,
                address_id=ADDRESS,
                payment_mode="full_online",
            )
            await booking_service.create_booking(
                session, user_id=CUSTOMER, payload=payload
            )
    assert exc.value.status_code == 422


def test_no_pujari_refunds_booking_fee(uniq):
    conn = get_connection()
    bid = uniq.id()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'bookings'
                  AND column_name = 'booking_fee'
                """
            )
            if cur.fetchone() is None:
                pytest.skip("migration_025 not applied — run: python scripts/apply_migration_025.py")
            cur.execute(
                """
                INSERT INTO bookings (
                    id, user_id, puja_id, address_id, status_id, cancellation_policy_id,
                    scheduled_date, scheduled_time, duration_minutes, total_amount,
                    amount_due_online, amount_due_offline, booking_fee, payment_mode, paid_at,
                    dispatch_mode, booking_class, created_at, updated_at
                ) VALUES (
                    %s, %s, %s, %s,
                    (SELECT id FROM status_types WHERE domain='booking' AND code='requested'),
                    (SELECT id FROM cancellation_policies WHERE name='standard'),
                    %s, %s::time, 90, 2100, 0, 2100, 61, 'booking_fee', now(),
                    'broadcast', 'advance', now(), now()
                )
                """,
                (bid, str(CUSTOMER), str(PUJA), str(ADDRESS), uniq.date, "10:00:00"),
            )
            cur.execute(
                """
                INSERT INTO payments (
                    id, booking_id, amount, idempotency_key, gateway_txn_id, status, created_at
                ) VALUES (
                    gen_random_uuid(), %s, 61, %s, %s, 'success', now()
                )
                """,
                (bid, f"idem_{bid}", f"pay_{bid}"),
            )
            result = exhaust_booking_no_pujari(cur, conn, bid)
        assert result.get("status") == "failed_no_pujari"
        with conn.cursor() as cur:
            cur.execute("SELECT amount FROM refunds WHERE booking_id = %s", (bid,))
            row = cur.fetchone()
        assert row is not None
        assert Decimal(str(row[0])) == FEE
    finally:
        conn.close()


@pytest.mark.asyncio
async def test_customer_cancel_requested_full_fee_refund(session, seed, uniq):
    bid = uuid.UUID(uniq.id())
    now = dt.datetime.now(dt.UTC)
    async with session.begin():
        await _require_migration_025(session)
        pending = (
            await session.execute(
                text(
                    "SELECT id FROM status_types WHERE domain='booking' AND code='requested'"
                )
            )
        ).scalar_one()
        policy = (
            await session.execute(
                text("SELECT id FROM cancellation_policies WHERE name='standard'")
            )
        ).scalar_one()
        await session.execute(
            text(
                """
                INSERT INTO bookings (
                    id, user_id, puja_id, address_id, status_id, cancellation_policy_id,
                    scheduled_date, scheduled_time, duration_minutes, total_amount,
                    amount_due_online, amount_due_offline, booking_fee, payment_mode, paid_at,
                    booking_class, created_at, updated_at
                ) VALUES (
                    :bid, :uid, :pid, :aid, :sid, :cpid,
                    :sd, CAST(:st AS time), 90, 2100, 0, 2100, 61, 'booking_fee', :now,
                    'advance', :now, :now
                )
                """
            ),
            {
                "bid": str(bid),
                "uid": str(CUSTOMER),
                "pid": str(PUJA),
                "aid": str(ADDRESS),
                "sid": pending,
                "cpid": policy,
                "sd": uniq.date,
                "st": "10:00:00",
                "now": now,
            },
        )
        await session.execute(
            text(
                """
                INSERT INTO payments (
                    id, booking_id, amount, idempotency_key, gateway_txn_id, status, created_at
                ) VALUES (
                    gen_random_uuid(), :bid, 61, :idem, :pay, 'success', :now
                )
                """
            ),
            {"bid": str(bid), "idem": f"idem_{bid}", "pay": f"pay_{bid}", "now": now},
        )

    async with session.begin():
        resp = await cancellation_service.cancel_booking(
            session, user_id=CUSTOMER, booking_id=bid
        )
    assert resp.refund_amount == FEE


def test_customer_cancel_confirmed_zero_refund_launch():
    amt = customer_cancel_refund_amount(
        booking_fee=FEE,
        amount_due_online=Decimal("0"),
        payment_mode="booking_fee",
        status_code="confirmed",
        policy_pct=100,
    )
    assert amt == Decimal("0")


@pytest.mark.asyncio
async def test_webhook_rejects_amount_mismatch_for_booking_fee(session, seed, uniq):
    """Under/over capture must not confirm booking — auto-refund initiated."""
    from app.services import webhook_service

    bid = uuid.UUID(uniq.id())
    pending = (
        await session.execute(
            text("SELECT id FROM status_types WHERE domain='booking' AND code='payment_pending'")
        )
    ).scalar_one()
    policy = (
        await session.execute(
            text("SELECT id FROM cancellation_policies WHERE name='standard'")
        )
    ).scalar_one()
    now = dt.datetime.now(dt.UTC)
    await _require_migration_025(session)
    await session.execute(
        text(
            """
            INSERT INTO bookings (
                id, user_id, puja_id, address_id, status_id, cancellation_policy_id,
                scheduled_date, scheduled_time, duration_minutes, total_amount,
                amount_due_online, amount_due_offline, booking_fee, payment_mode,
                booking_class, created_at, updated_at
            ) VALUES (
                :bid, :uid, :pid, :aid, :sid, :cpid,
                :sd, CAST(:st AS time), 90, 2100, 0, 2100, 61, 'booking_fee',
                'advance', :now, :now
            )
            """
        ),
        {
            "bid": str(bid),
            "uid": str(CUSTOMER),
            "pid": str(PUJA),
            "aid": str(ADDRESS),
            "sid": pending,
            "cpid": policy,
            "sd": uniq.date,
            "st": "10:00:00",
            "now": now,
        },
    )
    await session.commit()

    result = await webhook_service.handle_payment_captured(
        session,
        booking_id=bid,
        gateway_txn_id=f"pay_{uniq.id()}",
        idempotency_key=f"idem_{uniq.id()}",
        amount_paise=1000,
    )
    await session.commit()

    assert result.get("status") == "auto_refund_initiated"
    assert result.get("reason") == "amount_mismatch"
    status_code = (
        await session.execute(
            text(
                "SELECT st.code FROM bookings b "
                "JOIN status_types st ON st.id = b.status_id WHERE b.id = :bid"
            ),
            {"bid": str(bid)},
        )
    ).scalar_one()
    assert status_code == "payment_pending"
    refund = (
        await session.execute(
            text("SELECT amount FROM refunds WHERE booking_id = :bid"),
            {"bid": str(bid)},
        )
    ).scalar_one_or_none()
    assert refund is not None
    assert Decimal(str(refund)) == Decimal("10.00")


@pytest.mark.asyncio
async def test_webhook_creates_payment_split_for_booking_fee(session, seed, uniq):
    """Successful capture records payment_splits with platform_fee = booking_fee."""
    from app.services import webhook_service

    bid = uuid.UUID(uniq.id())
    pending = (
        await session.execute(
            text("SELECT id FROM status_types WHERE domain='booking' AND code='payment_pending'")
        )
    ).scalar_one()
    policy = (
        await session.execute(
            text("SELECT id FROM cancellation_policies WHERE name='standard'")
        )
    ).scalar_one()
    now = dt.datetime.now(dt.UTC)
    await _require_migration_025(session)
    await session.execute(
        text(
            """
            INSERT INTO bookings (
                id, user_id, puja_id, address_id, status_id, cancellation_policy_id,
                scheduled_date, scheduled_time, duration_minutes, total_amount,
                amount_due_online, amount_due_offline, booking_fee, payment_mode,
                booking_class, created_at, updated_at
            ) VALUES (
                :bid, :uid, :pid, :aid, :sid, :cpid,
                :sd, CAST(:st AS time), 90, 2100, 0, 2100, 61, 'booking_fee',
                'advance', :now, :now
            )
            """
        ),
        {
            "bid": str(bid),
            "uid": str(CUSTOMER),
            "pid": str(PUJA),
            "aid": str(ADDRESS),
            "sid": pending,
            "cpid": policy,
            "sd": uniq.date,
            "st": "10:00:00",
            "now": now,
        },
    )
    await session.commit()

    result = await webhook_service.handle_payment_captured(
        session,
        booking_id=bid,
        gateway_txn_id=f"pay_{uniq.id()}",
        idempotency_key=f"idem_{uniq.id()}",
        amount_paise=6100,
    )
    await session.commit()
    assert result.get("status") == "confirmed"

    split = (
        await session.execute(
            text(
                """
                SELECT ps.platform_fee, ps.net_pujari_amount
                FROM payments p
                JOIN payment_splits ps ON ps.payment_id = p.id
                WHERE p.booking_id = :bid
                """
            ),
            {"bid": str(bid)},
        )
    ).mappings().first()
    assert split is not None
    assert Decimal(str(split["platform_fee"])) == FEE
    assert Decimal(str(split["net_pujari_amount"])) == Decimal("0")


@pytest.mark.asyncio
async def test_admin_money_read_booking_fee_cap(session, seed, uniq):
    """Admin money read caps refundable_remaining at frozen booking_fee."""
    from app.api.v1.endpoints import admin_bookings as bookings_ep

    class _FakeRequest:
        client = None

    bid = uuid.UUID(uniq.id())
    pending = (
        await session.execute(
            text("SELECT id FROM status_types WHERE domain='booking' AND code='confirmed'")
        )
    ).scalar_one()
    policy = (
        await session.execute(
            text("SELECT id FROM cancellation_policies WHERE name='standard'")
        )
    ).scalar_one()
    now = dt.datetime.now(dt.UTC)
    await _require_migration_025(session)
    await session.execute(
        text(
            """
            INSERT INTO bookings (
                id, user_id, puja_id, address_id, status_id, cancellation_policy_id,
                scheduled_date, scheduled_time, duration_minutes, total_amount,
                amount_due_online, amount_due_offline, booking_fee, payment_mode, paid_at,
                booking_class, created_at, updated_at
            ) VALUES (
                :bid, :uid, :pid, :aid, :sid, :cpid,
                :sd, CAST(:st AS time), 90, 2100, 0, 2100, 61, 'booking_fee', :now,
                'advance', :now, :now
            )
            """
        ),
        {
            "bid": str(bid),
            "uid": str(CUSTOMER),
            "pid": str(PUJA),
            "aid": str(ADDRESS),
            "sid": pending,
            "cpid": policy,
            "sd": uniq.date,
            "st": "10:00:00",
            "now": now,
        },
    )
    await session.execute(
        text(
            """
            INSERT INTO payments (
                id, booking_id, amount, idempotency_key, gateway_txn_id, status, created_at
            ) VALUES (
                gen_random_uuid(), :bid, 61, :idem, :pay, 'success', :now
            )
            """
        ),
        {"bid": str(bid), "idem": f"idem_{bid}", "pay": f"pay_{bid}", "now": now},
    )
    from app.core.dependencies import Principal

    class _FakeRequest:
        client = None

    admin_uid = uuid.uuid4()
    await session.execute(
        text("INSERT INTO users (id, full_name, phone) VALUES (:id, 'Admin', :ph)"),
        {"id": str(admin_uid), "ph": "+91975" + uuid.uuid4().hex[:7]},
    )
    await session.commit()

    money = await bookings_ep.get_booking_money(
        bid,
        _FakeRequest(),
        Principal(user_id=admin_uid, app_context="admin", roles=("admin",)),
        session,
    )
    assert money.payment_mode == "booking_fee"
    assert money.booking_fee == FEE
    assert money.refundable_remaining_online == FEE
    assert money.amount_due_offline == Decimal("2100")


def test_refundable_platform_amount_no_pujari():
    amt = refundable_platform_amount(
        booking_fee=FEE,
        amount_due_online=Decimal("0"),
        payment_mode="booking_fee",
        status_code="requested",
        reason="no_pujari",
    )
    assert amt == FEE
