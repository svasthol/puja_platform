"""FY PAN gate — operative PAN required at ₹5L block tier."""
from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import text

from app.core.config import get_settings
from app.services import pujari_fy_pan_gate
from app.services.pujari_fy_pan_gate import assert_fy_pan_gate_allowed
from tests.test_tds_accrual_decouple import PUJARI_ID

pytestmark = pytest.mark.booking_fee_launch


@pytest.mark.asyncio
async def test_fy_pan_gate_blocks_inoperative_pan_hash_at_projected_five_lakh(engine, seed, monkeypatch):
    monkeypatch.setattr(get_settings(), "PUJARI_FY_PAN_GATE_ENABLED", True)

    maker = __import__(
        "sqlalchemy.ext.asyncio", fromlist=["async_sessionmaker"]
    ).async_sessionmaker(engine, expire_on_commit=False)

    async def _high_gross(_db, *, pujari_id, fy_start=None):
        return Decimal("480000")

    monkeypatch.setattr(pujari_fy_pan_gate, "current_fy_facilitation_gross", _high_gross)

    async with maker() as session:
        async with session.begin():
            await session.execute(
                text(
                    """
                    UPDATE pujaris
                    SET pan_hash = :ph, pan_status = 'unverified', entity_type = 'individual'
                    WHERE id = :pid
                    """
                ),
                {"ph": "b" * 64, "pid": str(PUJARI_ID)},
            )

    async with maker() as session:
        with pytest.raises(HTTPException) as exc:
            await assert_fy_pan_gate_allowed(
                session,
                pujari_id=PUJARI_ID,
                additional_collection_inr=Decimal("30000"),
            )
        assert exc.value.status_code == 422
        detail = exc.value.detail
        assert isinstance(detail, dict)
        assert detail.get("code") == pujari_fy_pan_gate.FY_PAN_GATE_BLOCKED


@pytest.mark.asyncio
async def test_fy_pan_gate_status_treats_operative_as_pan_on_file(engine, seed, monkeypatch):
    maker = __import__(
        "sqlalchemy.ext.asyncio", fromlist=["async_sessionmaker"]
    ).async_sessionmaker(engine, expire_on_commit=False)

    async def _at_five_lakh(_db, *, pujari_id, fy_start=None):
        return Decimal("520000")

    monkeypatch.setattr(pujari_fy_pan_gate, "current_fy_facilitation_gross", _at_five_lakh)

    async with maker() as session:
        async with session.begin():
            await session.execute(
                text(
                    """
                    UPDATE pujaris
                    SET pan_hash = :ph, pan_status = 'operative', entity_type = 'individual'
                    WHERE id = :pid
                    """
                ),
                {"ph": "c" * 64, "pid": str(PUJARI_ID)},
            )

    async with maker() as session:
        status = await pujari_fy_pan_gate.fy_pan_gate_status_for_pujari(
            session, pujari_id=PUJARI_ID
        )
        assert status.level == "ok"
        assert status.pan_on_file is True
