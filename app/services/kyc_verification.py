"""Pujari verification promotion after document review (A-KYC)."""
from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.kyc_config import REQUIRED_DOC_TYPES
from app.models.catalog import Pujari, PujariDocument
from app.services.partner_dispatch_readiness import ensure_partner_dispatch_readiness


async def _current_doc_verified(
    db: AsyncSession, pujari_id: uuid.UUID, doc_type: str
) -> bool:
    row = (
        await db.execute(
            select(PujariDocument.id).where(
                PujariDocument.pujari_id == pujari_id,
                PujariDocument.doc_type == doc_type,
                PujariDocument.is_current.is_(True),
                PujariDocument.status == "verified",
            )
        )
    ).scalar_one_or_none()
    return row is not None


async def required_docs_verified(db: AsyncSession, pujari_id: uuid.UUID) -> bool:
    for doc_type in REQUIRED_DOC_TYPES:
        if not await _current_doc_verified(db, pujari_id, doc_type):
            return False
    return True


async def required_non_photo_docs_verified(
    db: AsyncSession, pujari_id: uuid.UUID
) -> bool:
    """DigiLocker docs on current row — used for Slice C photo-only changes."""
    for doc_type in REQUIRED_DOC_TYPES:
        if doc_type == "photo":
            continue
        if not await _current_doc_verified(db, pujari_id, doc_type):
            return False
    return True


async def recompute_pujari_verification(
    db: AsyncSession, pujari_id: uuid.UUID
) -> str:
    """Promote to verified when every required doc is verified; else pending.

    Slice C: a verified partner re-uploading a selfie must stay **verified** while
    only the photo is pending/rejected (customers keep the last published photo).
    """
    pujari = (
        await db.execute(select(Pujari).where(Pujari.id == pujari_id))
    ).scalar_one_or_none()
    if pujari is None:
        raise ValueError(f"Pujari not found: {pujari_id}")

    previous_status = pujari.verification_status
    if await required_docs_verified(db, pujari_id):
        new_status = "verified"
    elif previous_status == "verified" and await required_non_photo_docs_verified(
        db, pujari_id
    ):
        new_status = "verified"
    else:
        new_status = "pending"

    if previous_status != new_status:
        pujari.verification_status = new_status
        pujari.updated_at = dt.datetime.now(dt.UTC)
        await db.flush()

    if new_status == "verified":
        await ensure_partner_dispatch_readiness(db, pujari_id=pujari_id)
        from app.services.trust_card import seed_public_name_pending

        await seed_public_name_pending(db, pujari_id)

    return new_status
