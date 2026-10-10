"""Admin TDS compliance endpoints (§0.S S4/S7/S9)."""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.api.v1.endpoints import admin_tds as admin_tds_ep
from app.core.dependencies import Principal
from app.schemas.admin_tds import TdsCorrectOfflineCollectionRequest
from app.services import tds_accrual_service

CUSTOMER = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001")
PUJARI_USER = uuid.UUID("bbbbbbbb-0000-0000-0000-000000000001")
PUJARI_ID = uuid.UUID("cccccccc-0000-0000-0000-000000000001")
ADDRESS = uuid.UUID("dddddddd-0000-0000-0000-000000000001")
PUJA = uuid.UUID("11111111-1111-1111-1111-111111111111")


class _FakeRequest:
    client = None


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


async def _mk_admin(session) -> Principal:
    uid = uuid.uuid4()
    await session.execute(
        text("INSERT INTO users (id, full_name, phone) VALUES (:id, 'A', :ph)"),
        {"id": str(uid), "ph": "+91990" + uuid.uuid4().hex[:7]},
    )
    return Principal(user_id=uid, app_context="admin", roles=("admin",))


@pytest.mark.asyncio
async def test_compliance_backlog_empty(session, seed):
    await _require_027(session)
    admin = await _mk_admin(session)
    resp = await admin_tds_ep.get_compliance_backlog(_FakeRequest(), 50, admin, session)
    assert resp.parked_count >= 0
    assert resp.pending_count >= 0


@pytest.mark.asyncio
async def test_fy_reconcile_endpoint(session, seed):
    admin = await _mk_admin(session)
    resp = await admin_tds_ep.get_fy_reconcile(_FakeRequest(), admin, session)
    assert isinstance(resp.green, bool)


@pytest.mark.asyncio
async def test_correct_offline_collection_clear(session, seed, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "TDS_ACCRUAL_ENABLED", True)
    await _require_027(session)
    admin = await _mk_admin(session)
    bid = uuid.uuid4()
    h = int(bid.hex[:12], 16)
    await session.execute(
        text(
            """
            INSERT INTO bookings (
                id, user_id, pujari_id, intended_pujari_id, puja_id, address_id, status_id,
                cancellation_policy_id, scheduled_date, scheduled_time, duration_minutes,
                total_amount, amount_due_online, amount_due_offline, booking_fee,
                payment_mode, paid_at, dispatch_mode, balance_collected_at,
                balance_collected_by, balance_collection_method, balance_collected_amount,
                created_at, updated_at
            )
            SELECT
                :bid, :uid, :pid, :pid, :puja, :addr, st.id,
                (SELECT id FROM cancellation_policies WHERE name='standard'),
                current_date + 600, CAST('10:00' AS time), 90, 2100, 0, 2100, 61,
                'booking_fee', now(), 'broadcast', now(),
                :puid, 'cash', 2100, now(), now()
            FROM status_types st
            WHERE st.domain = 'booking' AND st.code = 'in_progress'
            """
        ),
        {
            "bid": str(bid),
            "uid": str(CUSTOMER),
            "pid": str(PUJARI_ID),
            "puja": str(PUJA),
            "addr": str(ADDRESS),
            "puid": str(PUJARI_USER),
        },
    )
    await session.execute(
        text(
            """
            UPDATE pujaris
            SET entity_type = 'individual', pan_hash = :ph, pan_status = 'operative'
            WHERE id = :pid
            """
        ),
        {"ph": "d" * 64, "pid": str(PUJARI_ID)},
    )
    await session.commit()

    async with session.begin():
        await tds_accrual_service.accrue_tds_on_balance_collected(
            session,
            booking_id=bid,
            pujari_id=PUJARI_ID,
            gross_amount=Decimal("2100"),
        )

    resp = await admin_tds_ep.post_correct_offline_collection(
        bid,
        TdsCorrectOfflineCollectionRequest(action="clear", change_reason="test correction"),
        _FakeRequest(),
        admin,
        session,
    )
    assert resp.balance_collected_at is None
    assert resp.tds_reversal is not None
