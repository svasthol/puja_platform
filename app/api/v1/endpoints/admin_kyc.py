"""Admin KYC review queue (Sprint 4B — A-KYC).

RBAC: read → require_admin; approve/reject → require_admin_role (admin only).
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import Principal, require_admin, require_admin_role
from app.core.kyc_config import DOC_TYPE_LABELS, REQUIRED_DOC_TYPES
from app.db.engine import get_db, get_db_txn
from app.models.catalog import PujariDocument
from app.schemas.admin_kyc import (
    KycPendingItem,
    KycPendingListResponse,
    KycPujariDocSummary,
    KycPujariStatusResponse,
    KycReviewRequest,
    KycReviewResponse,
)
from app.schemas.common import decode_cursor, encode_cursor
from app.services.audit import record_admin_action
from app.services.kyc_storage import presign_kyc_get
from app.services.kyc_verification import recompute_pujari_verification, required_docs_verified

router = APIRouter(prefix="/admin/kyc", tags=["admin-kyc"])


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _doc_type_label(doc_type: str) -> str:
    return DOC_TYPE_LABELS.get(doc_type, doc_type.replace("_", " ").title())


async def _require_document(db: AsyncSession, doc_id: uuid.UUID) -> PujariDocument:
    doc = (
        await db.execute(select(PujariDocument).where(PujariDocument.id == doc_id))
    ).scalar_one_or_none()
    if doc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found.")
    return doc


def _attach_view_url(file_url: str) -> tuple[str | None, int | None]:
    url, expires = presign_kyc_get(file_url)
    if url is None:
        return None, None
    return url, expires


@router.get("/pending", response_model=KycPendingListResponse)
async def list_pending_kyc(
    cursor: str | None = None,
    limit: int = Query(20, ge=1, le=50),
    pujari_id: uuid.UUID | None = None,
    _p: Principal = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Pending current documents awaiting admin review."""
    page_limit = limit if isinstance(limit, int) else 20
    params: dict = {"lim": page_limit + 1}
    filters = (
        "WHERE pd.is_current = true AND pd.status = 'pending' "
    )
    if pujari_id is not None:
        params["pid"] = str(pujari_id)
        filters += "AND pd.pujari_id = :pid "

    cursor_pred = ""
    if cursor:
        uploaded_str, id_str = decode_cursor(cursor, 2)
        try:
            params["c_uploaded"] = uploaded_str
            params["c_id"] = uuid.UUID(id_str)
        except ValueError:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Invalid cursor.")
        cursor_pred = "AND (pd.uploaded_at, pd.id) < (:c_uploaded::timestamptz, :c_id) "

    rows = (
        await db.execute(
            text(
                """
                SELECT pd.id, pd.pujari_id, pd.doc_type, pd.version, pd.uploaded_at,
                       pd.file_url, u.full_name AS pujari_name, u.phone AS pujari_phone,
                       pj.verification_status AS pujari_verification_status
                FROM pujari_documents pd
                JOIN pujaris pj ON pj.id = pd.pujari_id
                JOIN users u ON u.id = pj.user_id
                """
                + filters
                + cursor_pred
                + "ORDER BY pd.uploaded_at DESC, pd.id DESC LIMIT :lim"
            ),
            params,
        )
    ).mappings().all()

    next_cursor = None
    page = list(rows)
    if len(page) > page_limit:
        page = page[:page_limit]
        last = page[-1]
        next_cursor = encode_cursor(last["uploaded_at"], last["id"])

    items: list[KycPendingItem] = []
    for r in page:
        view_url, expires = _attach_view_url(r["file_url"])
        items.append(
            KycPendingItem(
                id=r["id"],
                pujari_id=r["pujari_id"],
                pujari_name=r["pujari_name"],
                pujari_phone=r["pujari_phone"],
                pujari_verification_status=r["pujari_verification_status"],
                doc_type=r["doc_type"],
                doc_type_label=_doc_type_label(r["doc_type"]),
                version=r["version"],
                uploaded_at=r["uploaded_at"],
                view_url=view_url,
                view_url_expires_in=expires,
            )
        )

    return KycPendingListResponse(
        items=items,
        next_cursor=next_cursor,
        required_doc_types=list(REQUIRED_DOC_TYPES),
    )


