"""Pujari verification promotion after document review (A-KYC)."""
from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.kyc_config import REQUIRED_DOC_TYPES
from app.models.catalog import Pujari, PujariDocument


async def required_docs_verified(db: AsyncSession, pujari_id: uuid.UUID) -> bool:
    for doc_type in REQUIRED_DOC_TYPES:
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
        if row is None:
            return False
    return True


async def recompute_pujari_verification(
    db: AsyncSession, pujari_id: uuid.UUID
) -> str:
    """Promote to verified only when every required doc_type is verified; else pending."""
    pujari = (
        await db.execute(select(Pujari).where(Pujari.id == pujari_id))
    ).scalar_one_or_none()
    if pujari is None:
        raise ValueError(f"Pujari not found: {pujari_id}")

    if await required_docs_verified(db, pujari_id):
        new_status = "verified"
    else:
        new_status = "pending"

    if pujari.verification_status != new_status:
        pujari.verification_status = new_status
        pujari.updated_at = dt.datetime.now(dt.UTC)
        await db.flush()

    return new_status
