"""T7 facilitation reversal — proportional FY, ledger, recovery, online refund."""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.models.payment import Payment
from app.services import tds_accrual_service
from app.services.tds_v3_reversal_service import apply_facilitation_reversal
from tests.test_tds_accrual_decouple import (
    PUJARI_ID,
    _apply_tds_at_accept,
    _insert_booking,
    _require_migration_027,
    _require_migration_v3,
    _seed_fy,
    _set_pujari,
)

pytestmark = pytest.mark.booking_fee_launch


async def _require_migration_032(session) -> None:
    row = (
        await session.execute(
            text(
                """
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'pujari_tds_facilitation_ledger'
                  AND column_name = 'refund_reference'
                """
            )
        )
    ).scalar_one_or_none()
    if row is None:
        pytest.skip("migration_032 not applied")


async def _insert_tds_payment(session, booking_id: uuid.UUID, amount: Decimal) -> uuid.UUID:
    import datetime as dt

    pid = uuid.uuid4()
    session.add(
        Payment(
            id=pid,
            booking_id=booking_id,
            amount=float(amount),
            idempotency_key=f"tds:test-{booking_id.hex[:16]}",
            gateway_txn_id=f"pay_tds_{booking_id.hex[:12]}",
            status="success",
            created_at=dt.datetime.now(dt.UTC),
        )
    )
    return pid


async def _fy_totals(session, fy_gross_seed: Decimal) -> tuple[Decimal, Decimal, bool]:
    row = (
        await session.execute(
            text(
                """
                SELECT gross_facilitation, tds_accrued, deduction_latched
                FROM pujari_tax_year
                WHERE pujari_id = :pid
                """
            ),
            {"pid": str(PUJARI_ID)},
        )
    ).one()
    return (
        Decimal(str(row.gross_facilitation)),
        Decimal(str(row.tds_accrued)),
        bool(row.deduction_latched),
    )


@pytest.mark.asyncio
async def test_full_cancel_post_crossing_online_tds_refunded(engine, seed, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "TDS_ACCRUAL_ENABLED", True)
    maker = __import__(
        "sqlalchemy.ext.asyncio", fromlist=["async_sessionmaker"]
    ).async_sessionmaker(engine, expire_on_commit=False)
    booking_id = uuid.uuid4()
    async with maker() as session:
        async with session.begin():
            await _require_migration_027(session)
            await _require_migration_v3(session)
            await _require_migration_032(session)
            await _seed_fy(session, Decimal("510000"))
            await _set_pujari(session)
            await _insert_booking(
                session, booking_id, total_amount=Decimal("3000"), record_balance_at_insert=False
            )
            await _apply_tds_at_accept(session, booking_id, monkeypatch=monkeypatch)
            await _insert_tds_payment(session, booking_id, Decimal("3"))
            await tds_accrual_service.accrue_tds_on_balance_collected(
                session,
                booking_id=booking_id,
                pujari_id=PUJARI_ID,
                gross_amount=Decimal("3000"),
            )
            gross_before, tds_before, latched = await _fy_totals(session, Decimal("510000"))
            assert gross_before == Decimal("513000")
            assert tds_before == Decimal("3")
            assert latched is True

            rev = await apply_facilitation_reversal(
                session,
                booking_id=booking_id,
                pujari_id=PUJARI_ID,
                refund_reference=f"ref:full-cancel:{booking_id}",
                refund_fraction=Decimal("1"),
            )
            assert rev["reversed"] is True
            assert rev["turnover_reversed_inr"] == "3000.00"
            assert rev["tds_reversed_inr"] == "3.00"
            assert rev["customer_refund_inr"] == "3.00"

            gross_after, tds_after, latched_after = await _fy_totals(session, Decimal("510000"))
            assert gross_after == Decimal("510000")
            assert tds_after == Decimal("0")
            assert latched_after is True

            contra = (
                await session.execute(
                    text(
                        """
                        SELECT entry_type, gross_amount, tds_amount, refund_reference
                        FROM pujari_tds_facilitation_ledger
                        WHERE booking_id = :bid AND entry_type = 'reversal'
                        """
                    ),
                    {"bid": str(booking_id)},
                )
            ).one()
            assert contra.refund_reference == f"ref:full-cancel:{booking_id}"
            assert Decimal(str(contra.tds_amount)) == Decimal("3")
            liability = (
                await session.execute(
                    text("SELECT tds_liability_inr FROM bookings WHERE id = :bid"),
                    {"bid": str(booking_id)},
                )
            ).scalar_one()
            assert Decimal(str(liability)) == Decimal("0")