@router.get("/pujaris/{pujari_id}", response_model=KycPujariStatusResponse)
async def pujari_kyc_status(
    pujari_id: uuid.UUID,
    _p: Principal = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Current document status per required type for one pujari."""
    pujari = (
        await db.execute(
            text(
                """
                SELECT pj.id, u.full_name, u.phone, pj.verification_status
                FROM pujaris pj
                JOIN users u ON u.id = pj.user_id
                WHERE pj.id = :id
                """
            ),
            {"id": str(pujari_id)},
        )
    ).mappings().first()
    if pujari is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Pujari not found.")

    current_docs = (
        await db.execute(
            select(PujariDocument).where(
                PujariDocument.pujari_id == pujari_id,
                PujariDocument.is_current.is_(True),
            )
        )
    ).scalars().all()
    by_type = {d.doc_type: d for d in current_docs}

    summaries: list[KycPujariDocSummary] = []
    for doc_type in REQUIRED_DOC_TYPES:
        doc = by_type.get(doc_type)
        if doc is None:
            summaries.append(
                KycPujariDocSummary(
                    doc_type=doc_type,
                    doc_type_label=_doc_type_label(doc_type),
                )
            )
        else:
            view_url, _ = _attach_view_url(doc.file_url)
            summaries.append(
                KycPujariDocSummary(
                    doc_type=doc_type,
                    doc_type_label=_doc_type_label(doc_type),
                    status=doc.status,  # type: ignore[arg-type]
                    document_id=doc.id,
                    version=doc.version,
                    uploaded_at=doc.uploaded_at,
                    view_url=view_url,
                )
            )

    all_ok = await required_docs_verified(db, pujari_id)
    return KycPujariStatusResponse(
        pujari_id=pujari_id,
        full_name=pujari["full_name"],
        phone=pujari["phone"],
        verification_status=pujari["verification_status"],
        required_doc_types=list(REQUIRED_DOC_TYPES),
        documents=summaries,
        all_required_verified=all_ok,
    )


async def _review_document(
    db: AsyncSession,
    *,
    doc_id: uuid.UUID,
    new_status: str,
    actor: Principal,
    request: Request,
    payload: KycReviewRequest,
) -> KycReviewResponse:
    doc = await _require_document(db, doc_id)
    if not doc.is_current:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Document is superseded — review the current version only.",
        )
    if doc.status != "pending":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Document is already {doc.status}.",
        )

    before = {"status": doc.status, "doc_type": doc.doc_type}
    doc.status = new_status
    await db.flush()

    pujari_status = await recompute_pujari_verification(db, doc.pujari_id)
    all_ok = pujari_status == "verified"

    await record_admin_action(
        db,
        actor_user_id=actor.user_id,
        action=new_status,
        entity_type="pujari_documents",
        entity_id=str(doc.id),
        before=before,
        after={
            "status": new_status,
            "pujari_id": str(doc.pujari_id),
            "pujari_verification_status": pujari_status,
        },
        change_reason=payload.change_reason or payload.note,
        ip=_client_ip(request),
    )

    return KycReviewResponse(
        document_id=doc.id,
        document_status=new_status,  # type: ignore[arg-type]
        pujari_id=doc.pujari_id,
        pujari_verification_status=pujari_status,  # type: ignore[arg-type]
        all_required_verified=all_ok,
    )


@router.post("/{doc_id}/approve", response_model=KycReviewResponse)
async def approve_document(
    doc_id: uuid.UUID,
    payload: KycReviewRequest,
    request: Request,
    p: Principal = Depends(require_admin_role),
    db: AsyncSession = Depends(get_db_txn),
):
    """Approve one document; promote pujari when all required docs are verified."""
    return await _review_document(
        db,
        doc_id=doc_id,
        new_status="verified",
        actor=p,
        request=request,
        payload=payload,
    )


@router.post("/{doc_id}/reject", response_model=KycReviewResponse)
async def reject_document(
    doc_id: uuid.UUID,
    payload: KycReviewRequest,
    request: Request,
    p: Principal = Depends(require_admin_role),
    db: AsyncSession = Depends(get_db_txn),
):
    """Reject one document; blocks pujari verification until re-upload."""
    if not (payload.change_reason or payload.note):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Provide change_reason or note when rejecting.",
        )
    return await _review_document(
        db,
        doc_id=doc_id,
        new_status="rejected",
        actor=p,
        request=request,
        payload=payload,
    )
