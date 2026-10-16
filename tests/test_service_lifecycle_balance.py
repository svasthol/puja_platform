"""Partner service lifecycle — balance collection gates (Sprint 1/2)."""
from __future__ import annotations

import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import text

from app.api.v1.endpoints import service_lifecycle as lifecycle_ep
from app.core.dependencies import Principal
from app.schemas.booking import BalanceCollected

CUSTOMER = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001")
PUJARI_USER = uuid.UUID("bbbbbbbb-0000-0000-0000-000000000001")
PUJA = uuid.UUID("11111111-1111-1111-1111-111111111111")
ADDRESS = uuid.UUID("dddddddd-0000-0000-0000-000000000001")


def _pujari() -> Principal:
    return Principal(user_id=PUJARI_USER, app_context="pujari", roles=("pujari",))


async def _pujari_id(session) -> uuid.UUID:
    return uuid.UUID(
        str(
            (
                await session.execute(
                    text("SELECT id FROM pujaris WHERE user_id = :uid"),
                    {"uid": str(PUJARI_USER)},
                )
            ).scalar_one()
        )
    )


async def _insert_confirmed_booking(session, uniq, *, payment_mode: str = "booking_fee") -> uuid.UUID:
    pujari_id = await _pujari_id(session)
    bid = uuid.UUID(uniq.id())
    h = int(bid.hex[:12], 16)
    slot = f"{(h % 12) + 8:02d}:{(h // 12) % 60:02d}:00"
    day_off = 30 + (h % 120)
    await session.execute(
        text(
            """
            INSERT INTO bookings (
                id, user_id, pujari_id, intended_pujari_id, puja_id, address_id, status_id,
                cancellation_policy_id, scheduled_date, scheduled_time, duration_minutes,
                total_amount, amount_due_online, amount_due_offline, booking_fee,
                payment_mode, paid_at, dispatch_mode, created_at, updated_at
            )
            SELECT
                :bid, :uid, :pid, :pid, :puja, :addr, st.id,
                (SELECT id FROM cancellation_policies WHERE name='standard'),
                current_date + :day_off, CAST(:slot AS time), 90, 2100, 0, 2100, 61,
                :pm, now(), 'broadcast', now(), now()
            FROM status_types st
            WHERE st.domain = 'booking' AND st.code = 'confirmed'
            """
        ),
        {
            "bid": str(bid),
            "uid": str(CUSTOMER),
            "pid": str(pujari_id),
            "puja": str(PUJA),
            "addr": str(ADDRESS),
            "day_off": day_off,
            "slot": slot,
            "pm": payment_mode,
        },
    )
    await session.commit()
    return bid


@pytest.mark.asyncio
async def test_confirm_balance_requires_in_progress(session, seed, uniq):
    bid = await _insert_confirmed_booking(session, uniq)
    with pytest.raises(HTTPException) as exc:
        await lifecycle_ep.confirm_balance(
            bid,
            BalanceCollected(method="cash"),
            _pujari(),
            session,
        )
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_confirm_balance_rejects_over_collection(session, seed, uniq, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "TDS_ACCRUAL_ENABLED", True)
    bid = await _insert_confirmed_booking(session, uniq)
    pujari_id = await _pujari_id(session)
    await session.execute(
        text(
            """
            UPDATE pujaris SET entity_type = 'individual', pan_hash = :ph WHERE id = :pid
            """
        ),
        {"ph": "b" * 64, "pid": str(pujari_id)},
    )
    in_progress = (
        await session.execute(
            text("SELECT id FROM status_types WHERE domain='booking' AND code='in_progress'")
        )
    ).scalar_one()
    await session.execute(
        text("UPDATE bookings SET status_id = :sid WHERE id = :bid"),
        {"sid": in_progress, "bid": str(bid)},
    )
    await session.commit()

    with pytest.raises(HTTPException) as exc:
        await lifecycle_ep.confirm_balance(
            bid,
            BalanceCollected(method="cash", amount="3000"),
            _pujari(),
            session,
        )
    assert exc.value.status_code == 422
