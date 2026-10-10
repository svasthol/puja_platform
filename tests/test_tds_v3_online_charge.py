"""TDS v3 async checkout vs offline collection (ordering hazard)."""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import text

from tests.test_tds_accrual_decouple import (
    PUJARI_ID,
    _insert_booking,
    _require_migration_027,
    _require_migration_v3,
    _seed_fy,
    _set_pujari,
)

pytestmark = pytest.mark.booking_fee_launch


async def _require_migration_031(session) -> None:
    row = (
        await session.execute(
            text(
                """
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'bookings'
                  AND column_name = 'tds_online_charge_closed_at'
                """
            )
        )
    ).scalar_one_or_none()
    if row is None:
        pytest.skip("migration_031 not applied")


@pytest.mark.asyncio
async def test_finalize_before_offline_closes_order_and_recovery(engine, seed, monkeypatch):
    from app.core.config import get_settings
    from app.services.tds_v3_online_charge import finalize_unresolved_tds_before_offline_collection

    monkeypatch.setattr(get_settings(), "TDS_ACCRUAL_ENABLED", True)
    maker = __import__(
        "sqlalchemy.ext.asyncio", fromlist=["async_sessionmaker"]
    ).async_sessionmaker(engine, expire_on_commit=False)
    booking_id = uuid.uuid4()
    async with maker() as session:
        async with session.begin():
            await _require_migration_027(session)
            await _require_migration_v3(session)
            await _require_migration_031(session)
            await _seed_fy(session, Decimal("510000"))
            await _set_pujari(session)
            await _insert_booking(
                session,
                booking_id,
                total_amount=Decimal("3000"),
                record_balance_at_insert=False,
            )
            await session.execute(
                text(
                    """
                    UPDATE bookings
                    SET tds_liability_inr = 3,
                        tds_collected_online = 0,
                        tds_razorpay_order_id = 'order_pending_tds',
                        tds_facilitation_fy_applied_at = now(),
                        amount_due_offline = 3000,
                        updated_at = now()
                    WHERE id = :bid
                    """
                ),
                {"bid": str(booking_id)},
            )
            await finalize_unresolved_tds_before_offline_collection(
                session, booking_id=booking_id, pujari_id=PUJARI_ID
            )

    async with maker() as verify:
        row = (
            await verify.execute(
                text(
                    """
                    SELECT tds_razorpay_order_id,
                           tds_online_charge_closed_at,
                           amount_due_offline,
                           tds_collected_online
                    FROM bookings WHERE id = :bid
                    """
                ),
                {"bid": str(booking_id)},
            )
        ).one()
        assert row.tds_razorpay_order_id is None
        assert row.tds_online_charge_closed_at is not None
        assert Decimal(str(row.amount_due_offline)) == Decimal("3000")
        assert Decimal(str(row.tds_collected_online)) == Decimal("0")
        rec = (
            await verify.execute(
                text(
                    """
                    SELECT status FROM pujari_tds_recovery WHERE booking_id = :bid
                    """
                ),
                {"bid": str(booking_id)},
            )
        ).scalar_one_or_none()
        assert rec == "pending"


@pytest.mark.asyncio
async def test_late_tds_webhook_after_finalize_queues_refund(engine, seed, monkeypatch):
    from app.core.config import get_settings
    from app.services.tds_v3_online_charge import (
        finalize_unresolved_tds_before_offline_collection,
        handle_tds_payment_webhook,
    )

    monkeypatch.setattr(get_settings(), "TDS_ACCRUAL_ENABLED", True)
    maker = __import__(
        "sqlalchemy.ext.asyncio", fromlist=["async_sessionmaker"]
    ).async_sessionmaker(engine, expire_on_commit=False)
    booking_id = uuid.uuid4()
    order_id = "order_late_pay"
    async with maker() as session:
        async with session.begin():
            await _require_migration_027(session)
            await _require_migration_v3(session)
            await _require_migration_031(session)
            await _seed_fy(session, Decimal("510000"))
            await _set_pujari(session)
            await _insert_booking(
                session,
                booking_id,
                total_amount=Decimal("3000"),
                record_balance_at_insert=False,
            )
            await session.execute(
                text(
                    """
                    UPDATE bookings
                    SET tds_liability_inr = 3,
                        tds_collected_online = 0,
                        tds_razorpay_order_id = :oid,
                        tds_facilitation_fy_applied_at = now(),
                        amount_due_offline = 3000,
                        balance_collected_at = NULL,
                        updated_at = now()
                    WHERE id = :bid
                    """
                ),
                {"bid": str(booking_id), "oid": order_id},
            )
            await finalize_unresolved_tds_before_offline_collection(
                session, booking_id=booking_id, pujari_id=PUJARI_ID
            )
            await session.execute(
                text(
                    """
                    UPDATE bookings
                    SET balance_collected_at = now(),
                        balance_collected_by = (SELECT user_id FROM pujaris WHERE id = :pid),
                        balance_collection_method = 'cash',
                        balance_collected_amount = 3000,
                        tds_snapshot_entity_type = 'individual',
                        tds_snapshot_pan_on_file = true,
                        updated_at = now()
                    WHERE id = :bid
                    """
                ),
                {"bid": str(booking_id), "pid": str(PUJARI_ID)},
            )
            outcome = await handle_tds_payment_webhook(
                session,
                booking_id=booking_id,
                order_id=order_id,
                amount_inr=Decimal("3"),
                gateway_txn_id=f"pay_late_{booking_id.hex[:16]}",
            )
            assert outcome["status"] == "late_capture_refund_queued"

    async with maker() as verify:
        refund = (
            await verify.execute(
                text(
                    """
                    SELECT r.reason, r.status, r.amount
                    FROM refunds r
                    JOIN payments p ON p.id = r.payment_id
                    WHERE r.booking_id = :bid
                    """
                ),
                {"bid": str(booking_id)},
            )
        ).one()
        assert refund.reason == "tds_late_or_double_capture"
        assert refund.status == "pending"
        assert Decimal(str(refund.amount)) == Decimal("3")
