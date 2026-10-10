"""Sprint 2 TDS accrual integration tests (live PostgreSQL, migration 025)."""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.services import tds_accrual_service

pytestmark = pytest.mark.booking_fee_launch

PUJARI_ID = uuid.UUID("cccccccc-0000-0000-0000-000000000001")
CUSTOMER_ID = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001")
ADDRESS_ID = uuid.UUID("dddddddd-0000-0000-0000-000000000001")
PUJA_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")


async def _require_migration_025(session) -> None:
    row = (
        await session.execute(
            text(
                """
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'pujari_tax_year'
                """
            )
        )
    ).scalar_one_or_none()
    if row is None:
        pytest.skip("migration_025 not applied — run: python scripts/apply_migration_025.py")


async def _set_pujari_compliance(
    session,
    *,
    entity_type: str | None = "individual",
    pan_on_file: bool = True,
) -> None:
    pan_hash = "a" * 64 if pan_on_file else None
    pan_status = "operative" if pan_on_file else "unverified"
    await session.execute(
        text(
            """
            UPDATE pujaris
            SET entity_type = :et, pan_hash = :ph, pan_status = :ps
            WHERE id = :pid
            """
        ),
        {"et": entity_type, "ph": pan_hash, "ps": pan_status, "pid": str(PUJARI_ID)},
    )


def _unique_pan() -> str:
    digits = int(uuid.uuid4().hex[:8], 16) % 10000
    return f"ABCDE{digits:04d}F"