@pytest.mark.asyncio
async def test_partial_50_percent_refunds_cap_third_noop(engine, seed, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "TDS_ACCRUAL_ENABLED", True)
    maker = __import__(
        "sqlalchemy.ext.asyncio", fromlist=["async_sessionmaker"]
    ).async_sessionmaker(engine, expire_on_commit=False)
    booking_id = uuid.uuid4()
    async with maker() as session:
        async with session.begin():
            await _require_migration_027(session)
            await _require_migration_v3(session)
            await _require_migration_032(session)
            await _seed_fy(session, Decimal("510000"))
            await _set_pujari(session)
            await _insert_booking(
                session, booking_id, total_amount=Decimal("3000"), record_balance_at_insert=False
            )
            await _apply_tds_at_accept(session, booking_id, monkeypatch=monkeypatch)
            await _insert_tds_payment(session, booking_id, Decimal("3"))

            r1 = await apply_facilitation_reversal(
                session,
                booking_id=booking_id,
                pujari_id=PUJARI_ID,
                refund_reference=f"ref:half-1:{booking_id}",
                refund_fraction=Decimal("0.5"),
            )
            assert r1["reversed"] is True
            assert r1["turnover_reversed_inr"] == "1500.00"
            assert r1["tds_reversed_inr"] == "1.50"
            assert r1["customer_refund_inr"] == "1.50"

            r2 = await apply_facilitation_reversal(
                session,
                booking_id=booking_id,
                pujari_id=PUJARI_ID,
                refund_reference=f"ref:half-2:{booking_id}",
                refund_fraction=Decimal("0.5"),
            )
            assert r2["reversed"] is True
            assert r2["turnover_reversed_inr"] == "1500.00"
            assert r2["tds_reversed_inr"] == "1.50"

            gross_after, tds_after, _ = await _fy_totals(session, Decimal("510000"))
            assert gross_after == Decimal("510000")
            assert tds_after == Decimal("0")

            r3 = await apply_facilitation_reversal(
                session,
                booking_id=booking_id,
                pujari_id=PUJARI_ID,
                refund_reference=f"ref:half-3:{booking_id}",
                refund_fraction=Decimal("0.5"),
            )
            assert r3["reversed"] is False
            assert "remainder" in r3["reason"].lower() or "nothing" in r3["reason"].lower()


@pytest.mark.asyncio
async def test_recovery_only_reversal_no_customer_refund(engine, seed, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "TDS_ACCRUAL_ENABLED", True)
    monkeypatch.setattr(get_settings(), "TDS_ACCEPT_STUB_COLLECT", False)
    maker = __import__(
        "sqlalchemy.ext.asyncio", fromlist=["async_sessionmaker"]
    ).async_sessionmaker(engine, expire_on_commit=False)
    booking_id = uuid.uuid4()
    async with maker() as session:
        async with session.begin():
            await _require_migration_027(session)
            await _require_migration_v3(session)
            await _require_migration_032(session)
            await _seed_fy(session, Decimal("510000"))
            await _set_pujari(session)
            await _insert_booking(
                session, booking_id, total_amount=Decimal("3000"), record_balance_at_insert=False
            )
            from app.core.config import get_settings
            from app.services.tds_v3_accept_service import apply_tds_at_booking_confirmation

            monkeypatch.setattr(get_settings(), "TDS_ACCEPT_STUB_COLLECT", False)
            monkeypatch.setattr(get_settings(), "RAZORPAY_KEY_ID", "not_configured")
            await apply_tds_at_booking_confirmation(
                session, booking_id=booking_id, pujari_id=PUJARI_ID
            )
            rec = (
                await session.execute(
                    text(
                        "SELECT status FROM pujari_tds_recovery WHERE booking_id = :bid"
                    ),
                    {"bid": str(booking_id)},
                )
            ).scalar_one_or_none()
            assert rec == "pending"

            rev = await apply_facilitation_reversal(
                session,
                booking_id=booking_id,
                pujari_id=PUJARI_ID,
                refund_reference=f"ref:recovery-full:{booking_id}",
                refund_fraction=Decimal("1"),
            )
            assert rev["reversed"] is True
            assert rev["customer_refund_inr"] in ("0", "0.00")
            void = (
                await session.execute(
                    text(
                        "SELECT status FROM pujari_tds_recovery WHERE booking_id = :bid"
                    ),
                    {"bid": str(booking_id)},
                )
            ).scalar_one()
            assert void == "void"


