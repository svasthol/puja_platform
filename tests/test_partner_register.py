"""Partner register endpoint tests."""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from app.core.dependencies import Principal
from app.services import partner_kyc_service as kyc_svc


async def _mk_pujari_user(session) -> tuple[uuid.UUID, uuid.UUID]:
    uid = uuid.uuid4()
    await session.execute(
        text("INSERT INTO users (id, full_name, phone) VALUES (:id, 'Pandit', :ph)"),
        {"id": str(uid), "ph": "+91973" + uuid.uuid4().hex[:7]},
    )
    return uid, uid


@pytest.mark.asyncio
async def test_register_pujari_idempotent(session):
    uid = uuid.uuid4()
    await session.execute(
        text("INSERT INTO users (id, full_name, phone) VALUES (:id, 'Pandit', :ph)"),
        {"id": str(uid), "ph": "+91974" + uuid.uuid4().hex[:7]},
    )
    pujari1, created1 = await kyc_svc.register_pujari(
        session, user_id=uid, bio="bio", years_experience=5
    )
    pujari2, created2 = await kyc_svc.register_pujari(
        session, user_id=uid, bio=None, years_experience=None
    )
    assert created1 is True
    assert created2 is False
    assert pujari1.id == pujari2.id
    assert pujari2.verification_status == "pending"
