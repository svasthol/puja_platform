"""Sprint 4C slice 3 — A-PROMO, A-DISPUTE, A-MONEY-READ."""
from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import text

from app.api.v1.endpoints import admin_bookings as bookings_ep
from app.api.v1.endpoints import admin_promos as promos_ep
from app.core.dependencies import Principal
from app.schemas.admin_dispute import AdminDisputeRequest
from app.schemas.admin_promos import AdminPromoCreate, AdminPromoUpdate

CUSTOMER = "aaaaaaaa-0000-0000-0000-000000000001"
PUJARI_USER = "bbbbbbbb-0000-0000-0000-000000000001"
ADDRESS = "dddddddd-0000-0000-0000-000000000001"
PUJA = "11111111-1111-1111-1111-111111111111"


class _FakeRequest:
    client = None


def _admin(uid: uuid.UUID) -> Principal:
    return Principal(user_id=uid, app_context="admin", roles=("admin",))


async def _mk_admin(session) -> uuid.UUID:
    uid = uuid.uuid4()
    await session.execute(
        text("INSERT INTO users (id, full_name, phone) VALUES (:id, 'Admin', :ph)"),
        {"id": str(uid), "ph": "+91975" + uuid.uuid4().hex[:7]},
    )
    return uid


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


async def _insert_in_progress_booking(session, uniq) -> str:
    pujari_id = await _pujari_id(session)
    bid = uniq.id()
    slot_time = _unique_slot_time(uniq)
    await session.execute(
        text(
            """
            INSERT INTO bookings (
                id, user_id, pujari_id, intended_pujari_id, puja_id, address_id, status_id,
                cancellation_policy_id, scheduled_date, scheduled_time, duration_minutes,
                total_amount, amount_due_online, amount_due_offline, payment_mode, paid_at,
                dispatch_mode, created_at, updated_at
            )
            SELECT
                :bid, :uid, :pid, :pid, :puja, :addr, st.id,
                (SELECT id FROM cancellation_policies WHERE name='standard'),
                :d, CAST(:t AS time), 90, 2100, 250, 1850, 'advance_balance', now(),
                'broadcast', now(), now()
            FROM status_types st
            WHERE st.domain = 'booking' AND st.code = 'in_progress'
            """
        ),
        {
            "bid": bid,
            "uid": CUSTOMER,
            "pid": pujari_id,
            "puja": PUJA,
            "addr": ADDRESS,
            "d": uniq.date,
            "t": slot_time,
        },
    )
    await session.commit()
    return bid


async def _insert_success_payment(session, booking_id: str, uniq, *, amount: str = "250") -> str:
    pay_id = uniq.id()
    await session.execute(
        text(
            """
            INSERT INTO payments (
                id, booking_id, amount, idempotency_key, gateway_txn_id, status, created_at
            ) VALUES (:pid, :bid, :amt, :key, :gw, 'success', now())
            """
        ),
        {
            "pid": pay_id,
            "bid": booking_id,
            "amt": amount,
            "key": f"idem-{uniq.id()}",
            "gw": f"pay_{uniq.id()}",
        },
    )
    await session.commit()
    return pay_id


@pytest.mark.asyncio
async def test_create_promo_code(session, seed, uniq):
    actor = await _mk_admin(session)
    await session.commit()
    now = dt.datetime.now(dt.UTC)
    resp = await promos_ep.create_promo(
        AdminPromoCreate(
            code=f"TEST{uniq.id()[:6].upper()}",
            discount_pct=10,
            max_uses_per_user=2,
            valid_from=now,
            valid_until=now + dt.timedelta(days=30),
            is_active=True,
        ),
        _FakeRequest(),
        _admin(actor),
        session,
    )
    await session.commit()
    assert resp.discount_pct == 10
    assert resp.is_active is True
    assert resp.redemption_count == 0


@pytest.mark.asyncio
async def test_create_promo_invalid_date_range(session, seed, uniq):
    actor = await _mk_admin(session)
    await session.commit()
    now = dt.datetime.now(dt.UTC)
    with pytest.raises(ValidationError):
        AdminPromoCreate(
            code=f"BAD{uniq.id()[:6].upper()}",
            discount_pct=10,
            valid_from=now,
            valid_until=now - dt.timedelta(hours=1),
        )


@pytest.mark.asyncio
async def test_update_promo_deactivate(session, seed, uniq):
    actor = await _mk_admin(session)
    await session.commit()
    now = dt.datetime.now(dt.UTC)
    created = await promos_ep.create_promo(
        AdminPromoCreate(
            code=f"OFF{uniq.id()[:6].upper()}",
            discount_pct=15,
            valid_from=now,
            valid_until=now + dt.timedelta(days=7),
        ),
        _FakeRequest(),
        _admin(actor),
        session,
    )
    await session.commit()

    updated = await promos_ep.update_promo(
        created.id,
        AdminPromoUpdate(is_active=False),
        _FakeRequest(),
        _admin(actor),
        session,
    )
    await session.commit()
    assert updated.is_active is False


@pytest.mark.asyncio
async def test_dispute_in_progress_booking(session, seed, uniq):
    bid = await _insert_in_progress_booking(session, uniq)
    actor = await _mk_admin(session)
    await session.commit()

    resp = await bookings_ep.dispute_booking(
        uuid.UUID(bid),
        AdminDisputeRequest(
            change_reason="Customer reports offline balance not collected",
            dispute_type="offline_non_payment",
        ),
        _FakeRequest(),
        _admin(actor),
        session,
    )
    await session.commit()

    assert resp.status == "disputed"
    assert resp.previous_status == "in_progress"
    assert resp.offline_balance_note is not None

    status_row = (
        await session.execute(
            text(
                """
                SELECT st.code FROM bookings b
                JOIN status_types st ON st.id = b.status_id
                WHERE b.id = :bid
                """
            ),
            {"bid": bid},
        )
    ).scalar_one()
    assert status_row == "disputed"


@pytest.mark.asyncio
async def test_dispute_rejects_confirmed_booking(session, seed, uniq):
    from tests.test_admin_slice2 import _insert_confirmed_with_accepted_assignment

    bid, _ = await _insert_confirmed_with_accepted_assignment(session, uniq)
    actor = await _mk_admin(session)
    await session.commit()

    with pytest.raises(HTTPException) as exc:
        await bookings_ep.dispute_booking(
            uuid.UUID(bid),
            AdminDisputeRequest(change_reason="ops test"),
            _FakeRequest(),
            _admin(actor),
            session,
        )
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_booking_money_read(session, seed, uniq):
    bid = await _insert_in_progress_booking(session, uniq)
    await _insert_success_payment(session, bid, uniq, amount="250")
    actor = await _mk_admin(session)
    await session.commit()

    money = await bookings_ep.get_booking_money(
        uuid.UUID(bid),
        _FakeRequest(),
        _admin(actor),
        session,
    )

    assert money.booking_id == uuid.UUID(bid)
    assert money.payment_mode == "advance_balance"
    assert money.amount_due_online == Decimal("250")
    assert money.amount_due_offline == Decimal("1850")
    assert money.online_settlement_label == "Collected online — settlement pending"
    assert money.offline_balance_note is not None
    assert len(money.payments) == 1
    assert money.payments[0].settlement_label == "Collected online — settlement pending"
    assert money.refundable_remaining_online == Decimal("250")