@pytest.mark.asyncio
async def test_no_show_before_balance_blocks_late_accrual(engine, seed, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "TDS_ACCRUAL_ENABLED", True)
    maker = __import__(
        "sqlalchemy.ext.asyncio", fromlist=["async_sessionmaker"]
    ).async_sessionmaker(engine, expire_on_commit=False)
    booking_id = uuid.uuid4()
    async with maker() as session:
        async with session.begin():
            await _require_migration_027(session)
            await _require_migration_v3(session)
            await _require_migration_032(session)
            await _seed_fy(session, Decimal("510000"))
            await _set_pujari(session)
            await _insert_booking(
                session, booking_id, total_amount=Decimal("3000"), record_balance_at_insert=False
            )
            await _apply_tds_at_accept(session, booking_id, monkeypatch=monkeypatch)
            await tds_accrual_service.enqueue_tds_accrual_intent(
                session,
                booking_id=booking_id,
                pujari_id=PUJARI_ID,
                gross_amount=Decimal("3000"),
            )
            rev = await apply_facilitation_reversal(
                session,
                booking_id=booking_id,
                pujari_id=PUJARI_ID,
                refund_reference=f"ref:no-show:{booking_id}",
                refund_fraction=Decimal("1"),
            )
            assert rev["reversed"] is True
            intent = (
                await session.execute(
                    text(
                        "SELECT status FROM pujari_tds_accrual_intents WHERE booking_id = :bid"
                    ),
                    {"bid": str(booking_id)},
                )
            ).scalar_one()
            assert intent == "cancelled"

            with pytest.raises(ValueError, match="accrual blocked"):
                await tds_accrual_service.accrue_tds_on_balance_collected(
                    session,
                    booking_id=booking_id,
                    pujari_id=PUJARI_ID,
                    gross_amount=Decimal("3000"),
                )


@pytest.mark.asyncio
async def test_duplicate_refund_reference_noop(engine, seed, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "TDS_ACCRUAL_ENABLED", True)
    maker = __import__(
        "sqlalchemy.ext.asyncio", fromlist=["async_sessionmaker"]
    ).async_sessionmaker(engine, expire_on_commit=False)
    booking_id = uuid.uuid4()
    async with maker() as session:
        async with session.begin():
            await _require_migration_027(session)
            await _require_migration_v3(session)
            await _require_migration_032(session)
            await _seed_fy(session, Decimal("510000"))
            await _set_pujari(session)
            await _insert_booking(
                session, booking_id, total_amount=Decimal("3000"), record_balance_at_insert=False
            )
            await _apply_tds_at_accept(session, booking_id, monkeypatch=monkeypatch)
            first = await apply_facilitation_reversal(
                session,
                booking_id=booking_id,
                pujari_id=PUJARI_ID,
                refund_reference=f"ref:dup:{booking_id}",
                refund_fraction=Decimal("0.25"),
            )
            assert first["reversed"] is True
            dup = await apply_facilitation_reversal(
                session,
                booking_id=booking_id,
                pujari_id=PUJARI_ID,
                refund_reference=f"ref:dup:{booking_id}",
                refund_fraction=Decimal("0.25"),
            )
            assert dup.get("idempotent") is True
            assert dup["reversed"] is False
