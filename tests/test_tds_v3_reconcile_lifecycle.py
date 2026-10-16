"""TDS v3 reconcile helpers + lifecycle + readiness-style checks."""
from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.core.config import get_settings
from app.models.payment import Payment
from app.services import tds_accrual_service
from app.services.tds_ledger_net_sql import (
    BOOKING_LEDGER_TDS_NET_EXPR,
    LEDGER_TDS_NET_EXPR,
)
from app.services.tds_accrual_service import fy_start_for_date
from app.services.tds_v3_reversal_service import (
    apply_facilitation_reversal,
)
from tests.test_tds_accrual_decouple import (
    ADDRESS_ID,
    CUSTOMER_ID,
    PUJARI_ID,
    PUJA_ID,
    _apply_tds_at_accept,
    _insert_booking,
    _require_migration_027,
    _require_migration_v3,
    _seed_fy,
    _set_pujari,
)

pytestmark = pytest.mark.booking_fee_launch


async def _require_v3_chain(session) -> None:
    await _require_migration_027(session)
    await _require_migration_v3(session)
    for col, table in (
        ("tds_liability_inr", "bookings"),
        ("tds_online_charge_closed_at", "bookings"),
        ("refund_reference", "pujari_tds_facilitation_ledger"),
    ):
        row = (
            await session.execute(
                text(
                    """
                    SELECT 1 FROM information_schema.columns
                    WHERE table_schema = 'public'
                      AND table_name = :t
                      AND column_name = :c
                    """
                ),
                {"t": table, "c": col},
            )
        ).scalar_one_or_none()
        if row is None:
            pytest.skip(f"migration chain incomplete — missing {table}.{col}")


async def _pujari_fy_tds_ledger_pair(
    session, pujari_id: uuid.UUID, fy_start
) -> tuple[Decimal, Decimal]:
    row = (
        await session.execute(
            text(
                f"""
                SELECT ty.tds_accrued AS acc,
                       {LEDGER_TDS_NET_EXPR} AS net
                FROM pujari_tax_year ty
                LEFT JOIN pujari_tds_facilitation_ledger l
                       ON l.pujari_id = ty.pujari_id AND l.fy_start = ty.fy_start
                WHERE ty.pujari_id = :pid AND ty.fy_start = :fy
                GROUP BY ty.pujari_id, ty.fy_start, ty.tds_accrued
                """
            ),
            {"pid": str(pujari_id), "fy": fy_start},
        )
    ).mappings().first()
    if row is None:
        return Decimal("0"), Decimal("0")
    acc = Decimal(str(row["acc"] or 0)).quantize(Decimal("0.01"))
    net = Decimal(str(row["net"] or 0)).quantize(Decimal("0.01"))
    return acc, net


async def _pujari_fy_tds_matches_ledger(session, pujari_id: uuid.UUID, fy_start) -> bool:
    acc, net = await _pujari_fy_tds_ledger_pair(session, pujari_id, fy_start)
    return acc == net


async def _booking_ledger_tds_net(session, booking_id: uuid.UUID) -> Decimal:
    row = (
        await session.execute(
            text(
                f"""
                SELECT {BOOKING_LEDGER_TDS_NET_EXPR} AS net
                FROM pujari_tds_facilitation_ledger
                WHERE booking_id = :bid
                """
            ),
            {"bid": str(booking_id)},
        )
    ).scalar_one()
    return Decimal(str(row or 0)).quantize(Decimal("0.01"))


async def _insert_tds_payment(session, booking_id: uuid.UUID, amount: Decimal) -> None:
    session.add(
        Payment(
            id=uuid.uuid4(),
            booking_id=booking_id,
            amount=float(amount),
            idempotency_key=f"tds:life-{booking_id.hex[:16]}",
            gateway_txn_id=f"gw_{booking_id.hex[:12]}",
            status="success",
            created_at=dt.datetime.now(dt.UTC),
        )
    )


