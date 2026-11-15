"""PR2 end-to-end reliability: post-commit, payment-verify, reconcile scheduling."""
from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import uuid
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from sqlalchemy import text

from app.core.config import get_settings
from app.db import post_commit
from app.schemas.booking import BookingCreate
from app.services import booking_events, booking_service, payment_capture, payment_verify_service
from app.services import razorpay_client

CUSTOMER = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001")
PUJA = uuid.UUID("11111111-1111-1111-1111-111111111111")
ADDRESS = uuid.UUID("dddddddd-0000-0000-0000-000000000001")
FEE_PAISE = 6100


async def _require_migration_038(session) -> None:
    row = (
        await session.execute(
            text(
                """
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'bookings'
                  AND column_name = 'reconcile_next_at'
                """
            )
        )
    ).scalar_one_or_none()
    if row is None:
        pytest.skip("migration_038 not applied — run: python scripts/apply_migration_038.py")


async def _seed_booking_fee(session) -> None:
    await session.execute(
        text(
            """
            INSERT INTO platform_settings (key, value_json, updated_at)
            VALUES (
                'booking_fee',
                '{"amount": 61.00, "currency": "INR", "label": "Muhurat & Slot Lock Token"}',
                now()
            )
            ON CONFLICT (key) DO UPDATE SET value_json = EXCLUDED.value_json, updated_at = now()
            """
        )
    )


async def _insert_hold(session, uniq) -> uuid.UUID:
    hold_id = uuid.uuid4()
    now = dt.datetime.now(dt.UTC)
    await session.execute(
        text(
            """
            INSERT INTO slot_holds (
                id, user_id, pujari_id, slot_date, slot_time,
                held_at, expires_at, released_at, converted_at
            ) VALUES (
                :hid, :uid, NULL, :sd, :st, :now, :exp, NULL, NULL
            )
            """
        ),
        {
            "hid": str(hold_id),
            "uid": str(CUSTOMER),
            "sd": uniq.date2,
            "st": "09:00:00",
            "now": now,
            "exp": now + dt.timedelta(minutes=5),
        },
    )
    return hold_id


def _checkout_signature(*, order_id: str, payment_id: str) -> str:
    secret = get_settings().RAZORPAY_KEY_SECRET or "test_secret"
    payload = f"{order_id}|{payment_id}".encode()
    return hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()


async def _ensure_dispatch_supply(session) -> None:
    """Pricing, service area, and availability for launch eligibility."""
    rows = (
        await session.execute(text("SELECT id::text FROM pujaris ORDER BY id LIMIT 2"))
    ).scalars().all()
    if len(rows) < 1:
        return
    p1, p2 = rows[0], rows[1] if len(rows) > 1 else rows[0]
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


@pytest.mark.asyncio
async def test_create_booking_sets_reconcile_schedule(session, seed, uniq, monkeypatch):
    """REL-005: razorpay order write schedules reconcile_next_at (~20m)."""
    await _require_migration_038(session)
    await session.rollback()

    order_id = f"order_{uniq.id()[:12]}"

    async def _fake_order(**_kwargs: object) -> str:
        return order_id

    monkeypatch.setattr(razorpay_client, "create_order", _fake_order)

    async with session.begin():
        await _seed_booking_fee(session)
        await _ensure_dispatch_supply(session)
        hold_id = await _insert_hold(session, uniq)
        payload = BookingCreate(
            hold_id=hold_id,
            puja_id=PUJA,
            address_id=ADDRESS,
            payment_mode="booking_fee",
        )
        resp = await booking_service.create_booking(session, user_id=CUSTOMER, payload=payload)

    row = (
        await session.execute(
            text(
                """
                SELECT razorpay_order_id, reconcile_next_at, reconcile_attempts
                FROM bookings WHERE id = :bid
                """
            ),
            {"bid": str(resp.booking_id)},
        )
    ).mappings().one()
    assert row["razorpay_order_id"] == order_id
    assert row["reconcile_next_at"] is not None
    assert int(row["reconcile_attempts"] or 0) == 0


