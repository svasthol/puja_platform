"""Customer-visible profile photo pointer (Slice B) — admin-gated from verified `photo` doc."""
from __future__ import annotations

import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def sync_pujari_customer_profile_photo_pointer(
    db: AsyncSession,
    *,
    pujari_id: uuid.UUID,
    document_id: uuid.UUID,
    doc_type: str,
    new_status: str,
) -> None:
    """Keep `pujaris.customer_profile_photo_doc_id` aligned with KYC admin review.

    - Approve (`verified`) a current `photo` doc → point customers at that document.
    - Reject (`rejected`) or any path where that doc was the published one → clear pointer.
    """
    if doc_type != "photo":
        return

    if new_status == "verified":
        await db.execute(
            text(
                """
                UPDATE pujaris p
                SET customer_profile_photo_doc_id = :doc_id, updated_at = now()
                FROM pujari_documents pd
                WHERE p.id = :pid
                  AND pd.id = :doc_id
                  AND pd.pujari_id = p.id
                  AND pd.doc_type = 'photo'
                  AND pd.is_current = true
                  AND pd.status = 'verified'
                """
            ),
            {"pid": str(pujari_id), "doc_id": str(document_id)},
        )
        return

    if new_status == "rejected":
        await db.execute(
            text(
                """
                UPDATE pujaris
                SET customer_profile_photo_doc_id = NULL, updated_at = now()
                WHERE id = :pid AND customer_profile_photo_doc_id = :doc_id
                """
            ),
            {"pid": str(pujari_id), "doc_id": str(document_id)},
        )


async def clear_customer_profile_photo_if_reference_stale(
    db: AsyncSession, *, pujari_id: uuid.UUID
) -> None:
    """After a new `photo` upload supersedes old rows, drop pointer if it referenced an old version."""
    await db.execute(
        text(
            """
            UPDATE pujaris
            SET customer_profile_photo_doc_id = NULL, updated_at = now()
            WHERE id = :pid
              AND customer_profile_photo_doc_id IS NOT NULL
              AND customer_profile_photo_doc_id IN (
                SELECT id FROM pujari_documents
                WHERE pujari_id = :pid AND doc_type = 'photo' AND is_current = false
              )
            """
        ),
        {"pid": str(pujari_id)},
    )