@pytest.mark.asyncio
async def test_full_accrue_then_full_reverse_ledger_tds_net_zero(engine, seed, monkeypatch):
    monkeypatch.setattr(get_settings(), "TDS_ACCRUAL_ENABLED", True)
    maker = __import__(
        "sqlalchemy.ext.asyncio", fromlist=["async_sessionmaker"]
    ).async_sessionmaker(engine, expire_on_commit=False)
    booking_id = uuid.uuid4()
    async with maker() as session:
        async with session.begin():
            await _require_v3_chain(session)
            await _seed_fy(session, Decimal("510000"))
            await _set_pujari(session)
            fy_start = fy_start_for_date(dt.date.today())
            tds_before, net_before = await _pujari_fy_tds_ledger_pair(
                session, PUJARI_ID, fy_start
            )
            await _insert_booking(session, booking_id, total_amount=Decimal("3000"))
            await _apply_tds_at_accept(session, booking_id, monkeypatch=monkeypatch)
            await tds_accrual_service.accrue_tds_on_balance_collected(
                session,
                booking_id=booking_id,
                pujari_id=PUJARI_ID,
                gross_amount=Decimal("3000"),
            )
            assert await _booking_ledger_tds_net(session, booking_id) == Decimal("3.00")
            await apply_facilitation_reversal(
                session,
                booking_id=booking_id,
                pujari_id=PUJARI_ID,
                refund_reference=f"readiness:full:{booking_id}",
                refund_fraction=Decimal("1"),
            )
            assert await _booking_ledger_tds_net(session, booking_id) == Decimal("0")
            tds_after, net_after = await _pujari_fy_tds_ledger_pair(
                session, PUJARI_ID, fy_start
            )
            assert tds_after - tds_before == Decimal("0")
            assert net_after - net_before == Decimal("0")
            liability = (
                await session.execute(
                    text(
                        "SELECT tds_liability_inr FROM bookings WHERE id = :bid"
                    ),
                    {"bid": str(booking_id)},
                )
            ).scalar_one()
            assert Decimal(str(liability)) == Decimal("0")