@pytest.mark.asyncio
async def test_payment_capture_clears_reconcile(session, seed, uniq, monkeypatch):
    """Successful capture NULLs reconcile_next_at."""
    await _require_migration_038(session)
    booking_id = uuid.uuid4()
    now = dt.datetime.now(dt.UTC)
    pending_id = (
        await session.execute(
            text("SELECT id FROM status_types WHERE domain='booking' AND code='payment_pending'")
        )
    ).scalar_one()
    policy_id = (
        await session.execute(text("SELECT id FROM cancellation_policies WHERE name='standard'"))
    ).scalar_one()

    await session.execute(
        text(
            """
            INSERT INTO bookings (
                id, user_id, puja_id, address_id, status_id, cancellation_policy_id,
                scheduled_date, scheduled_time, duration_minutes, total_amount,
                amount_due_online, amount_due_offline, payment_mode, dispatch_mode,
                booking_class, booking_fee, razorpay_order_id, reconcile_next_at,
                reconcile_attempts, created_at, updated_at
            ) VALUES (
                :bid, :uid, :puja, :addr, :sid, :cpid,
                :sd, '14:00:00', 90, 2100, 0, 2100, 'booking_fee', 'broadcast',
                'instant', 61, :oid, :rat, 1, :now, :now
            )
            """
        ),
        {
            "bid": str(booking_id),
            "uid": str(CUSTOMER),
            "puja": str(PUJA),
            "addr": str(ADDRESS),
            "sid": pending_id,
            "cpid": policy_id,
            "sd": uniq.date2,
            "oid": f"order_{uniq.id()[:8]}",
            "rat": now + dt.timedelta(minutes=5),
            "now": now,
        },
    )
    await session.commit()

    async def _noop_publish(*_a: object, **_k: object) -> None:
        return None

    monkeypatch.setattr(booking_events, "publish_booking_event", _noop_publish)

    pay_id = f"pay_{uniq.id()[:10]}"
    async with session.begin():
        result = await payment_capture.handle_payment_captured(
            session,
            booking_id=booking_id,
            gateway_txn_id=pay_id,
            idempotency_key=pay_id,
            amount_paise=FEE_PAISE,
        )
    assert result.get("status") == "confirmed"

    cleared = (
        await session.execute(
            text("SELECT reconcile_next_at FROM bookings WHERE id = :bid"),
            {"bid": str(booking_id)},
        )
    ).scalar_one()
    assert cleared is None


@pytest.mark.asyncio
async def test_payment_verify_captured_confirms(session, seed, uniq, monkeypatch):
    """REL-015: valid signature + captured payment → requested + enqueue hint."""
    await _require_migration_038(session)
    booking_id = uuid.uuid4()
    now = dt.datetime.now(dt.UTC)
    pending_id = (
        await session.execute(
            text("SELECT id FROM status_types WHERE domain='booking' AND code='payment_pending'")
        )
    ).scalar_one()
    policy_id = (
        await session.execute(text("SELECT id FROM cancellation_policies WHERE name='standard'"))
    ).scalar_one()
    order_id = f"order_{uniq.id()[:12]}"
    pay_id = f"pay_{uniq.id()[:12]}"
    sig = _checkout_signature(order_id=order_id, payment_id=pay_id)

    await session.execute(
        text(
            """
            INSERT INTO bookings (
                id, user_id, puja_id, address_id, status_id, cancellation_policy_id,
                scheduled_date, scheduled_time, duration_minutes, total_amount,
                amount_due_online, amount_due_offline, payment_mode, dispatch_mode,
                booking_class, booking_fee, razorpay_order_id, created_at, updated_at
            ) VALUES (
                :bid, :uid, :puja, :addr, :sid, :cpid,
                    :sd, '11:00:00', 90, 2100, 0, 2100, 'booking_fee', 'broadcast',
                    'instant', 61, :oid, :now, :now
                )
                """
            ),
            {
                "bid": str(booking_id),
                "uid": str(CUSTOMER),
                "puja": str(PUJA),
                "addr": str(ADDRESS),
                "sid": pending_id,
                "cpid": policy_id,
                "sd": uniq.date2,
                "oid": order_id,
                "now": now,
            },
        )
    await session.commit()

    async def _fake_fetch(payment_id: str) -> dict:
        assert payment_id == pay_id
        return {"id": pay_id, "order_id": order_id, "status": "captured", "amount": FEE_PAISE}

    async def _noop_publish(*_a: object, **_k: object) -> None:
        return None

    monkeypatch.setattr(razorpay_client, "fetch_payment", _fake_fetch)
    monkeypatch.setattr(booking_events, "publish_booking_event", _noop_publish)

    async with session.begin():
        body, status = await payment_verify_service.verify_booking_payment(
            session,
            user_id=CUSTOMER,
            booking_id=booking_id,
            razorpay_payment_id=pay_id,
            razorpay_order_id=order_id,
            razorpay_signature=sig,
        )
    assert status == 200
    assert body["status"] == "confirmed"


