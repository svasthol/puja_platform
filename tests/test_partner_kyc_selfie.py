"""Partner selfie presign + confirm (mocked S3)."""
from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from sqlalchemy import text

from app.services import partner_kyc_service as kyc_svc


async def _seed_pujari(session) -> uuid.UUID:
    uid = uuid.uuid4()
    pid = uuid.uuid4()
    phone = "+91973" + uuid.uuid4().hex[:7]
    await session.execute(
        text("INSERT INTO users (id, full_name, phone) VALUES (:id, 'Pandit', :ph)"),
        {"id": str(uid), "ph": phone},
    )
    await session.execute(
        text(
            "INSERT INTO pujaris (id, user_id, verification_status, created_at, updated_at) "
            "VALUES (:pid, :uid, 'pending', now(), now())"
        ),
        {"pid": str(pid), "uid": str(uid)},
    )
    return pid


async def _insert_photo_doc(session, pujari_id: uuid.UUID) -> uuid.UUID:
    doc_id = uuid.uuid4()
    await session.execute(
        text(
            "INSERT INTO pujari_documents "
            "(id, pujari_id, doc_type, file_url, version, is_current, status) "
            "VALUES (:id, :pid, 'photo', :url, 1, true, 'pending')"
        ),
        {
            "id": str(doc_id),
            "pid": str(pujari_id),
            "url": f"kyc/917675834207/photo/{doc_id}.jpg",
        },
    )
    return doc_id


# Minimal JPEG (no EXIF) + fake EXIF segment for strip test
_MIN_JPEG = (
    b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    b"\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08"
    b"\x0a\x0c\x14\x0d\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a\x1f\x1e"
    b"\x1d\x1a\x1c\x1c\x20\x24\x2e\x27\x20\x22\x2c\x23\x1c\x1c\x28\x37\x29"
    b"\x2c\x30\x31\x34\x34\x34\x1f\x27\x39\x3d\x38\x32\x3c\x2e\x33\x34\x32"
    b"\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00\xff\xc4\x00\x14"
    b"\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
    b"\x08\xff\xc4\x00\x14\x10\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
    b"\x00\x00\x00\x00\xff\xda\x00\x08\x01\x01\x00\x00\x3f\x00\x37\xff\xd9"
)
_EXIF_JPEG = (
    b"\xff\xd8\xff\xe1\x00\x10Exif\x00\x00MM\x00\x00\x00\x00\x00\x00"
    + _MIN_JPEG[2:]
)


@pytest.mark.asyncio
async def test_presign_selfie_creates_document_row(session):
    pid = await _seed_pujari(session)
    await session.commit()

    with patch(
        "app.services.partner_kyc_service.presign_kyc_put",
        return_value=("https://s3.example/upload", 900),
    ):
        doc_id, url, expires, key = await kyc_svc.presign_selfie(
            session,
            pujari_id=pid,
            content_type="image/jpeg",
            content_length=1024,
        )
    await session.commit()

    assert url == "https://s3.example/upload"
    assert expires == 900
    assert key.startswith("kyc/")
    assert "/photo/" in key

    row = (
        await session.execute(
            text(
                "SELECT doc_type, file_url, is_current, status FROM pujari_documents WHERE id = :id"
            ),
            {"id": str(doc_id)},
        )
    ).mappings().one()
    assert row["doc_type"] == "photo"
    assert row["file_url"] == key
    assert row["is_current"] is True
    assert row["status"] == "uploading"


@pytest.mark.asyncio
async def test_confirm_selfie_strips_exif_and_sets_uploaded_at(session):
    pid = await _seed_pujari(session)
    doc_id = await _insert_photo_doc(session, pid)
    await session.commit()

    stored: dict[str, bytes] = {}

    def _fake_fetch(_url: str):
        return _EXIF_JPEG, "image/jpeg"

    def _fake_store(**kwargs):
        stored["body"] = kwargs["body"]
        return kwargs["s3_key"]

    with (
        patch("app.services.partner_kyc_service.fetch_kyc_bytes", _fake_fetch),
        patch("app.services.partner_kyc_service.store_kyc_bytes", _fake_store),
    ):
        doc = await kyc_svc.confirm_selfie(
            session,
            pujari_id=pid,
            document_id=doc_id,
        )
    await session.commit()

    assert doc.status == "pending"
    assert doc.uploaded_at is not None
    assert b"\xff\xe1" not in stored["body"]


@pytest.mark.asyncio
async def test_confirm_selfie_missing_s3_object(session):
    pid = await _seed_pujari(session)
    doc_id = await _insert_photo_doc(session, pid)
    await session.commit()

    from app.services.kyc_storage import KycStorageError

    with patch(
        "app.services.partner_kyc_service.fetch_kyc_bytes",
        side_effect=KycStorageError("not found"),
    ):
        with pytest.raises(kyc_svc.PartnerKycError) as exc:
            await kyc_svc.confirm_selfie(
                session,
                pujari_id=pid,
                document_id=doc_id,
            )
    assert exc.value.status_code == 422
