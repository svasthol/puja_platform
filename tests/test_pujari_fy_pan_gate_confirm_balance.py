"""FY PAN gate — confirm-balance warn+allow (no FY 422 on collection)."""
from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import text

from app.api.v1.endpoints import service_lifecycle as lifecycle_ep
from app.core.config import get_settings
from app.core.dependencies import Principal
from app.schemas.booking import BalanceCollected
from app.services import pujari_fy_pan_gate
from tests.test_service_lifecycle_balance import (
    CUSTOMER,
    PUJARI_USER,
    _insert_confirmed_booking,
    _pujari,
    _pujari_id,
)

pytestmark = pytest.mark.booking_fee_launch


async def _set_in_progress(session, bid):
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


@pytest.mark.asyncio
async def test_confirm_balance_allows_block_tier_with_fy_pan_warn_code(
    session, seed, uniq, monkeypatch
):
    from app.core.config import get_settings as gs

    monkeypatch.setattr(gs(), "TDS_ACCRUAL_ENABLED", False)
    monkeypatch.setattr(get_settings(), "PUJARI_FY_PAN_GATE_ENABLED", True)

    async def _high_gross(_db, *, pujari_id, fy_start=None):
        return Decimal("480000")

    monkeypatch.setattr(pujari_fy_pan_gate, "current_fy_facilitation_gross", _high_gross)

    bid = await _insert_confirmed_booking(session, uniq)
    pujari_id = await _pujari_id(session)
    await session.execute(
        text(
            """
            UPDATE pujaris
            SET pan_hash = :ph, pan_status = 'unverified', entity_type = 'individual'
            WHERE id = :pid
            """
        ),
        {"ph": "b" * 64, "pid": str(pujari_id)},
    )
    await _set_in_progress(session, bid)

    resp = await lifecycle_ep.confirm_balance(
        bid,
        BalanceCollected(method="cash"),
        _pujari(),
        session,
    )
    assert resp.status == "collected"
    assert resp.tds is not None
    assert resp.tds.message_code == pujari_fy_pan_gate.FY_PAN_GATE_WARN
    assert resp.tds.message

    collected_at = (
        await session.execute(
            text("SELECT balance_collected_at FROM bookings WHERE id = :bid"),
            {"bid": str(bid)},
        )
    ).scalar_one()
    assert collected_at is not None