@pytest.mark.asyncio
async def test_payment_verify_rejects_bad_signature(session, seed, uniq):
    await _require_migration_038(session)
    await session.rollback()
    booking_id = uuid.uuid4()
    order_id = f"order_{uniq.id()[:12]}"
    now = dt.datetime.now(dt.UTC)
    pending_id = (
        await session.execute(
            text("SELECT id FROM status_types WHERE domain='booking' AND code='payment_pending'")
        )
    ).scalar_one()
    policy_id = (
        await session.execute(text("SELECT id FROM cancellation_policies WHERE name='standard'"))
    ).scalar_one()

    await session.execute(
        text(
            """
            INSERT INTO bookings (
                id, user_id, puja_id, address_id, status_id, cancellation_policy_id,
                scheduled_date, scheduled_time, duration_minutes, total_amount,
                amount_due_online, amount_due_offline, payment_mode, dispatch_mode,
                booking_class, booking_fee, razorpay_order_id, created_at, updated_at
            ) VALUES (
                :bid, :uid, :puja, :addr, :sid, :cpid,
                    :sd, '12:00:00', 90, 2100, 0, 2100, 'booking_fee', 'broadcast',
                    'instant', 61, :oid, :now, :now
                )
                """
            ),
            {
                "bid": str(booking_id),
                "uid": str(CUSTOMER),
                "puja": str(PUJA),
                "addr": str(ADDRESS),
                "sid": pending_id,
                "cpid": policy_id,
                "sd": uniq.date2,
                "oid": order_id,
                "now": now,
            },
        )
    await session.commit()

    with pytest.raises(HTTPException) as exc:
        async with session.begin():
            await payment_verify_service.verify_booking_payment(
                session,
                user_id=CUSTOMER,
                booking_id=booking_id,
                razorpay_payment_id=f"pay_{uniq.id()[:12]}",
                razorpay_order_id=order_id,
                razorpay_signature="deadbeef",
            )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_payment_verify_authorized_is_202(session, seed, uniq, monkeypatch):
    await _require_migration_038(session)
    booking_id = uuid.uuid4()
    now = dt.datetime.now(dt.UTC)
    pending_id = (
        await session.execute(
            text("SELECT id FROM status_types WHERE domain='booking' AND code='payment_pending'")
        )
    ).scalar_one()
    policy_id = (
        await session.execute(text("SELECT id FROM cancellation_policies WHERE name='standard'"))
    ).scalar_one()
    order_id = f"order_{uniq.id()[:12]}"
    pay_id = f"pay_{uniq.id()[:12]}"
    sig = _checkout_signature(order_id=order_id, payment_id=pay_id)

    await session.execute(
        text(
            """
            INSERT INTO bookings (
                id, user_id, puja_id, address_id, status_id, cancellation_policy_id,
                scheduled_date, scheduled_time, duration_minutes, total_amount,
                amount_due_online, amount_due_offline, payment_mode, dispatch_mode,
                booking_class, booking_fee, razorpay_order_id, created_at, updated_at
            ) VALUES (
                :bid, :uid, :puja, :addr, :sid, :cpid,
                    :sd, '13:00:00', 90, 2100, 0, 2100, 'booking_fee', 'broadcast',
                    'instant', 61, :oid, :now, :now
                )
                """
            ),
            {
                "bid": str(booking_id),
                "uid": str(CUSTOMER),
                "puja": str(PUJA),
                "addr": str(ADDRESS),
                "sid": pending_id,
                "cpid": policy_id,
                "sd": uniq.date2,
                "oid": order_id,
                "now": now,
            },
        )
    await session.commit()

    async def _fake_fetch(_pid: str) -> dict:
        return {"id": pay_id, "order_id": order_id, "status": "authorized", "amount": FEE_PAISE}

    monkeypatch.setattr(razorpay_client, "fetch_payment", _fake_fetch)

    async with session.begin():
        body, status = await payment_verify_service.verify_booking_payment(
            session,
            user_id=CUSTOMER,
            booking_id=booking_id,
            razorpay_payment_id=pay_id,
            razorpay_order_id=order_id,
            razorpay_signature=sig,
        )
    assert status == 202
    assert body["status"] == "processing"


@pytest.mark.asyncio
async def test_get_db_txn_pattern_flush_after_commit(session, monkeypatch):
    """REL-002: mimics get_db_txn — tasks only after successful commit."""
    sent: list[str] = []
    mock_app = MagicMock()

    def _send_task(name, args=None, **kwargs):
        sent.append(name)

    mock_app.send_task = _send_task
    monkeypatch.setattr("app.workers.celery_app.celery_app", mock_app)

    post_commit.discard_post_commit(session)
    async with session.begin():
        post_commit.enqueue_celery_task(
            session,
            task_name="app.workers.dispatch.broadcast_booking",
            args=["after-commit"],
        )
        await session.execute(text("SELECT 1"))
    await post_commit.flush_post_commit(session)
    assert sent == ["app.workers.dispatch.broadcast_booking"]