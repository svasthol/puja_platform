"""Refund worker — idempotency header + permanent vs retryable classification."""
from __future__ import annotations

import uuid

import httpx
import pytest
from sqlalchemy import text

from app.services.razorpay_client import (
    REFUND_IDEMPOTENCY_HEADER,
    RazorpayRefundPermanentError,
    RazorpayRefundRetryableError,
    create_refund_sync,
)
from app.workers.refund import process_refunds

CUSTOMER = "aaaaaaaa-0000-0000-0000-000000000001"
PUJARI_USER = "bbbbbbbb-0000-0000-0000-000000000001"
ADDRESS = "dddddddd-0000-0000-0000-000000000001"
PUJA = "11111111-1111-1111-1111-111111111111"


@pytest.fixture(autouse=True)
def _stub_refund_ops_alerts(monkeypatch):
    """Avoid prometheus/celery side effects when asserting worker DB transitions."""

    def _mark(conn, *, refund_id, booking_id, attempt, error):
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE refunds SET status='failed_permanent', last_error=%s WHERE id=%s",
                (error[:500], refund_id),
            )

    monkeypatch.setattr("app.workers.refund._mark_failed_permanent", _mark)


def _unique_slot_time(uniq) -> str:
    h = (int(uniq.id().replace("-", "")[:4], 16) % 12) + 8
    m = int(uniq.id().replace("-", "")[4:8], 16) % 60
    return f"{h:02d}:{m:02d}:00"


async def _pujari_id(session) -> str:
    return str(
        (
            await session.execute(
                text("SELECT id FROM pujaris WHERE user_id = :uid"),
                {"uid": PUJARI_USER},
            )
        ).scalar_one()
    )


async def _insert_confirmed_booking(session, uniq) -> str:
    pujari_id = await _pujari_id(session)
    bid = uniq.id()
    slot_time = _unique_slot_time(uniq)
    slot_date = uniq.date
    await session.execute(
        text(
            """
            INSERT INTO bookings (
                id, user_id, pujari_id, intended_pujari_id, puja_id, address_id, status_id,
                cancellation_policy_id, scheduled_date, scheduled_time, duration_minutes,
                total_amount, amount_due_online, amount_due_offline, booking_fee,
                payment_mode, paid_at, cancelled_at, created_at, updated_at
            )
            SELECT
                :bid, :uid, :pid, :pid, :puja, :addr,
                (SELECT id FROM status_types WHERE domain='booking' AND code='confirmed'),
                (SELECT id FROM cancellation_policies ORDER BY id LIMIT 1),
                CAST(:d AS date), CAST(:t AS time), 60,
                2100, 0, 2100, 61, 'booking_fee', now(),
                NULL, now(), now()
            """
        ),
        {
            "bid": bid,
            "uid": CUSTOMER,
            "pid": pujari_id,
            "puja": PUJA,
            "addr": ADDRESS,
            "d": slot_date,
            "t": slot_time,
        },
    )
    return bid


async def _insert_payment(session, booking_id: str, uniq, *, gateway_txn_id: str | None) -> str:
    pay_id = uniq.id()
    await session.execute(
        text(
            """
            INSERT INTO payments (
                id, booking_id, amount, idempotency_key, gateway_txn_id, status, created_at
            ) VALUES (:pid, :bid, 61, :key, :gw, 'success', now())
            """
        ),
        {
            "pid": pay_id,
            "bid": booking_id,
            "key": f"idem-{uniq.id()}",
            "gw": gateway_txn_id,
        },
    )
    return pay_id


async def _insert_pending_refund(session, pay_id: str, booking_id: str, rid: str) -> None:
    await session.execute(
        text(
            """
            INSERT INTO refunds (
                id, payment_id, booking_id, amount, reason, status,
                attempt_count, next_attempt_at, created_at
            ) VALUES (
                :rid, :pid, :bid, 61, 'customer_cancel', 'pending',
                0, now(), now()
            )
            """
        ),
        {"rid": rid, "pid": pay_id, "bid": booking_id},
    )


def test_create_refund_sync_sends_x_refund_idempotency_header(monkeypatch):
    captured: dict = {}

    class _FakeResponse:
        status_code = 200

        def json(self):
            return {"id": "rfnd_test123"}

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, url, json=None, headers=None, auth=None):
            captured["headers"] = headers
            captured["url"] = url
            return _FakeResponse()

    monkeypatch.setattr(httpx, "Client", _FakeClient)
    key = str(uuid.uuid4())
    out = create_refund_sync(
        payment_gateway_id="pay_test",
        amount_paise=6100,
        idempotency_key=key,
    )
    assert out == "rfnd_test123"
    assert captured["headers"][REFUND_IDEMPOTENCY_HEADER] == key
    assert "X-Razorpay-Idempotency" not in captured["headers"]


