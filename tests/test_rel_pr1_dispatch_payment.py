"""PR1 — REL-001 dispatch guard, REL-004 duplicate capture, REL-016 pay_ keys."""
from __future__ import annotations

import datetime as dt
import uuid

import pytest
from sqlalchemy import text

from app.services import booking_events, webhook_service
from app.workers.dispatch import broadcast_booking
from app.workers.sweep import get_connection

CUSTOMER = "aaaaaaaa-0000-0000-0000-000000000001"
PUJA = "11111111-1111-1111-1111-111111111111"
ADDRESS = "dddddddd-0000-0000-0000-000000000001"


@pytest.mark.asyncio
async def test_duplicate_capture_queues_duplicate_payment_refund(session, seed, uniq, monkeypatch):
    booking_id = uuid.uuid4()
    now = dt.datetime.now(dt.UTC)
    pending_id = (
        await session.execute(
            text("SELECT id FROM status_types WHERE domain='booking' AND code='payment_pending'")
        )
    ).scalar_one()
    requested_id = (
        await session.execute(
            text("SELECT id FROM status_types WHERE domain='booking' AND code='requested'")
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
                booking_class, paid_at, booking_fee, created_at, updated_at
            ) VALUES (
                :bid, :uid, :puja, :addr, :sid, :cpid,
                :sd, '10:00:00', 90, 2100, 0, 2100, 'booking_fee', 'broadcast',
                'instant', :now, 61, :now, :now
            )
            """
        ),
        {
            "bid": str(booking_id),
            "uid": CUSTOMER,
            "puja": PUJA,
            "addr": ADDRESS,
            "sid": requested_id,
            "cpid": policy_id,
            "sd": uniq.date,
            "now": now,
        },
    )
    await session.execute(
        text(
            """
            INSERT INTO payments (id, booking_id, amount, idempotency_key, gateway_txn_id, status, created_at)
            VALUES (gen_random_uuid(), :bid, 61, :k1, :k1, 'success', :now)
            """
        ),
        {"bid": str(booking_id), "k1": f"pay_first_{uniq.id()[:8]}", "now": now},
    )
    await session.commit()

    async def _noop_publish(*_args: object, **_kwargs: object) -> None:
        return None

    monkeypatch.setattr(booking_events, "publish_booking_event", _noop_publish)

    pay2 = f"pay_second_{uniq.id()[:8]}"
    result = await webhook_service.handle_payment_captured(
        session,
        booking_id=booking_id,
        gateway_txn_id=pay2,
        idempotency_key=pay2,
        amount_paise=6100,
    )
    await session.commit()

    assert result.get("reason") == "duplicate_capture"
    dup_status = (
        await session.execute(
            text("SELECT status FROM payments WHERE gateway_txn_id = :k"),
            {"k": pay2},
        )
    ).scalar_one()
    assert dup_status == "duplicate_capture"
    refund_reason = (
        await session.execute(
            text(
                """
                SELECT r.reason FROM refunds r
                JOIN payments p ON p.id = r.payment_id
                WHERE p.gateway_txn_id = :k
                """
            ),
            {"k": pay2},
        )
    ).scalar_one()
    assert refund_reason == "duplicate_payment"


@pytest.mark.asyncio
async def test_replay_same_pay_id_is_already_processed(session, seed, uniq, monkeypatch):
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
                booking_class, booking_fee, created_at, updated_at
            ) VALUES (
                :bid, :uid, :puja, :addr, :sid, :cpid,
                :sd, '10:00:00', 90, 2100, 0, 2100, 'booking_fee', 'broadcast',
                'instant', 61, :now, :now
            )
            """
        ),
        {
            "bid": str(booking_id),
            "uid": CUSTOMER,
            "puja": PUJA,
            "addr": ADDRESS,
            "sid": pending_id,
            "cpid": policy_id,
            "sd": uniq.date,
            "now": now,
        },
    )
    await session.commit()
    async def _noop_publish(*_args: object, **_kwargs: object) -> None:
        return None

    monkeypatch.setattr(booking_events, "publish_booking_event", _noop_publish)

    pay = f"pay_{uniq.id()[:12]}"
    first = await webhook_service.handle_payment_captured(
        session,
        booking_id=booking_id,
        gateway_txn_id=pay,
        idempotency_key=pay,
        amount_paise=6100,
    )
    await session.commit()
    assert first.get("status") == "confirmed"

    second = await webhook_service.handle_payment_captured(
        session,
        booking_id=booking_id,
        gateway_txn_id=pay,
        idempotency_key=pay,
        amount_paise=6100,
    )
    assert second.get("status") == "already_processed"


@pytest.mark.asyncio
async def test_orphan_success_then_valid_capture_confirms_booking(
    session, seed, uniq, monkeypatch
):
    """Mismatched first capture (success row) must not block a valid second capture."""
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
                booking_class, booking_fee, created_at, updated_at
            ) VALUES (
                :bid, :uid, :puja, :addr, :sid, :cpid,
                :sd, '10:00:00', 90, 2100, 0, 2100, 'booking_fee', 'broadcast',
                'instant', 61, :now, :now
            )
            """
        ),
        {
            "bid": str(booking_id),
            "uid": CUSTOMER,
            "puja": PUJA,
            "addr": ADDRESS,
            "sid": pending_id,
            "cpid": policy_id,
            "sd": uniq.date,
            "now": now,
        },
    )
    await session.commit()
    async def _noop_publish(*_args: object, **_kwargs: object) -> None:
        return None

    monkeypatch.setattr(booking_events, "publish_booking_event", _noop_publish)

    bad_pay = f"pay_bad_{uniq.id()[:8]}"
    bad = await webhook_service.handle_payment_captured(
        session,
        booking_id=booking_id,
        gateway_txn_id=bad_pay,
        idempotency_key=bad_pay,
        amount_paise=999,
    )
    await session.commit()
    assert bad.get("reason") == "amount_mismatch"

    good_pay = f"pay_good_{uniq.id()[:8]}"
    good = await webhook_service.handle_payment_captured(
        session,
        booking_id=booking_id,
        gateway_txn_id=good_pay,
        idempotency_key=good_pay,
        amount_paise=6100,
    )
    await session.commit()
    assert good.get("status") == "confirmed"
    paid_at = (
        await session.execute(
            text("SELECT paid_at FROM bookings WHERE id = :bid"),
            {"bid": str(booking_id)},
        )
    ).scalar_one()
    assert paid_at is not None


def test_dispatch_skips_unpaid_payment_pending(uniq):
    conn = get_connection()
    bid = uniq.id()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO bookings (
                    id, user_id, puja_id, address_id, status_id, cancellation_policy_id,
                    scheduled_date, scheduled_time, duration_minutes, total_amount,
                    amount_due_online, amount_due_offline, payment_mode, paid_at,
                    dispatch_mode, booking_class, created_at, updated_at
                ) VALUES (
                    %s, %s, %s, %s,
                    (SELECT id FROM status_types WHERE domain='booking' AND code='payment_pending'),
                    (SELECT id FROM cancellation_policies WHERE name='standard'),
                    %s, '10:00:00', 90, 2100, 2100, 0, 'full_online', NULL,
                    'broadcast', 'instant', now(), now()
                )
                """,
                (bid, CUSTOMER, PUJA, ADDRESS, uniq.date),
            )
        conn.commit()
        result = broadcast_booking(bid)
        assert result.get("skipped") == "not_dispatchable"
    finally:
        conn.close()