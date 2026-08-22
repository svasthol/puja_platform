"""Auto dispatch readiness when a pujari is verified or a new puja is catalogued."""
from __future__ import annotations

import datetime as dt
import uuid

import pytest
from sqlalchemy import text

from app.services.dispatch_supply import assert_dispatch_supply, count_dispatch_eligible_for_slot
from app.services.kyc_verification import recompute_pujari_verification
from app.services.partner_dispatch_readiness import (
    ensure_partner_dispatch_readiness,
    ensure_puja_pricing_for_verified_pujaris,
)


async def _mk_pending_pujari(session) -> uuid.UUID:
    uid = uuid.uuid4()
    pid = uuid.uuid4()
    await session.execute(
        text("INSERT INTO users (id, full_name, phone) VALUES (:id, 'P', :ph)"),
        {"id": str(uid), "ph": "+91980" + uuid.uuid4().hex[:7]},
    )
    await session.execute(
        text(
            "INSERT INTO pujaris (id, user_id, verification_status, created_at, updated_at) "
            "VALUES (:pid, :uid, 'pending', now(), now())"
        ),
        {"pid": str(pid), "uid": str(uid)},
    )
    return pid


@pytest.mark.asyncio
async def test_ensure_partner_dispatch_readiness_idempotent(session, seed, uniq):
    pid = await _mk_pending_pujari(session)
    await session.execute(
        text("UPDATE pujaris SET verification_status = 'verified' WHERE id = :pid"),
        {"pid": str(pid)},
    )
    await session.commit()

    first = await ensure_partner_dispatch_readiness(session, pujari_id=pid)
    second = await ensure_partner_dispatch_readiness(session, pujari_id=pid)

    assert first.service_areas_linked >= 1
    assert first.availability_inserted == 7
    assert first.pricing_inserted >= 1
    assert second.service_areas_linked == 0
    assert second.availability_inserted == 0
    assert second.pricing_inserted == 0

    area_count = (
        await session.execute(
            text("SELECT count(*) FROM pujari_service_areas WHERE pujari_id = :pid"),
            {"pid": str(pid)},
        )
    ).scalar_one()
    avail_count = (
        await session.execute(
            text("SELECT count(*) FROM pujari_availability WHERE pujari_id = :pid"),
            {"pid": str(pid)},
        )
    ).scalar_one()
    assert area_count >= 1
    assert avail_count == 7


@pytest.mark.asyncio
async def test_readiness_enables_dispatch_supply(session, seed, uniq):
    pid = await _mk_pending_pujari(session)
    puja_id = uuid.UUID("11111111-1111-1111-1111-111111111111")
    await session.execute(
        text("UPDATE pujaris SET verification_status = 'verified' WHERE id = :pid"),
        {"pid": str(pid)},
    )
    await session.commit()

    now = dt.datetime.now(dt.UTC)
    slot_date = (now + dt.timedelta(days=3)).date()
    slot_time = dt.time(10, 0)

    await ensure_partner_dispatch_readiness(session, pujari_id=pid)
    after = await count_dispatch_eligible_for_slot(
        session,
        puja_id=puja_id,
        scheduled_date=slot_date,
        scheduled_time=slot_time,
        duration_minutes=90,
    )

    assert after >= 1
    await assert_dispatch_supply(
        session,
        puja_id=puja_id,
        scheduled_date=slot_date,
        scheduled_time=slot_time,
        duration_minutes=90,
    )


@pytest.mark.asyncio
async def test_recompute_verified_applies_readiness(session, seed):
    pid = await _mk_pending_pujari(session)
    for doc_type in ("identity_proof", "address_proof", "photo"):
        await session.execute(
            text(
                """
                INSERT INTO pujari_documents
                (id, pujari_id, doc_type, file_url, version, is_current, status, uploaded_at)
                VALUES (gen_random_uuid(), :pid, :dtype, :url, 1, true, 'verified', now())
                """
            ),
            {
                "pid": str(pid),
                "dtype": doc_type,
                "url": f"kyc/{pid}/{doc_type}.jpg",
            },
        )
    await session.commit()

    status = await recompute_pujari_verification(session, pid)
    assert status == "verified"

    area_count = (
        await session.execute(
            text("SELECT count(*) FROM pujari_service_areas WHERE pujari_id = :pid"),
            {"pid": str(pid)},
        )
    ).scalar_one()
    avail_count = (
        await session.execute(
            text("SELECT count(*) FROM pujari_availability WHERE pujari_id = :pid"),
            {"pid": str(pid)},
        )
    ).scalar_one()
    assert area_count >= 1
    assert avail_count == 7


@pytest.mark.asyncio
async def test_ensure_puja_pricing_for_verified_pujaris(session, seed, uniq):
    pid = await _mk_pending_pujari(session)
    await session.execute(
        text("UPDATE pujaris SET verification_status = 'verified' WHERE id = :pid"),
        {"pid": str(pid)},
    )
    puja_id = uuid.uuid4()
    await session.execute(
        text(
            """
            INSERT INTO pujas (
                id, category_id, name, slug, duration_minutes, default_price,
                display_order, is_active, created_at, updated_at
            )
            SELECT :id, c.id, :name, :slug, 90, 1500, 9999, true, now(), now()
            FROM puja_categories c
            WHERE c.is_active
            LIMIT 1
            """
        ),
        {
            "id": str(puja_id),
            "name": f"Ready-{uniq.id()[:8]}",
            "slug": f"ready-{uniq.id()[:8]}",
        },
    )
    await session.commit()

    result = await ensure_puja_pricing_for_verified_pujaris(session, puja_id=puja_id)
    assert result.pricing_inserted >= 1

    row = (
        await session.execute(
            text(
                "SELECT 1 FROM pujari_pricing WHERE pujari_id = :pid AND puja_id = :puja"
            ),
            {"pid": str(pid), "puja": str(puja_id)},
        )
    ).scalar_one_or_none()
    assert row is not None
