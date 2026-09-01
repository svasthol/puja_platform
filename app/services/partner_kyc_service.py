"""Partner KYC onboarding orchestration (Setu DigiLocker v1, vendor-agnostic)."""
from __future__ import annotations

import base64
import datetime as dt
import hashlib
import hmac
import json
import re
import secrets
import uuid
from urllib.parse import urlencode, urlparse, urlunparse

import httpx
import structlog
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.kyc_config import (
    KYC_CONSENT_PURPOSE_DIGILOCKER_AADHAAR,
    KYC_CONSENT_TEXT,
    KYC_CONSENT_TEXT_VERSION,
    REQUIRED_DOC_TYPES,
    SCOPE_TO_DOC_TYPES,
)
from app.core.redis_client import redis_delete, redis_set_nx
from app.models.catalog import Pujari, PujariDocument
from app.models.identity import User
from app.models.kyc import KycConsent, KycIdentityRegistry, KycVerificationRequest
from app.services.kyc_storage import (
    KycStorageError,
    KycStorageNotConfigured,
    fetch_kyc_bytes,
    kyc_partner_folder,
    presign_kyc_put,
    store_kyc_bytes,
)
from app.services.kyc_types import KycVendorError
from app.services.kyc_vendor import get_kyc_vendor

log = structlog.get_logger()
settings = get_settings()

_TERMINAL_STATUSES = frozenset({"success", "failed", "expired"})
_NON_TERMINAL_STATUSES = frozenset({"created", "authenticated"})
_FINALIZE_LOCK_SECONDS = 180


