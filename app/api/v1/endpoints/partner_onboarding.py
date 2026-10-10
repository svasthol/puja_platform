"""Partner onboarding — register, DigiLocker KYC, selfie upload."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints.auth import _rate_limit
from app.core.config import get_settings
from app.core.dependencies import Principal, require_pujari
from app.db.engine import get_db, get_db_txn
from app.schemas.partner_kyc import (
    DigilockerStartResponse,
    KycActiveDigilockerRequest,
    KycDocRequirement,
    KycRequestStatusResponse,
    PartnerKycStatusResponse,
    PartnerRegisterRequest,
    PartnerRegisterResponse,
    SelfieConfirmResponse,
    SelfiePresignRequest,
    SelfiePresignResponse,
)
from app.schemas.tax_profile import PujariPanSubmitRequest, PujariPanSubmitResponse
from app.services import partner_kyc_service as kyc_svc
from app.services.partner_kyc_service import PartnerKycError
from app.services.pujari_compliance import submit_partner_pan

router = APIRouter(prefix="/pujari", tags=["pujari-onboarding"])
callback_router = APIRouter(tags=["pujari-kyc-callback"])
settings = get_settings()


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _user_agent(request: Request) -> str | None:
    return request.headers.get("User-Agent")


async def _pujari_id(db: AsyncSession, user_id: uuid.UUID) -> uuid.UUID:
    pid = (
        await db.execute(
            text("SELECT id FROM pujaris WHERE user_id = :uid"),
            {"uid": str(user_id)},
        )
    ).scalar_one_or_none()
    if pid is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Register as pujari first.")
    return pid


def _map_kyc_error(exc: PartnerKycError) -> HTTPException:
    return HTTPException(exc.status_code, str(exc))


@router.post("/register", response_model=PartnerRegisterResponse)
async def register_pujari(
    payload: PartnerRegisterRequest,
    p: Principal = Depends(require_pujari),
    db: AsyncSession = Depends(get_db_txn),
):
    try:
        pujari, created = await kyc_svc.register_pujari(
            db,
            user_id=p.user_id,
            bio=payload.bio,
            years_experience=payload.years_experience,
        )
    except PartnerKycError as exc:
        raise _map_kyc_error(exc) from exc
    return PartnerRegisterResponse(
        pujari_id=pujari.id,
        verification_status=pujari.verification_status,
        created=created,
    )


@router.post("/kyc/digilocker", response_model=DigilockerStartResponse)
async def start_digilocker(
    request: Request,
    p: Principal = Depends(require_pujari),
    db: AsyncSession = Depends(get_db_txn),
):
    pid = await _pujari_id(db, p.user_id)
    await _rate_limit(
        f"kyc_start:{pid}",
        settings.KYC_START_RATE_LIMIT_PER_HOUR,
        3600,
    )
    try:
        row, url = await kyc_svc.start_digilocker(
            db,
            pujari_id=pid,
            ip=_client_ip(request),
            user_agent=_user_agent(request),
        )
    except PartnerKycError as exc:
        raise _map_kyc_error(exc) from exc
    return DigilockerStartResponse(
        request_id=row.id,
        url=url or None,
        expires_at=row.expires_at,
        status=row.status,
    )


@callback_router.get("/pujari/kyc/callback")
async def kyc_callback(
    request: Request,
    id: str = Query(..., description="Setu DigiLocker request id"),
    success: bool = Query(...),
    kyc_nonce: str | None = Query(default=None),
    scope: str | None = Query(default=None),
    errCode: str | None = Query(default=None),
    errMessage: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db_txn),
):
    """PUBLIC — nonce-bound DigiLocker redirect landing (no bearer token)."""
    await _rate_limit(
        f"kyc_callback:{id}",
        settings.KYC_CALLBACK_RATE_LIMIT_PER_HOUR,
        3600,
    )
    try:
        await kyc_svc.handle_callback(
            db,
            vendor_request_id=id,
            success=success,
            nonce=kyc_nonce,
            scope=scope,
            error_code=errCode,
            error_message=errMessage,
        )
    except PartnerKycError as exc:
        raise _map_kyc_error(exc) from exc
    return RedirectResponse(url=settings.KYC_APP_RETURN_URL, status_code=status.HTTP_302_FOUND)


@router.get("/kyc/requests/{request_id}", response_model=KycRequestStatusResponse)
async def get_kyc_request(
    request_id: uuid.UUID,
    p: Principal = Depends(require_pujari),
    db: AsyncSession = Depends(get_db_txn),
):
    pid = await _pujari_id(db, p.user_id)
    try:
        row, created_types = await kyc_svc.poll_and_finalize(
            db, request_id=request_id, pujari_id=pid
        )
    except PartnerKycError as exc:
        raise _map_kyc_error(exc) from exc
    flags = row.review_flags if isinstance(row.review_flags, list) else []
    return KycRequestStatusResponse(
        request_id=row.id,
        status=row.status,
        scope=row.scope,
        doc_types_created=created_types,
        error_code=row.error_code,
        error_message=row.error_message,
        review_flags=flags,
    )


@router.post("/documents", response_model=SelfiePresignResponse)
async def presign_selfie_document(
    payload: SelfiePresignRequest,
    p: Principal = Depends(require_pujari),
    db: AsyncSession = Depends(get_db_txn),
):
    """Camera-captured selfie only — gating `photo` doc (UX control, not liveness)."""
    pid = await _pujari_id(db, p.user_id)
    try:
        doc_id, url, expires, file_url = await kyc_svc.presign_selfie(
            db,
            pujari_id=pid,
            content_type=payload.content_type,
            content_length=payload.content_length,
        )
    except PartnerKycError as exc:
        raise _map_kyc_error(exc) from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    return SelfiePresignResponse(
        document_id=doc_id,
        upload_url=url,
        upload_url_expires_in=expires,
        file_url=file_url,
    )


@router.post("/documents/{document_id}/confirm", response_model=SelfieConfirmResponse)
async def confirm_selfie_document(
    document_id: uuid.UUID,
    p: Principal = Depends(require_pujari),
    db: AsyncSession = Depends(get_db_txn),
):
    """After presigned PUT — verify S3 object and strip JPEG EXIF before admin review."""
    pid = await _pujari_id(db, p.user_id)
    try:
        doc = await kyc_svc.confirm_selfie(
            db,
            pujari_id=pid,
            document_id=document_id,
        )
    except PartnerKycError as exc:
        raise _map_kyc_error(exc) from exc
    return SelfieConfirmResponse(
        document_id=doc.id,
        status=doc.status,
        file_url=doc.file_url,
    )


@router.post("/kyc/pan", response_model=PujariPanSubmitResponse)
async def submit_pan(
    payload: PujariPanSubmitRequest,
    p: Principal = Depends(require_pujari),
    db: AsyncSession = Depends(get_db_txn),
):
    """Partner PAN + entity type for TDS (Setu verify when KYC_SETU_PAN_PRODUCT_ID set)."""
    pid = await _pujari_id(db, p.user_id)
    result = await submit_partner_pan(
        db,
        pujari_id=pid,
        entity_type=payload.entity_type,
        pan=payload.pan,
        consent=payload.consent,
        reason=payload.reason,
    )
    return PujariPanSubmitResponse(
        entity_type=result["entity_type"],
        pan_on_file=result["pan_on_file"],
        pan_status=result["pan_status"],
        message=result["message"],
        verified_name=result.get("verified_name"),
    )


@router.get("/kyc/status", response_model=PartnerKycStatusResponse)
async def partner_kyc_status(
    p: Principal = Depends(require_pujari),
    db: AsyncSession = Depends(get_db),
):
    pid = await _pujari_id(db, p.user_id)
    try:
        verification_status, required, live = await kyc_svc.get_partner_kyc_status(
            db, pid
        )
    except PartnerKycError as exc:
        raise _map_kyc_error(exc) from exc

    active: KycActiveDigilockerRequest | None = None
    if live is not None:
        flags = live.review_flags if isinstance(live.review_flags, list) else []
        resume_url = await kyc_svc.digilocker_resume_url(live)
        active = KycActiveDigilockerRequest(
            request_id=live.id,
            status=live.status,
            expires_at=live.expires_at,
            url=resume_url,
            review_flags=flags,
        )

    return PartnerKycStatusResponse(
        verification_status=verification_status,
        required=[
            KycDocRequirement(doc_type=t, status=st, document_id=doc_id)
            for t, st, doc_id in required
        ],
        active_digilocker_request=active,
    )
