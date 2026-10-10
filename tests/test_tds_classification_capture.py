"""§0.L-4 — TDS classification snapshot at balance collection (migration 026)."""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.api.v1.endpoints import service_lifecycle as lifecycle_ep
from app.core.dependencies import Principal
from app.schemas.booking import BalanceCollected
from app.services import tds_accrual_service

CUSTOMER = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001")
PUJARI_USER = uuid.UUID("bbbbbbbb-0000-0000-0000-000000000001")
PUJA = uuid.UUID("11111111-1111-1111-1111-111111111111")
ADDRESS = uuid.UUID("dddddddd-0000-0000-0000-000000000001")


async def _require_migration_026(session) -> None:
    row = (
        await session.execute(
            text(
                """
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'bookings'
                  AND column_name = 'tds_snapshot_entity_type'
                """
            )
        )
    ).scalar_one_or_none()
    if row is None:
        pytest.skip("migration_026 not applied — run: python scripts/apply_migration_026.py")


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


async def _insert_in_progress_booking(session, uniq) -> uuid.UUID:
    pujari_id = await _pujari_id(session)
    bid = uuid.UUID(uniq.id())
    h = int(bid.hex[:12], 16)
    slot = f"{(h % 12) + 8:02d}:{(h // 12) % 60:02d}:00"
    day_off = 200 + (h % 500)
    in_progress = (
        await session.execute(
            text("SELECT id FROM status_types WHERE domain='booking' AND code='in_progress'")
        )
    ).scalar_one()
    await session.execute(
        text(
            """
            INSERT INTO bookings (
                id, user_id, pujari_id, intended_pujari_id, puja_id, address_id, status_id,
                cancellation_policy_id, scheduled_date, scheduled_time, duration_minutes,
                total_amount, amount_due_online, amount_due_offline, booking_fee,
                payment_mode, paid_at, dispatch_mode, created_at, updated_at
            )
            VALUES (
                :bid, :uid, :pid, :pid, :puja, :addr, :sid,
                (SELECT id FROM cancellation_policies WHERE name='standard'),
                current_date + :day_off, CAST(:slot AS time), 90, 2100, 0, 2100, 61,
                'booking_fee', now(), 'broadcast', now(), now()
            )
            """
        ),
        {
            "bid": str(bid),
            "uid": str(CUSTOMER),
            "pid": str(pujari_id),
            "puja": str(PUJA),
            "addr": str(ADDRESS),
            "sid": in_progress,
            "day_off": day_off,
            "slot": slot,
        },
    )
    await session.commit()
    return bid


@pytest.mark.asyncio
async def test_confirm_balance_captures_classification_snapshot(session, seed, uniq, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "TDS_ACCRUAL_ENABLED", False)
    await _require_migration_026(session)
    bid = await _insert_in_progress_booking(session, uniq)
    pujari_id = await _pujari_id(session)
    await session.execute(
        text(
            """
            UPDATE pujaris
            SET entity_type = 'individual', pan_hash = NULL
            WHERE id = :pid
            """
        ),
        {"pid": str(pujari_id)},
    )
    await session.commit()

    resp = await lifecycle_ep.confirm_balance(
        bid,
        BalanceCollected(method="cash"),
        _pujari(),
        session,
    )
    assert resp.status == "collected"
    assert resp.tds.skipped is True

    snap = await tds_accrual_service.lookup_classification_snapshot_for_booking(session, bid)
    assert snap == {"entity_type": "individual", "pan_on_file": False}

    await session.execute(
        text("UPDATE pujaris SET entity_type = 'firm', pan_hash = :ph WHERE id = :pid"),
        {"ph": "c" * 64, "pid": str(pujari_id)},
    )
    await session.commit()

    snap_after_drift = await tds_accrual_service.lookup_classification_snapshot_for_booking(
        session, bid
    )
    assert snap_after_drift == {"entity_type": "individual", "pan_on_file": False}


@pytest.mark.asyncio
async def test_confirm_balance_snapshot_no_pan_no_entity_type(session, seed, uniq, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "TDS_ACCRUAL_ENABLED", False)
    await _require_migration_026(session)
    bid = await _insert_in_progress_booking(session, uniq)
    pujari_id = await _pujari_id(session)
    await session.execute(
        text("UPDATE pujaris SET entity_type = NULL, pan_hash = NULL WHERE id = :pid"),
        {"pid": str(pujari_id)},
    )
    await session.commit()

    resp = await lifecycle_ep.confirm_balance(
        bid,
        BalanceCollected(method="cash", amount=Decimal("2100")),
        _pujari(),
        session,
    )
    assert resp.status == "collected"

    snap = await tds_accrual_service.lookup_classification_snapshot_for_booking(session, bid)
    assert snap == {"entity_type": None, "pan_on_file": False}


@pytest.mark.asyncio
async def test_capture_classification_snapshot_is_idempotent(session, seed, uniq):
    await _require_migration_026(session)
    bid = await _insert_in_progress_booking(session, uniq)
    pujari_id = await _pujari_id(session)
    await session.execute(
        text(
            """
            UPDATE bookings
            SET balance_collected_at = now(),
                balance_collected_by = :uid,
                balance_collection_method = 'cash',
                balance_collected_amount = 2100
            WHERE id = :bid
            """
        ),
        {"uid": str(PUJARI_USER), "bid": str(bid)},
    )
    await session.commit()

    first = await tds_accrual_service.capture_classification_snapshot_at_collection(
        session, booking_id=bid, pujari_id=pujari_id
    )
    second = await tds_accrual_service.capture_classification_snapshot_at_collection(
        session, booking_id=bid, pujari_id=pujari_id
    )
    assert first is True
    assert second is False