@pytest.mark.asyncio
async def test_lifecycle_crossing_collect_half_refund_no_show_sweep(engine, seed, monkeypatch):
    """Accept → collect → 50% reversal → second booking swept; hand-check FY + ledger."""
    monkeypatch.setattr(get_settings(), "TDS_ACCRUAL_ENABLED", True)
    maker = __import__(
        "sqlalchemy.ext.asyncio", fromlist=["async_sessionmaker"]
    ).async_sessionmaker(engine, expire_on_commit=False)
    booking_a = uuid.uuid4()
    booking_b = uuid.uuid4()
    fy_seed = Decimal("510000")
    fy_start = fy_start_for_date(dt.date.today())

    async with maker() as session:
        async with session.begin():
            await _require_v3_chain(session)
            await _seed_fy(session, fy_seed)
            await _set_pujari(session)
            fy_row = (
                await session.execute(
                    text(
                        """
                        SELECT gross_facilitation, tds_accrued
                        FROM pujari_tax_year
                        WHERE pujari_id = :pid AND fy_start = :fy
                        """
                    ),
                    {"pid": str(PUJARI_ID), "fy": fy_start},
                )
            ).one()
            gross_fy_before = Decimal(str(fy_row.gross_facilitation))
            tds_fy_before = Decimal(str(fy_row.tds_accrued or 0))
            _, net_fy_before = await _pujari_fy_tds_ledger_pair(
                session, PUJARI_ID, fy_start
            )
            await _insert_booking(
                session, booking_a, total_amount=Decimal("3000"), record_balance_at_insert=False
            )
            await _apply_tds_at_accept(session, booking_a, monkeypatch=monkeypatch)
            await _insert_tds_payment(session, booking_a, Decimal("3"))
            await tds_accrual_service.accrue_tds_on_balance_collected(
                session,
                booking_id=booking_a,
                pujari_id=PUJARI_ID,
                gross_amount=Decimal("3000"),
            )
            await apply_facilitation_reversal(
                session,
                booking_id=booking_a,
                pujari_id=PUJARI_ID,
                refund_reference=f"life:a:half:{booking_a}",
                refund_fraction=Decimal("0.5"),
            )

            b_day = dt.date(2015, 6, 1) + dt.timedelta(
                days=int(booking_b.hex[:4], 16) % 28
            )
            b_slot = "09:00:00"
            await session.execute(
                text(
                    """
                    INSERT INTO bookings (
                        id, user_id, pujari_id, intended_pujari_id, puja_id, address_id, status_id,
                        cancellation_policy_id, scheduled_date, scheduled_time, duration_minutes,
                        total_amount, amount_due_online, amount_due_offline, booking_fee,
                        payment_mode, paid_at, dispatch_mode, balance_collected_at,
                        balance_collected_by, balance_collection_method, balance_collected_amount,
                        tds_snapshot_entity_type, tds_snapshot_pan_on_file,
                        created_at, updated_at
                    )
                    SELECT
                        :bid, :uid, :pid, :pid, :puja, :addr, st.id,
                        (SELECT id FROM cancellation_policies WHERE name='standard'),
                        :sched_d, CAST(:sched_t AS time), 90, 3000, 0, 3000, 61,
                        'booking_fee', now(), 'broadcast', NULL, NULL, NULL, NULL,
                        NULL, NULL, now(), now()
                    FROM status_types st
                    WHERE st.domain = 'booking' AND st.code = 'confirmed'
                    """
                ),
                {
                    "bid": str(booking_b),
                    "uid": str(CUSTOMER_ID),
                    "pid": str(PUJARI_ID),
                    "puja": str(PUJA_ID),
                    "addr": str(ADDRESS_ID),
                    "sched_d": b_day,
                    "sched_t": b_slot,
                },
            )
            await _apply_tds_at_accept(session, booking_b, monkeypatch=monkeypatch)
            swept = await apply_facilitation_reversal(
                session,
                booking_id=booking_b,
                pujari_id=PUJARI_ID,
                refund_reference=f"life:b:no_collect:{booking_b}",
                refund_fraction=Decimal("1"),
            )
            assert swept["reversed"] is True

    async with maker() as verify:
        fy = (
            await verify.execute(
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
        # b_a: +3000 -1500 turnover; +3 -1.5 tds. b_b: +3000 -3000; +3 -3.
        assert Decimal(str(fy.gross_facilitation)) - gross_fy_before == Decimal("1500")
        assert Decimal(str(fy.tds_accrued)) - tds_fy_before == Decimal("1.50")
        assert fy.deduction_latched is True

        la = (
            await verify.execute(
                text(
                    "SELECT tds_liability_inr, tds_collected_online FROM bookings WHERE id = :bid"
                ),
                {"bid": str(booking_a)},
            )
        ).one()
        assert Decimal(str(la.tds_liability_inr)) == Decimal("1.50")
        assert Decimal(str(la.tds_collected_online)) == Decimal("1.50")

        lb = (
            await verify.execute(
                text(
                    "SELECT tds_liability_inr FROM bookings WHERE id = :bid"
                ),
                {"bid": str(booking_b)},
            )
        ).one()
        assert Decimal(str(lb.tds_liability_inr)) == Decimal("0")

        assert await _booking_ledger_tds_net(verify, booking_a) == Decimal("1.50")
        assert await _booking_ledger_tds_net(verify, booking_b) == Decimal("-3.00")

        tds_b, net_b = await _pujari_fy_tds_ledger_pair(verify, PUJARI_ID, fy_start)
        assert tds_b - tds_fy_before == Decimal("1.50")
        assert net_b - net_fy_before == Decimal("-1.50")
