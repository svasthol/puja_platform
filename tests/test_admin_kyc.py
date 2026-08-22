"""Sprint 4B — admin KYC review tests (A-KYC)."""
from __future__ import annotations

import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import text

from app.api.v1.endpoints import admin_kyc as kyc_ep
from app.core.dependencies import Principal
from app.schemas.admin_kyc import KycReviewRequest


class _FakeRequest:
    client = None


def _admin(uid: uuid.UUID) -> Principal:
    return Principal(user_id=uid, app_context="admin", roles=("admin",))


async def _mk_admin(session) -> uuid.UUID:
    uid = uuid.uuid4()
    await session.execute(
        text("INSERT INTO users (id, full_name, phone) VALUES (:id, 'Admin', :ph)"),
        {"id": str(uid), "ph": "+91971" + uuid.uuid4().hex[:7]},
    )
    return uid


async def _mk_pujari(session) -> uuid.UUID:
    uid = uuid.uuid4()
    pid = uuid.uuid4()
    await session.execute(
        text("INSERT INTO users (id, full_name, phone) VALUES (:id, 'Pandit', :ph)"),
        {"id": str(uid), "ph": "+91972" + uuid.uuid4().hex[:7]},
    )
    await session.execute(
        text(
            "INSERT INTO pujaris (id, user_id, verification_status, created_at, updated_at) "
            "VALUES (:pid, :uid, 'pending', now(), now())"
        ),
        {"pid": str(pid), "uid": str(uid)},
    )
    return pid


async def _insert_doc(
    session,
    *,
    pujari_id: uuid.UUID,
    doc_type: str,
    status: str = "pending",
) -> uuid.UUID:
    doc_id = uuid.uuid4()
    await session.execute(
        text(
            "INSERT INTO pujari_documents "
            "(id, pujari_id, doc_type, file_url, version, is_current, status, uploaded_at) "
            "VALUES (:id, :pid, :dtype, :url, 1, true, :st, now())"
        ),
        {
            "id": str(doc_id),
            "pid": str(pujari_id),
            "dtype": doc_type,
            "url": f"kyc/{pujari_id}/{doc_type}.jpg",
            "st": status,
        },
    )
    return doc_id


@pytest.mark.asyncio
async def test_list_pending_kyc(session):
    actor = await _mk_admin(session)
    pid = await _mk_pujari(session)
    await _insert_doc(session, pujari_id=pid, doc_type="identity_proof")
    await session.commit()

    resp = await kyc_ep.list_pending_kyc(limit=20, _p=_admin(actor), db=session)
    assert len(resp.items) >= 1
    assert resp.items[0].doc_type == "identity_proof"
    assert "identity_proof" in resp.required_doc_types


@pytest.mark.asyncio
async def test_approve_promotes_when_all_required_verified(session):
    actor = await _mk_admin(session)
    pid = await _mk_pujari(session)
    doc_ids = {
        t: await _insert_doc(session, pujari_id=pid, doc_type=t)
        for t in ("identity_proof", "address_proof", "photo")
    }
    await session.commit()

    for doc_type in ("identity_proof", "address_proof"):
        await kyc_ep.approve_document(
            doc_ids[doc_type],
            KycReviewRequest(change_reason="ok"),
            _FakeRequest(),
            p=_admin(actor),
            db=session,
        )
        await session.commit()

    status_row = (
        await session.execute(
            text("SELECT verification_status FROM pujaris WHERE id = :id"),
            {"id": str(pid)},
        )
    ).scalar_one()
    assert status_row == "pending"

    result = await kyc_ep.approve_document(
        doc_ids["photo"],
        KycReviewRequest(change_reason="ok"),
        _FakeRequest(),
        p=_admin(actor),
        db=session,
    )
    await session.commit()

    assert result.all_required_verified is True
    assert result.pujari_verification_status == "verified"

    area_count = (
        await session.execute(
            text("SELECT count(*) FROM pujari_service_areas WHERE pujari_id = :id"),
            {"id": str(pid)},
        )
    ).scalar_one()
    avail_count = (
        await session.execute(
            text("SELECT count(*) FROM pujari_availability WHERE pujari_id = :id"),
            {"id": str(pid)},
        )
    ).scalar_one()
    assert area_count >= 1
    assert avail_count == 7


@pytest.mark.asyncio
async def test_reject_requires_reason(session):
    actor = await _mk_admin(session)
    pid = await _mk_pujari(session)
    doc_id = await _insert_doc(session, pujari_id=pid, doc_type="photo")
    await session.commit()

    with pytest.raises(HTTPException) as exc:
        await kyc_ep.reject_document(
            doc_id,
            KycReviewRequest(),
            _FakeRequest(),
            p=_admin(actor),
            db=session,
        )
    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_pujari_kyc_status_summary(session):
    actor = await _mk_admin(session)
    pid = await _mk_pujari(session)
    await _insert_doc(session, pujari_id=pid, doc_type="identity_proof")
    await session.commit()

    summary = await kyc_ep.pujari_kyc_status(pid, _p=_admin(actor), db=session)
    assert summary.pujari_id == pid
    assert len(summary.documents) == 3
    assert summary.documents[0].doc_type == "identity_proof"
    assert summary.documents[0].status == "pending"
    assert summary.documents[1].status is None  # missing address_proof
