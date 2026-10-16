"""26Q export — ledger net TDS and taxable-base net for a period."""
from __future__ import annotations

import datetime as dt
import os
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import text

from scripts.export_tds_26q import fetch_export_rows
from tests.test_tds_accrual_decouple import PUJARI_ID, _insert_booking

pytestmark = pytest.mark.booking_fee_launch

_MAR_2026 = dt.datetime(2099, 1, 15, 12, 0, 0, tzinfo=dt.UTC)
_MAR_START = dt.datetime(2099, 1, 1, tzinfo=dt.UTC)
_MAR_END = dt.datetime(2099, 1, 31, 23, 59, 59, 999999, tzinfo=dt.UTC)
_APR_2026 = dt.datetime(2099, 2, 10, 12, 0, 0, tzinfo=dt.UTC)
_APR_START = dt.datetime(2099, 2, 1, tzinfo=dt.UTC)
_APR_END = dt.datetime(2099, 2, 28, 23, 59, 59, 999999, tzinfo=dt.UTC)


def _sync_url() -> str:
    url = os.environ.get("DATABASE_URL", "postgresql+psycopg://postgres@127.0.0.1:5433/Mana_Guruji")
    return url.replace("postgresql+psycopg://", "postgresql://").replace(
        "postgresql+asyncpg://", "postgresql://"
    )


async def _insert_ledger_row(
    session,
    *,
    entry_type: str,
    gross: Decimal,
    tds: Decimal,
    created_at: dt.datetime,
    booking_id: uuid.UUID | None = None,
) -> None:
    await session.execute(
        text(
            """
            INSERT INTO pujari_tds_facilitation_ledger (
                id, pujari_id, booking_id, entry_type, gross_amount, tds_amount, fy_start, created_at
            ) VALUES (
                gen_random_uuid(), :pid, :bid, :et, :gross, :tds, '2025-04-01', :created_at
            )
            """
        ),
        {
            "pid": str(PUJARI_ID),
            "bid": str(booking_id) if booking_id else None,
            "et": entry_type,
            "gross": str(gross),
            "tds": str(tds),
            "created_at": created_at,
        },
    )


@pytest.mark.asyncio
async def test_export_ledger_net_two_accruals_one_reversal(engine, seed):
    import psycopg

    maker = __import__(
        "sqlalchemy.ext.asyncio", fromlist=["async_sessionmaker"]
    ).async_sessionmaker(engine, expire_on_commit=False)
    b1, b2, b3 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    async with maker() as session:
        async with session.begin():
            await _insert_booking(session, b1)
            await _insert_booking(session, b2)
            await _insert_booking(session, b3)
            await _insert_ledger_row(
                session,
                entry_type="accrual",
                gross=Decimal("1000"),
                tds=Decimal("10.00"),
                created_at=_MAR_2026,
                booking_id=b1,
            )
            await _insert_ledger_row(
                session,
                entry_type="accrual",
                gross=Decimal("500"),
                tds=Decimal("5.00"),
                created_at=_MAR_2026 + dt.timedelta(days=1),
                booking_id=b2,
            )
            await _insert_ledger_row(
                session,
                entry_type="reversal",
                gross=Decimal("200"),
                tds=Decimal("3.00"),
                created_at=_MAR_2026 + dt.timedelta(days=2),
                booking_id=b3,
            )

    with psycopg.connect(_sync_url()) as conn:
        rows = fetch_export_rows(conn, period_start=_MAR_START, period_end=_MAR_END)

    assert len(rows) == 1
    row = rows[0]
    assert row["pujari_id"] == str(PUJARI_ID)
    assert Decimal(row["amount_on_which_tds_deducted"]) == Decimal("1300.00")
    assert Decimal(row["tds_deducted"]) == Decimal("12.00")
    assert row["first_txn_date"] == "2099-01-15"
    assert row["last_txn_date"] == "2099-01-17"
    assert row["PAN"] == ""
    assert row["section"] == "194-O"


@pytest.mark.asyncio
async def test_export_excludes_fully_reversed_pujari(engine, seed):
    import psycopg

    maker = __import__(
        "sqlalchemy.ext.asyncio", fromlist=["async_sessionmaker"]
    ).async_sessionmaker(engine, expire_on_commit=False)
    bid = uuid.uuid4()
    async with maker() as session:
        async with session.begin():
            await _insert_booking(session, bid)
            await _insert_ledger_row(
                session,
                entry_type="accrual",
                gross=Decimal("100"),
                tds=Decimal("10.00"),
                created_at=_APR_2026,
                booking_id=bid,
            )
            await _insert_ledger_row(
                session,
                entry_type="reversal",
                gross=Decimal("100"),
                tds=Decimal("10.00"),
                created_at=_APR_2026 + dt.timedelta(hours=1),
                booking_id=bid,
            )

    with psycopg.connect(_sync_url()) as conn:
        rows = fetch_export_rows(conn, period_start=_APR_START, period_end=_APR_END)

    assert rows == []


def test_deposit_round_footer_math():
    from app.services.pricing_tds_v3 import deposit_round_inr

    assert deposit_round_inr(Decimal("12.00")) == Decimal("10")
    assert deposit_round_inr(Decimal("15.00")) == Decimal("20")
