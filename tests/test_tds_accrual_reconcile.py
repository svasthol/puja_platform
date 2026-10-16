"""Auto-reconcile failed accrual intents when ledger already exists."""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.services import tds_accrual_service


async def _require_027(session) -> None:
    row = (
        await session.execute(
            text(
                """
                SELECT 1 FROM information_schema.tables
                WHERE table_name = 'pujari_tds_accrual_intents'
                """
            )
        )
    ).scalar_one_or_none()
    if row is None:
        pytest.skip("migration_027 not applied")


@pytest.mark.asyncio
async def test_reconcile_failed_intent_when_ledger_exists(session, seed):
    await _require_027(session)
    intent_id = uuid.uuid4()
    bid_row = (
        await session.execute(
            text("SELECT id, pujari_id FROM bookings WHERE pujari_id IS NOT NULL LIMIT 1")
        )
    ).one_or_none()
    if bid_row is None:
        pytest.skip("no bookings in seed")
    bid = uuid.UUID(str(bid_row.id))
    pujari_id = uuid.UUID(str(bid_row.pujari_id))
    fy = __import__("datetime").date(2026, 4, 1)

    await session.execute(
        text("DELETE FROM pujari_tds_accrual_intents WHERE booking_id = :bid"),
        {"bid": str(bid)},
    )
    await session.execute(
        text(
            """
            INSERT INTO pujari_tds_accrual_intents (
                id, booking_id, pujari_id, gross_amount, collected_at,
                status, last_error, attempt_count
            ) VALUES (
                :iid, :bid, :pid, 2100, now(), 'failed', 'duplicate accrual', 1
            )
            """
        ),
        {"iid": str(intent_id), "bid": str(bid), "pid": str(pujari_id)},
    )
    await session.execute(
        text(
            """
            DELETE FROM pujari_tds_facilitation_ledger
            WHERE booking_id = :bid AND entry_type = 'accrual'
            """
        ),
        {"bid": str(bid)},
    )
    await session.execute(
        text(
            """
            INSERT INTO pujari_tds_facilitation_ledger (
                id, pujari_id, booking_id, entry_type, gross_amount, tds_amount, fy_start
            ) VALUES (
                gen_random_uuid(), :pid, :bid, 'accrual', 100, 0, :fy
            )
            """
        ),
        {"pid": str(pujari_id), "bid": str(bid), "fy": fy},
    )
    await session.commit()

    stats = await tds_accrual_service.reconcile_failed_accrual_intents(session, limit=10)
    assert stats["reconciled"] == 1
    row = (
        await session.execute(
            text("SELECT status, last_error FROM pujari_tds_accrual_intents WHERE id = :iid"),
            {"iid": str(intent_id)},
        )
    ).one()
    assert row.status == "completed"
    assert row.last_error is None