async def _insert_booking(
    session, booking_id: uuid.UUID, *, total_amount: Decimal = Decimal("2100")
) -> None:
    h = int(booking_id.hex[:12], 16)
    slot_time = f"{(h % 12) + 8:02d}:{(h // 12) % 60:02d}:00"
    day_offset = 500 + (h % 300)
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
                current_date + :day_off, CAST(:slot AS time), 90, :total, 0, :total, 61,
                'booking_fee', now(), 'broadcast', now(), now()
            FROM status_types st
            WHERE st.domain = 'booking' AND st.code = 'confirmed'
            ON CONFLICT (id) DO NOTHING
            """
        ),
        {
            "bid": str(booking_id),
            "uid": str(CUSTOMER_ID),
            "pid": str(PUJARI_ID),
            "puja": str(PUJA_ID),
            "addr": str(ADDRESS_ID),
            "day_off": day_offset,
            "slot": slot_time,
            "total": str(total_amount),
        },
    )


async def _seed_fy_gross(session, gross: Decimal) -> None:
    fy_start = tds_accrual_service.fy_start_for_date(
        __import__("datetime").date.today()
    )
    await session.execute(
        text(
            """
            INSERT INTO pujari_tax_year (pujari_id, fy_start, gross_facilitation, tds_accrued)
            VALUES (:pid, :fy, :gross, 0)
            ON CONFLICT (pujari_id, fy_start) DO UPDATE
            SET gross_facilitation = :gross,
                tds_accrued = 0,
                deduction_latched = false,
                updated_at = now()
            """
        ),
        {"pid": str(PUJARI_ID), "fy": fy_start, "gross": str(gross)},
    )


@pytest.mark.asyncio
async def test_accrual_crosses_five_lakh_threshold(engine, seed, monkeypatch):
    """TDS accrues when FY gross crosses admin threshold."""
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "TDS_ACCRUAL_ENABLED", True)

    maker = __import__("sqlalchemy.ext.asyncio", fromlist=["async_sessionmaker"]).async_sessionmaker(
        engine, expire_on_commit=False
    )
    booking_id = uuid.uuid4()
    async with maker() as session:
        async with session.begin():
            await _require_migration_025(session)
            await _set_pujari_compliance(session)
            from tests.test_tds_accrual_decouple import (
                _apply_tds_at_accept,
                _insert_booking as insert_v3,
                _require_migration_v3,
            )

            await insert_v3(
                session, booking_id, total_amount=Decimal("20000"), record_balance_at_insert=False
            )
            await _seed_fy_gross(session, Decimal("490000"))
            await _require_migration_v3(session)
            await _apply_tds_at_accept(session, booking_id, monkeypatch=monkeypatch)
            result = await tds_accrual_service.accrue_tds_on_balance_collected(
                session,
                booking_id=booking_id,
                pujari_id=PUJARI_ID,
                gross_amount=Decimal("20000"),
            )
            assert result["accrual_enabled"] is True
            assert result["skipped"] is False
            assert result["tds_amount"] == "10.00"
            assert result["tds_rate"] == "0.001"

            ledger = (
                await session.execute(
                    text(
                        """
                        SELECT gross_amount, tds_amount
                        FROM pujari_tds_facilitation_ledger
                        WHERE booking_id = :bid AND entry_type = 'accrual'
                        """
                    ),
                    {"bid": str(booking_id)},
                )
            ).mappings().first()
            assert Decimal(str(ledger["gross_amount"])) == Decimal("10000.00")
            assert Decimal(str(ledger["tds_amount"])) == Decimal("10.00")

            row = (
                await session.execute(
                    text(
                        """
                        SELECT gross_facilitation, tds_accrued
                        FROM pujari_tax_year
                        WHERE pujari_id = :pid
                        """
                    ),
                    {"pid": str(PUJARI_ID)},
                )
            ).mappings().first()
            assert Decimal(str(row["gross_facilitation"])) == Decimal("510000")
            assert Decimal(str(row["tds_accrued"])) == Decimal("10.00")


@pytest.mark.asyncio
async def test_accrual_idempotent_per_booking(engine, seed, monkeypatch):
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "TDS_ACCRUAL_ENABLED", True)

    maker = __import__("sqlalchemy.ext.asyncio", fromlist=["async_sessionmaker"]).async_sessionmaker(
        engine, expire_on_commit=False
    )
    booking_id = uuid.uuid4()
    async with maker() as session:
        async with session.begin():
            await _require_migration_025(session)
            await _set_pujari_compliance(session)
            from tests.test_tds_accrual_decouple import (
                _apply_tds_at_accept,
                _insert_booking as insert_v3,
                _require_migration_v3,
            )

            await insert_v3(session, booking_id, record_balance_at_insert=False)
            await _require_migration_v3(session)
            await _apply_tds_at_accept(session, booking_id, monkeypatch=monkeypatch)
            first = await tds_accrual_service.accrue_tds_on_balance_collected(
                session,
                booking_id=booking_id,
                pujari_id=PUJARI_ID,
                gross_amount=Decimal("2100"),
            )
            second = await tds_accrual_service.accrue_tds_on_balance_collected(
                session,
                booking_id=booking_id,
                pujari_id=PUJARI_ID,
                gross_amount=Decimal("2100"),
            )
            assert first["idempotent"] is False
            assert second["idempotent"] is True
            count = (
                await session.execute(
                    text(
                        """
                        SELECT count(*) FROM pujari_tds_facilitation_ledger
                        WHERE booking_id = :bid AND entry_type = 'accrual'
                        """
                    ),
                    {"bid": str(booking_id)},
                )
            ).scalar_one()
            assert count == 1


@pytest.mark.asyncio
async def test_accrual_skipped_when_flag_off(engine, seed, monkeypatch):
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "TDS_ACCRUAL_ENABLED", False)

    maker = __import__("sqlalchemy.ext.asyncio", fromlist=["async_sessionmaker"]).async_sessionmaker(
        engine, expire_on_commit=False
    )
    async with maker() as session:
        async with session.begin():
            await _require_migration_025(session)
            result = await tds_accrual_service.accrue_tds_on_balance_collected(
                session,
                booking_id=uuid.uuid4(),
                pujari_id=PUJARI_ID,
                gross_amount=Decimal("2100"),
            )
            assert result["skipped"] is True


@pytest.mark.asyncio
async def test_reversal_restores_fy_totals(engine, seed, monkeypatch):
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "TDS_ACCRUAL_ENABLED", True)

    maker = __import__("sqlalchemy.ext.asyncio", fromlist=["async_sessionmaker"]).async_sessionmaker(
        engine, expire_on_commit=False
    )
    booking_id = uuid.uuid4()
    async with maker() as session:
        async with session.begin():
            await _require_migration_025(session)
            await _set_pujari_compliance(session)
            from tests.test_tds_accrual_decouple import (
                _apply_tds_at_accept,
                _insert_booking,
                _require_migration_v3,
            )

            await _insert_booking(session, booking_id, record_balance_at_insert=False)
            await _seed_fy_gross(session, Decimal("510000"))
            await _require_migration_v3(session)
            await _apply_tds_at_accept(session, booking_id, monkeypatch=monkeypatch)
            await tds_accrual_service.accrue_tds_on_balance_collected(
                session,
                booking_id=booking_id,
                pujari_id=PUJARI_ID,
                gross_amount=Decimal("3000"),
            )
            rev = await tds_accrual_service.reverse_tds_on_cancel(
                session, booking_id=booking_id, pujari_id=PUJARI_ID
            )
            assert rev["reversed"] is True
            row = (
                await session.execute(
                    text(
                        """
                        SELECT gross_facilitation, tds_accrued
                        FROM pujari_tax_year
                        WHERE pujari_id = :pid
                        """
                    ),
                    {"pid": str(PUJARI_ID)},
                )
            ).mappings().first()
            assert Decimal(str(row["gross_facilitation"])) == Decimal("510000")
            assert Decimal(str(row["tds_accrued"])) == Decimal("0")


@pytest.mark.asyncio
async def test_reverse_if_accrued_lookup(engine, seed, monkeypatch):
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "TDS_ACCRUAL_ENABLED", True)

    maker = __import__("sqlalchemy.ext.asyncio", fromlist=["async_sessionmaker"]).async_sessionmaker(
        engine, expire_on_commit=False
    )
    booking_id = uuid.uuid4()
    async with maker() as session:
        async with session.begin():
            await _require_migration_025(session)
            await _set_pujari_compliance(session)
            from tests.test_tds_accrual_decouple import (
                _apply_tds_at_accept,
                _insert_booking as insert_v3,
                _require_migration_v3,
                _seed_fy,
            )

            await _seed_fy(session, Decimal("510000"))
            await insert_v3(
                session, booking_id, total_amount=Decimal("3000"), record_balance_at_insert=False
            )
            await _require_migration_v3(session)
            await _apply_tds_at_accept(session, booking_id, monkeypatch=monkeypatch)
            await tds_accrual_service.accrue_tds_on_balance_collected(
                session,
                booking_id=booking_id,
                pujari_id=PUJARI_ID,
                gross_amount=Decimal("3000"),
            )
            rev = await tds_accrual_service.reverse_tds_if_accrued(
                session, booking_id=booking_id
            )
            assert rev["reversed"] is True
            again = await tds_accrual_service.reverse_tds_if_accrued(
                session, booking_id=booking_id
            )
            assert again["reversed"] is False


@pytest.mark.asyncio
async def test_pujari_compliance_update(engine, seed):
    from app.services.pujari_compliance import hash_pan, update_tax_compliance, validate_pan

    pan = _unique_pan()
    assert validate_pan(pan) == pan
    maker = __import__("sqlalchemy.ext.asyncio", fromlist=["async_sessionmaker"]).async_sessionmaker(
        engine, expire_on_commit=False
    )
    async with maker() as session:
        async with session.begin():
            await _require_migration_025(session)
            result = await update_tax_compliance(
                session,
                pujari_id=PUJARI_ID,
                entity_type="individual",
                pan=pan,
            )
            assert result["entity_type"] == "individual"
            assert result["pan_on_file"] is True
            row = (
                await session.execute(
                    text("SELECT pan_hash FROM pujaris WHERE id = :pid"),
                    {"pid": str(PUJARI_ID)},
                )
            ).scalar_one()
            assert row == hash_pan(pan)


@pytest.mark.asyncio
async def test_fy_tax_summary(engine, seed, monkeypatch):
    from app.core.config import get_settings
    from app.services import pujari_fy_pan_gate
    from app.services.pricing import load_tds_facilitation_config

    settings = get_settings()
    monkeypatch.setattr(settings, "TDS_ACCRUAL_ENABLED", True)

    maker = __import__("sqlalchemy.ext.asyncio", fromlist=["async_sessionmaker"]).async_sessionmaker(
        engine, expire_on_commit=False
    )

    async def _booking_gross(_db, *, pujari_id, fy_start=None):
        return Decimal("0")

    monkeypatch.setattr(
        pujari_fy_pan_gate, "current_fy_facilitation_gross", _booking_gross
    )

    async with maker() as session:
        async with session.begin():
            await _require_migration_025(session)
            await _set_pujari_compliance(session, pan_on_file=True)
            await _seed_fy_gross(session, Decimal("100000"))
            summary = await tds_accrual_service.pujari_fy_tax_summary(
                session, pujari_id=PUJARI_ID
            )
            assert summary["fy_gross_facilitation"] == "100000.00"
            assert Decimal(summary["threshold_remaining_inr"]) == Decimal("400000.00")
            assert "remaining" in summary["message"].lower()

            booking_gross = Decimal("2100")
            ledger_gross = Decimal("1000")

            async def _booking_gross_high(_db, *, pujari_id, fy_start=None):
                return booking_gross

            monkeypatch.setattr(
                pujari_fy_pan_gate, "current_fy_facilitation_gross", _booking_gross_high
            )
            await _seed_fy_gross(session, ledger_gross)
            cfg = await load_tds_facilitation_config(session)
            expected_fy = max(ledger_gross, booking_gross).quantize(Decimal("0.01"))
            summary_max = await tds_accrual_service.pujari_fy_tax_summary(
                session, pujari_id=PUJARI_ID
            )
            assert summary_max["fy_gross_facilitation"] == str(expected_fy)
            assert summary_max["fy_gross_facilitation"] == "2100.00"
            remaining = max(
                Decimal("0"),
                (cfg.individual_fy_threshold_inr - expected_fy).quantize(Decimal("0.01")),
            )
            assert Decimal(summary_max["threshold_remaining_inr"]) == remaining