class PartnerKycError(Exception):
    def __init__(self, message: str, *, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def _hash_nonce(nonce: str) -> str:
    pepper = settings.KYC_IDENTITY_PEPPER or settings.SECRET_KEY
    return hmac.new(pepper.encode(), nonce.encode(), hashlib.sha256).hexdigest()


def _hash_digilocker_id(digilocker_id: str) -> str:
    pepper = settings.KYC_IDENTITY_PEPPER or settings.SECRET_KEY
    return hmac.new(
        pepper.encode(), digilocker_id.encode(), hashlib.sha256
    ).hexdigest()


def _consent_text_hash() -> str:
    return hashlib.sha256(KYC_CONSENT_TEXT.encode()).hexdigest()


def _append_query(url: str, params: dict[str, str]) -> str:
    parsed = urlparse(url)
    existing = dict(
        p.split("=", 1) if "=" in p else (p, "")
        for p in (parsed.query.split("&") if parsed.query else [])
        if p
    )
    existing.update(params)
    new_query = urlencode(existing)
    return urlunparse(parsed._replace(query=new_query))


def _normalize_name(value: str | None) -> str:
    if not value:
        return ""
    cleaned = re.sub(r"[^a-zA-Z0-9 ]", " ", value.lower())
    return " ".join(cleaned.split())


def _names_mismatch(registered: str | None, digilocker: str | None) -> bool:
    a = _normalize_name(registered)
    b = _normalize_name(digilocker)
    if not a or not b:
        return False
    if a == b:
        return False
    if a in b or b in a:
        return False
    return True


def _age_from_dob(dob: str | None) -> int | None:
    if not dob:
        return None
    for fmt in ("%d-%m-%Y", "%Y-%m-%d"):
        try:
            born = dt.datetime.strptime(dob, fmt).date()
            today = _now().date()
            return today.year - born.year - (
                (today.month, today.day) < (born.month, born.day)
            )
        except ValueError:
            continue
    return None


def _strip_jpeg_exif(data: bytes) -> bytes:
    if not data.startswith(b"\xff\xd8"):
        return data
    out = bytearray()
    i = 2
    out.extend(data[0:2])
    while i < len(data):
        if data[i] != 0xff:
            break
        marker = data[i + 1]
        i += 2
        if marker in (0xd8, 0xd9):
            out.extend(bytes([0xff, marker]))
            continue
        if i + 1 >= len(data):
            break
        seg_len = int.from_bytes(data[i:i + 2], "big")
        segment = data[i - 2:i + seg_len]
        if marker == 0xe1:
            i += seg_len
            continue
        out.extend(segment)
        i += seg_len
    if i < len(data):
        out.extend(data[i:])
    return bytes(out)


async def _pujari_for_user(db: AsyncSession, user_id: uuid.UUID) -> Pujari | None:
    return (
        await db.execute(select(Pujari).where(Pujari.user_id == user_id))
    ).scalar_one_or_none()


async def register_pujari(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    bio: str | None,
    years_experience: int | None,
) -> tuple[Pujari, bool]:
    existing = await _pujari_for_user(db, user_id)
    if existing is not None:
        return existing, False
    now = _now()
    pujari = Pujari(
        id=uuid.uuid4(),
        user_id=user_id,
        bio=bio,
        years_experience=years_experience,
        verification_status="pending",
        created_at=now,
        updated_at=now,
    )
    db.add(pujari)
    await db.flush()
    return pujari, True


async def _lazy_expire_stale(db: AsyncSession, pujari_id: uuid.UUID) -> None:
    await db.execute(
        text(
            """
            UPDATE kyc_verification_requests
            SET status = 'expired', updated_at = now()
            WHERE pujari_id = :pid
              AND kind = 'digilocker'
              AND status IN ('created', 'authenticated')
              AND expires_at < now()
            """
        ),
        {"pid": str(pujari_id)},
    )


def _partner_visible_doc_status(status: str | None) -> str | None:
    """Hide in-flight selfie uploads from partner status (admin queue uses DB status)."""
    if status == "uploading":
        return None
    return status


async def _get_live_request(
    db: AsyncSession, pujari_id: uuid.UUID
) -> KycVerificationRequest | None:
    return (
        await db.execute(
            select(KycVerificationRequest).where(
                KycVerificationRequest.pujari_id == pujari_id,
                KycVerificationRequest.kind == "digilocker",
                KycVerificationRequest.status.in_(("created", "authenticated")),
            )
        )
    ).scalar_one_or_none()


async def _expire_request(db: AsyncSession, request_id: uuid.UUID) -> None:
    await db.execute(
        text(
            """
            UPDATE kyc_verification_requests
            SET status = 'expired', updated_at = now()
            WHERE id = :id AND status IN ('created', 'authenticated')
            """
        ),
        {"id": str(request_id)},
    )


async def _resume_or_clear_live(
    db: AsyncSession, live: KycVerificationRequest
) -> tuple[KycVerificationRequest, str] | None:
    """Return (row, vendor_url) to resume, or None to start a fresh request."""
    if live.vendor_request_id.startswith("local:"):
        await _expire_request(db, live.id)
        return None
    vendor = get_kyc_vendor()
    try:
        vendor_status = await vendor.get_request_status(live.vendor_request_id)
    except KycVendorError as exc:
        if exc.code == "request_not_found":
            await _expire_request(db, live.id)
            return None
        raise PartnerKycError("KYC vendor unavailable.", status_code=502) from exc
    if vendor_status.url:
        return live, vendor_status.url
    if vendor_status.status == "authenticated":
        return live, ""
    if live.expires_at < _now():
        await _expire_request(db, live.id)
        return None
    return live, ""


async def start_digilocker(
    db: AsyncSession,
    *,
    pujari_id: uuid.UUID,
    ip: str | None,
    user_agent: str | None,
) -> tuple[KycVerificationRequest, str]:
    if not settings.KYC_REDIRECT_URL:
        raise PartnerKycError("KYC redirect URL is not configured.", status_code=500)

    await _lazy_expire_stale(db, pujari_id)
    live = await _get_live_request(db, pujari_id)
    if live is not None:
        resumed = await _resume_or_clear_live(db, live)
        if resumed is not None:
            log.info(
                "kyc_request_resumed",
                request_id=str(resumed[0].id),
                pujari_id=str(pujari_id),
            )
            return resumed

    now = _now()
    request_id = uuid.uuid4()
    nonce = secrets.token_urlsafe(32)
    nonce_hash = _hash_nonce(nonce)
    placeholder_vendor_id = f"local:{request_id}"
    expires_at = now + dt.timedelta(minutes=settings.KYC_REQUEST_TTL_MINUTES)

    row = KycVerificationRequest(
        id=request_id,
        pujari_id=pujari_id,
        vendor=settings.KYC_VENDOR,
        kind="digilocker",
        vendor_request_id=placeholder_vendor_id,
        status="created",
        nonce_hash=nonce_hash,
        review_flags=[],
        created_at=now,
        updated_at=now,
        expires_at=expires_at,
    )
    db.add(row)
    await db.flush()

    consent = KycConsent(
        id=uuid.uuid4(),
        pujari_id=pujari_id,
        request_id=request_id,
        purpose=KYC_CONSENT_PURPOSE_DIGILOCKER_AADHAAR,
        text_version=KYC_CONSENT_TEXT_VERSION,
        consent_text_hash=_consent_text_hash(),
        granted_at=now,
        ip=ip,
        user_agent=user_agent,
    )
    db.add(consent)
    await db.flush()

    redirect_with_nonce = _append_query(
        settings.KYC_REDIRECT_URL,
        {"kyc_nonce": nonce},
    )

    vendor = get_kyc_vendor()
    try:
        started = await vendor.start_digilocker(redirect_url=redirect_with_nonce)
    except KycVendorError as exc:
        log.error(
            "kyc_vendor_error",
            vendor=vendor.vendor_name,
            error_code=exc.code,
            pujari_id=str(pujari_id),
        )
        if exc.code == "vendor_auth":
            log.error("kyc_vendor_auth_misconfig", pujari_id=str(pujari_id))
            raise PartnerKycError("KYC vendor misconfigured.", status_code=500) from exc
        raise PartnerKycError("KYC vendor unavailable.", status_code=502) from exc

    updated = (
        await db.execute(
            text(
                """
                UPDATE kyc_verification_requests
                SET vendor_request_id = :vid,
                    status = 'created',
                    expires_at = :exp,
                    updated_at = now()
                WHERE id = :id AND vendor_request_id = :placeholder
                """
            ),
            {
                "vid": started.vendor_request_id,
                "exp": started.expires_at,
                "id": str(request_id),
                "placeholder": placeholder_vendor_id,
            },
        )
    ).rowcount
    if updated != 1:
        raise PartnerKycError("Failed to bind vendor request.", status_code=409)

    await db.refresh(row)
    row.vendor_request_id = started.vendor_request_id
    row.expires_at = started.expires_at
    log.info(
        "kyc_request_started",
        request_id=str(request_id),
        vendor=vendor.vendor_name,
        status="created",
        pujari_id=str(pujari_id),
    )
    return row, started.url


async def _request_by_vendor_id(
    db: AsyncSession, vendor_request_id: str
) -> KycVerificationRequest | None:
    return (
        await db.execute(
            select(KycVerificationRequest).where(
                KycVerificationRequest.vendor_request_id == vendor_request_id
            )
        )
    ).scalar_one_or_none()


async def handle_callback(
    db: AsyncSession,
    *,
    vendor_request_id: str,
    success: bool,
    nonce: str | None,
    scope: str | None,
    error_code: str | None,
    error_message: str | None,
) -> KycVerificationRequest:
    row = await _request_by_vendor_id(db, vendor_request_id)
    if row is None:
        raise PartnerKycError("KYC request not found.", status_code=404)
    if not nonce or _hash_nonce(nonce) != row.nonce_hash:
        raise PartnerKycError("Invalid or missing nonce.", status_code=403)

    if not success:
        await db.execute(
            text(
                """
                UPDATE kyc_verification_requests
                SET status = 'failed',
                    scope = :scope,
                    error_code = :ec,
                    error_message = :em,
                    updated_at = now()
                WHERE id = :id AND status IN ('created', 'authenticated')
                """
            ),
            {
                "scope": scope,
                "ec": error_code,
                "em": error_message,
                "id": str(row.id),
            },
        )
        await db.refresh(row)
        return row

    updated = (
        await db.execute(
            text(
                """
                UPDATE kyc_verification_requests
                SET status = 'authenticated',
                    scope = COALESCE(:scope, scope),
                    updated_at = now()
                WHERE id = :id AND status IN ('created', 'authenticated')
                """
            ),
            {"scope": scope, "id": str(row.id)},
        )
    ).rowcount
    if updated:
        log.info(
            "kyc_request_authenticated",
            request_id=str(row.id),
            vendor=row.vendor,
            status="authenticated",
            pujari_id=str(row.pujari_id),
        )
    await db.refresh(row)
    return row


async def _download_url(url: str) -> bytes:
    async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.content


async def _upsert_document(
    db: AsyncSession,
    *,
    pujari_id: uuid.UUID,
    doc_type: str,
    file_url: str,
    vendor_request_id: str,
    document_id: uuid.UUID | None = None,
    doc_status: str = "pending",
) -> uuid.UUID:
    existing = (
        await db.execute(
            select(PujariDocument).where(
                PujariDocument.pujari_id == pujari_id,
                PujariDocument.doc_type == doc_type,
                PujariDocument.file_url == file_url,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing.id

    await db.execute(
        text(
            """
            UPDATE pujari_documents
            SET is_current = false
            WHERE pujari_id = :pid AND doc_type = :dtype AND is_current = true
            """
        ),
        {"pid": str(pujari_id), "dtype": doc_type},
    )
    version = (
        await db.execute(
            text(
                """
                SELECT COALESCE(MAX(version), 0) + 1
                FROM pujari_documents
                WHERE pujari_id = :pid AND doc_type = :dtype
                """
            ),
            {"pid": str(pujari_id), "dtype": doc_type},
        )
    ).scalar_one()
    doc = PujariDocument(
        id=document_id or uuid.uuid4(),
        pujari_id=pujari_id,
        doc_type=doc_type,
        file_url=file_url,
        version=int(version),
        is_current=True,
        status=doc_status,
        uploaded_at=_now(),
    )
    db.add(doc)
    await db.flush()
    return doc.id


async def _register_identity(
    db: AsyncSession,
    *,
    pujari_id: uuid.UUID,
    digilocker_id: str,
) -> None:
    digest = _hash_digilocker_id(digilocker_id)
    denied = (
        await db.execute(
            select(KycIdentityRegistry).where(
                KycIdentityRegistry.digilocker_id_hash == digest,
                KycIdentityRegistry.state == "denied",
            )
        )
    ).scalar_one_or_none()
    if denied is not None:
        raise PartnerKycError(
            "This identity is blocked from registration.",
            status_code=409,
        )

    active_other = (
        await db.execute(
            select(KycIdentityRegistry).where(
                KycIdentityRegistry.digilocker_id_hash == digest,
                KycIdentityRegistry.state == "active",
                KycIdentityRegistry.pujari_id != pujari_id,
            )
        )
    ).scalar_one_or_none()
    if active_other is not None:
        raise PartnerKycError(
            "This DigiLocker identity is already linked to another account.",
            status_code=409,
        )

    existing_same = (
        await db.execute(
            select(KycIdentityRegistry).where(
                KycIdentityRegistry.digilocker_id_hash == digest,
                KycIdentityRegistry.pujari_id == pujari_id,
            )
        )
    ).scalar_one_or_none()
    if existing_same is not None:
        return

    now = _now()
    try:
        db.add(
            KycIdentityRegistry(
                id=uuid.uuid4(),
                digilocker_id_hash=digest,
                pujari_id=pujari_id,
                state="active",
                created_at=now,
                updated_at=now,
            )
        )
        await db.flush()
    except IntegrityError:
        conflict = (
            await db.execute(
                select(KycIdentityRegistry).where(
                    KycIdentityRegistry.digilocker_id_hash == digest
                )
            )
        ).scalar_one_or_none()
        if conflict is not None and conflict.pujari_id != pujari_id:
            raise PartnerKycError(
                "This DigiLocker identity is already linked to another account.",
                status_code=409,
            )


async def _finalize_locked(
    db: AsyncSession,
    row: KycVerificationRequest,
) -> list[str]:
    if row.status == "success":
        return list(SCOPE_TO_DOC_TYPES.get("ADHAR", ()))

    vendor = get_kyc_vendor()
    try:
        vendor_status = await vendor.get_request_status(row.vendor_request_id)
    except KycVendorError as exc:
        log.error(
            "kyc_vendor_error",
            request_id=str(row.id),
            vendor=vendor.vendor_name,
            error_code=exc.code,
        )
        raise PartnerKycError("KYC vendor unavailable.", status_code=502) from exc

    if vendor_status.status in ("failed", "expired"):
        await db.execute(
            text(
                """
                UPDATE kyc_verification_requests
                SET status = :st, scope = :scope, updated_at = now()
                WHERE id = :id AND status IN ('created', 'authenticated')
                """
            ),
            {"st": vendor_status.status, "scope": vendor_status.scope, "id": str(row.id)},
        )
        await db.refresh(row)
        return []

    if vendor_status.status == "authenticated" and row.status == "created":
        await db.execute(
            text(
                """
                UPDATE kyc_verification_requests
                SET status = 'authenticated',
                    scope = COALESCE(:scope, scope),
                    updated_at = now()
                WHERE id = :id AND status = 'created'
                """
            ),
            {"scope": vendor_status.scope, "id": str(row.id)},
        )
        await db.refresh(row)
        log.info(
            "kyc_request_authenticated",
            request_id=str(row.id),
            vendor=row.vendor,
            status="authenticated",
            pujari_id=str(row.pujari_id),
        )

    if row.status != "authenticated":
        return []

    digilocker_id = vendor_status.digilocker_id
    if digilocker_id:
        await _register_identity(db, pujari_id=row.pujari_id, digilocker_id=digilocker_id)

    try:
        identity = await vendor.fetch_aadhaar(row.vendor_request_id)
    except KycVendorError as exc:
        raise PartnerKycError("Failed to fetch Aadhaar from vendor.", status_code=502) from exc

    user = (
        await db.execute(
            select(User).join(Pujari, Pujari.user_id == User.id).where(
                Pujari.id == row.pujari_id
            )
        )
    ).scalar_one()

    flags: list[str] = []
    age = _age_from_dob(identity.date_of_birth)
    if age is not None and age < 18:
        flags.append("age_under_18")
    if _names_mismatch(user.full_name, identity.name):
        flags.append("name_mismatch")

    vendor_prefix = row.vendor_request_id
    created_types: list[str] = []
    partner_folder = kyc_partner_folder(user.phone, row.pujari_id)

    try:
        if identity.photo_base64:
            photo_bytes = base64.b64decode(identity.photo_base64)
            key = (
                f"kyc/{partner_folder}/identity_proof/{vendor_prefix}/aadhaar_photo.jpg"
            )
            store_kyc_bytes(s3_key=key, body=photo_bytes, content_type="image/jpeg")
            await _upsert_document(
                db,
                pujari_id=row.pujari_id,
                doc_type="identity_proof",
                file_url=key,
                vendor_request_id=vendor_prefix,
            )
            created_types.append("identity_proof")

        if identity.xml_file_url:
            xml_bytes = await _download_url(identity.xml_file_url)
            key = f"kyc/{partner_folder}/address_proof/{vendor_prefix}/aadhaar.xml"
            store_kyc_bytes(s3_key=key, body=xml_bytes, content_type="application/xml")
            await _upsert_document(
                db,
                pujari_id=row.pujari_id,
                doc_type="address_proof",
                file_url=key,
                vendor_request_id=vendor_prefix,
            )
            created_types.append("address_proof")
    except KycStorageNotConfigured as exc:
        raise PartnerKycError(
            "KYC document storage not configured. Set S3_BUCKET_KYC and credentials or IAM role.",
            status_code=502,
        ) from exc
    except KycStorageError as exc:
        raise PartnerKycError(str(exc), status_code=502) from exc

    try:
        await vendor.revoke(row.vendor_request_id)
    except KycVendorError:
        log.warning(
            "kyc_revoke_failed",
            request_id=str(row.id),
            vendor_request_id=row.vendor_request_id,
        )

    await db.execute(
        text(
            """
            UPDATE kyc_verification_requests
            SET status = 'success',
                scope = COALESCE(:scope, scope),
                review_flags = CAST(:flags AS jsonb),
                updated_at = now()
            WHERE id = :id AND status IN ('created', 'authenticated')
            """
        ),
        {
            "scope": vendor_status.scope,
            "flags": json.dumps(flags),
            "id": str(row.id),
        },
    )
    log.info(
        "kyc_request_finalized",
        request_id=str(row.id),
        vendor=row.vendor,
        status="success",
        pujari_id=str(row.pujari_id),
    )
    return created_types


async def poll_and_finalize(
    db: AsyncSession,
    *,
    request_id: uuid.UUID,
    pujari_id: uuid.UUID,
) -> tuple[KycVerificationRequest, list[str]]:
    await _lazy_expire_stale(db, pujari_id)
    row = (
        await db.execute(
            select(KycVerificationRequest).where(
                KycVerificationRequest.id == request_id,
                KycVerificationRequest.pujari_id == pujari_id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise PartnerKycError("KYC request not found.", status_code=404)

    if row.status in _TERMINAL_STATUSES:
        return row, []

    if row.status not in _NON_TERMINAL_STATUSES:
        return row, []

    lock_key = f"kyc_finalize:{row.vendor_request_id}"
    acquired = await redis_set_nx(lock_key, "1", ex=_FINALIZE_LOCK_SECONDS)
    if not acquired:
        await db.refresh(row)
        return row, []

    try:
        await db.execute(
            text(
                "SELECT id FROM kyc_verification_requests WHERE id = :id FOR UPDATE"
            ),
            {"id": str(row.id)},
        )
        created: list[str] = []
        if row.status in _NON_TERMINAL_STATUSES:
            created = await _finalize_locked(db, row)
        await db.refresh(row)
        return row, created
    finally:
        await redis_delete(lock_key)


async def presign_selfie(
    db: AsyncSession,
    *,
    pujari_id: uuid.UUID,
    content_type: str,
    content_length: int,
) -> tuple[uuid.UUID, str, int, str]:
    phone = (
        await db.execute(
            select(User.phone)
            .join(Pujari, Pujari.user_id == User.id)
            .where(Pujari.id == pujari_id)
        )
    ).scalar_one_or_none()
    partner_folder = kyc_partner_folder(phone, pujari_id)
    doc_id = uuid.uuid4()
    ext = content_type.split("/", 1)[1].replace("jpeg", "jpg")
    s3_key = f"kyc/{partner_folder}/photo/{doc_id}.{ext}"
    url, expires = presign_kyc_put(
        s3_key=s3_key,
        content_type=content_type,
        content_length=content_length,
    )
    await _upsert_document(
        db,
        pujari_id=pujari_id,
        doc_type="photo",
        file_url=s3_key,
        vendor_request_id=str(doc_id),
        document_id=doc_id,
        doc_status="uploading",
    )
    return doc_id, url, expires, s3_key


async def confirm_selfie(
    db: AsyncSession,
    *,
    pujari_id: uuid.UUID,
    document_id: uuid.UUID,
) -> PujariDocument:
    """Verify selfie landed in S3; strip JPEG EXIF/GPS and re-store."""
    doc = (
        await db.execute(
            select(PujariDocument).where(
                PujariDocument.id == document_id,
                PujariDocument.pujari_id == pujari_id,
                PujariDocument.doc_type == "photo",
                PujariDocument.is_current.is_(True),
            )
        )
    ).scalar_one_or_none()
    if doc is None:
        raise PartnerKycError("Selfie document not found.", status_code=404)
    if doc.status not in ("uploading", "pending"):
        raise PartnerKycError(
            f"Selfie document is already {doc.status}.",
            status_code=409,
        )

    try:
        body, content_type = fetch_kyc_bytes(doc.file_url)
    except KycStorageNotConfigured as exc:
        raise PartnerKycError(
            "KYC document storage not configured.",
            status_code=502,
        ) from exc
    except KycStorageError as exc:
        raise PartnerKycError(str(exc), status_code=422) from exc

    ct = (content_type or "image/jpeg").split(";")[0].strip().lower()
    s3_key = doc.file_url
    if ct in ("image/jpeg", "image/jpg"):
        body = _strip_jpeg_exif(body)
        store_kyc_bytes(s3_key=s3_key, body=body, content_type="image/jpeg")
    elif ct in ("image/png", "image/webp"):
        pass
    else:
        raise PartnerKycError(
            f"Unsupported selfie content type: {content_type}",
            status_code=422,
        )

    doc.uploaded_at = _now()
    doc.status = "pending"
    await db.flush()
    return doc


async def get_partner_kyc_status(
    db: AsyncSession, pujari_id: uuid.UUID
) -> tuple[
    str,
    list[tuple[str, str | None, uuid.UUID | None]],
    KycVerificationRequest | None,
]:
    await _lazy_expire_stale(db, pujari_id)
    pujari = (
        await db.execute(select(Pujari).where(Pujari.id == pujari_id))
    ).scalar_one_or_none()
    if pujari is None:
        raise PartnerKycError("Pujari not found.", status_code=404)

    live = await _get_live_request(db, pujari_id)

    docs = (
        await db.execute(
            select(PujariDocument).where(
                PujariDocument.pujari_id == pujari_id,
                PujariDocument.is_current.is_(True),
            )
        )
    ).scalars().all()
    by_type = {d.doc_type: d for d in docs}
    required: list[tuple[str, str | None, uuid.UUID | None]] = []
    for doc_type in REQUIRED_DOC_TYPES:
        doc = by_type.get(doc_type)
        if doc is None:
            required.append((doc_type, None, None))
        else:
            visible = _partner_visible_doc_status(doc.status)
            required.append((doc_type, visible, doc.id if visible else None))
    return pujari.verification_status, required, live


async def digilocker_resume_url(live: KycVerificationRequest) -> str | None:
    """Best-effort vendor URL for an in-flight `created` request (service-layer vendor call)."""
    if live.status != "created" or live.vendor_request_id.startswith("local:"):
        return None
    vendor = get_kyc_vendor()
    try:
        vendor_status = await vendor.get_request_status(live.vendor_request_id)
    except KycVendorError:
        return None
    return vendor_status.url


async def latest_digilocker_review_flags(
    db: AsyncSession, pujari_id: uuid.UUID
) -> list[str]:
    row = (
        await db.execute(
            select(KycVerificationRequest)
            .where(
                KycVerificationRequest.pujari_id == pujari_id,
                KycVerificationRequest.kind == "digilocker",
            )
            .order_by(KycVerificationRequest.updated_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if row is None or not isinstance(row.review_flags, list):
        return []
    return list(row.review_flags)


async def deny_identity(
    db: AsyncSession,
    *,
    actor_user_id: uuid.UUID,
    denied_reason: str,
    digilocker_id_hash: str | None,
    pujari_id: uuid.UUID | None,
) -> KycIdentityRegistry:
    if digilocker_id_hash:
        digest = digilocker_id_hash
    elif pujari_id:
        reg = (
            await db.execute(
                select(KycIdentityRegistry).where(
                    KycIdentityRegistry.pujari_id == pujari_id,
                    KycIdentityRegistry.state == "active",
                )
            )
        ).scalar_one_or_none()
        if reg is None:
            raise PartnerKycError("No active identity registry for pujari.", status_code=404)
        digest = reg.digilocker_id_hash
    else:
        raise PartnerKycError(
            "Provide digilocker_id_hash or pujari_id.",
            status_code=422,
        )

    row = (
        await db.execute(
            select(KycIdentityRegistry).where(
                KycIdentityRegistry.digilocker_id_hash == digest
            )
        )
    ).scalar_one_or_none()
    now = _now()
    if row is None:
        row = KycIdentityRegistry(
            id=uuid.uuid4(),
            digilocker_id_hash=digest,
            pujari_id=pujari_id,
            state="denied",
            denied_reason=denied_reason,
            denied_by=actor_user_id,
            denied_at=now,
            created_at=now,
            updated_at=now,
        )
        db.add(row)
    else:
        row.state = "denied"
        row.denied_reason = denied_reason
        row.denied_by = actor_user_id
        row.denied_at = now
        row.updated_at = now
    await db.flush()
    return row