def test_create_refund_sync_400_is_permanent(monkeypatch):
    class _FakeResponse:
        status_code = 400
        text = "bad"

        def json(self):
            return {"error": {"description": "refund not allowed"}}

    class _FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, *args, **kwargs):
            return _FakeResponse()

    monkeypatch.setattr(httpx, "Client", lambda *a, **k: _FakeClient())
    with pytest.raises(RazorpayRefundPermanentError):
        create_refund_sync(
            payment_gateway_id="pay_x",
            amount_paise=100,
            idempotency_key=str(uuid.uuid4()),
        )


def test_create_refund_sync_409_is_retryable(monkeypatch):
    class _FakeResponse:
        status_code = 409
        text = "conflict"

        def json(self):
            return {}

    class _FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, *args, **kwargs):
            return _FakeResponse()

    monkeypatch.setattr(httpx, "Client", lambda *a, **k: _FakeClient())
    with pytest.raises(RazorpayRefundRetryableError):
        create_refund_sync(
            payment_gateway_id="pay_x",
            amount_paise=100,
            idempotency_key=str(uuid.uuid4()),
        )


@pytest.mark.asyncio
async def test_worker_permanent_failed_on_first_pass(session, seed, uniq, monkeypatch):
    bid = await _insert_confirmed_booking(session, uniq)
    pay_id = await _insert_payment(session, bid, uniq, gateway_txn_id=f"pay_{uniq.id()}")
    rid = uniq.id()
    await _insert_pending_refund(session, pay_id, bid, rid)
    await session.commit()

    def _boom(**_kwargs):
        raise RazorpayRefundPermanentError("client error")

    monkeypatch.setattr("app.services.razorpay_client.create_refund_sync", _boom)
    process_refunds(1)

    row = (
        await session.execute(
            text("SELECT status, attempt_count FROM refunds WHERE id = :rid"),
            {"rid": rid},
        )
    ).mappings().first()
    assert row["status"] == "failed_permanent"
    assert row["attempt_count"] == 1


@pytest.mark.asyncio
async def test_worker_missing_gateway_txn_id_permanent(session, seed, uniq, monkeypatch):
    bid = await _insert_confirmed_booking(session, uniq)
    pay_id = await _insert_payment(session, bid, uniq, gateway_txn_id=None)
    rid = uniq.id()
    await _insert_pending_refund(session, pay_id, bid, rid)
    await session.commit()

    calls = []

    def _track(**kwargs):
        calls.append(kwargs)
        return "rfnd_x"

    monkeypatch.setattr("app.services.razorpay_client.create_refund_sync", _track)
    process_refunds(1)

    assert calls == []
    row = (
        await session.execute(
            text("SELECT status FROM refunds WHERE id = :rid"),
            {"rid": rid},
        )
    ).scalar_one()
    assert row == "failed_permanent"


@pytest.mark.asyncio
async def test_worker_retryable_503_stays_pending(session, seed, uniq, monkeypatch):
    bid = await _insert_confirmed_booking(session, uniq)
    pay_id = await _insert_payment(session, bid, uniq, gateway_txn_id=f"pay_{uniq.id()}")
    rid = uniq.id()
    await _insert_pending_refund(session, pay_id, bid, rid)
    await session.commit()

    def _retry(**_kwargs):
        raise RazorpayRefundRetryableError("503 unavailable")

    monkeypatch.setattr("app.services.razorpay_client.create_refund_sync", _retry)
    process_refunds(1)

    row = (
        await session.execute(
            text("SELECT status, attempt_count FROM refunds WHERE id = :rid"),
            {"rid": rid},
        )
    ).mappings().first()
    assert row["status"] == "pending"
    assert row["attempt_count"] == 1


@pytest.mark.asyncio
async def test_worker_retryable_409_stays_pending(session, seed, uniq, monkeypatch):
    bid = await _insert_confirmed_booking(session, uniq)
    pay_id = await _insert_payment(session, bid, uniq, gateway_txn_id=f"pay_{uniq.id()}")
    rid = uniq.id()
    await _insert_pending_refund(session, pay_id, bid, rid)
    await session.commit()

    def _retry(**_kwargs):
        raise RazorpayRefundRetryableError("409 in flight")

    monkeypatch.setattr("app.services.razorpay_client.create_refund_sync", _retry)
    process_refunds(1)

    row = (
        await session.execute(
            text("SELECT status FROM refunds WHERE id = :rid"),
            {"rid": rid},
        )
    ).scalar_one()
    assert row == "pending"
