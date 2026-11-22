"""Partner KYC onboarding orchestration (DigiLocker, vendor-agnostic)."""
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
from sqlalchemy import exists, select, text
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
from app.core.redis_client import redis_delete, redis_get, redis_set, redis_set_nx
from app.models.catalog import Pujari, PujariDocument
from app.models.identity import User
from app.models.kyc import KycConsent, KycIdentityRegistry, KycVerificationRequest
from app.services.apisathi_kyc_client import storage_vendor_request_id
from app.services.kyc_storage import (
    KycStorageError,
    KycStorageNotConfigured,
    SELFIE_CONTENT_TYPES,
    fetch_kyc_bytes,
    kyc_partner_folder,
    presign_kyc_put,
    store_kyc_bytes,
)
from app.services.kyc_types import KycAadhaarAddress, KycIdentity, KycVendorError
from app.services.kyc_vendor import active_kyc_vendor_name, get_kyc_vendor
from app.services.kyc_verification import recompute_pujari_verification
from app.services.profile_photo_publish import clear_customer_profile_photo_if_reference_stale

log = structlog.get_logger()
settings = get_settings()

_TERMINAL_STATUSES = frozenset({"success", "failed", "expired"})
_NON_TERMINAL_STATUSES = frozenset({"created", "authenticated"})
_FINALIZE_LOCK_SECONDS = 180
_DOB_FORMATS = ("%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y")
# Namespaced so a demographic key can never collide with a vendor DigiLocker id hash.
_AADHAAR_DEMOGRAPHIC_KEY_PREFIX = "aadhaar-demographic-v1"

# Identity review flags are admin-only; a blocked person must not learn they matched.
PARTNER_VISIBLE_REVIEW_FLAGS = frozenset({"name_mismatch", "age_under_18"})


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


def _is_placeholder_name(value: str | None) -> bool:
    """True when the user has not set a real display name (OTP default)."""
    normalized = _normalize_name(value)
    if not normalized:
        return True
    return normalized == _normalize_name("New User")


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


def _parse_dob(dob: str | None) -> dt.date | None:
    if not dob:
        return None
    for fmt in _DOB_FORMATS:
        try:
            return dt.datetime.strptime(dob.strip(), fmt).date()
        except ValueError:
            continue
    return None


def _age_from_dob(dob: str | None) -> int | None:
    born = _parse_dob(dob)
    if born is None:
        return None
    today = _now().date()
    return today.year - born.year - (
        (today.month, today.day) < (born.month, born.day)
    )


def _aadhaar_demographic_key(identity: KycIdentity) -> str | None:
    """Stable identity key for vendors that return no DigiLocker id.

    Name + DOB + Aadhaar last-4 from the UIDAI record; same Aadhaar ⇒ same key.
    """
    name = _normalize_name(identity.name)
    born = _parse_dob(identity.date_of_birth)
    last4 = re.sub(r"\D", "", identity.masked_number or "")[-4:]
    if not name or born is None or len(last4) != 4:
        return None
    return f"{_AADHAAR_DEMOGRAPHIC_KEY_PREFIX}|{name}|{born.isoformat()}|{last4}"


def partner_visible_review_flags(flags: object) -> list[str]:
    if not isinstance(flags, list):
        return []
    return [f for f in flags if f in PARTNER_VISIBLE_REVIEW_FLAGS]


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


def _consent_url_redis_key(request_id: uuid.UUID) -> str:
    return f"kyc:consent_url:{request_id}"


async def _store_consent_url(
    request_id: uuid.UUID, url: str, *, expires_at: dt.datetime
) -> None:
    if not url:
        return
    ttl = max(60, int((expires_at - _now()).total_seconds()))
    try:
        await redis_set(_consent_url_redis_key(request_id), url, ex=ttl)
    except Exception:
        log.warning("kyc_consent_url_cache_failed", request_id=str(request_id))


async def _load_consent_url(request_id: uuid.UUID) -> str | None:
    try:
        return await redis_get(_consent_url_redis_key(request_id))
    except Exception:
        log.warning("kyc_consent_url_load_failed", request_id=str(request_id))
        return None


def _vendor_poll_redis_key(vendor: str, vendor_request_id: str) -> str:
    """Stable Redis key for per-request vendor status poll throttling."""
    tail = vendor_request_id[-64:] if len(vendor_request_id) > 64 else vendor_request_id
    safe = re.sub(r"[^a-zA-Z0-9._-]", "_", tail)
    return f"kyc:vendor_poll:{vendor}:{safe}"


async def _acquire_vendor_status_poll(*, vendor: str, vendor_request_id: str) -> bool:
    """Return True if this worker may call the vendor status API now."""
    interval = settings.KYC_VENDOR_STATUS_POLL_MIN_SECONDS
    if interval <= 0:
        return True
    key = _vendor_poll_redis_key(vendor, vendor_request_id)
    return await redis_set_nx(key, "1", ex=interval)


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
    vendor = get_kyc_vendor(live.vendor)
    if not await _acquire_vendor_status_poll(
        vendor=live.vendor, vendor_request_id=live.vendor_request_id
    ):
        log.debug(
            "kyc_resume_poll_throttled",
            request_id=str(live.id),
            vendor=live.vendor,
        )
        return live, ""
    try:
        vendor_status = await vendor.get_request_status(live.vendor_request_id)
    except KycVendorError as exc:
        if exc.code == "request_not_found":
            await _expire_request(db, live.id)
            return None
        if exc.retryable:
            log.warning(
                "kyc_resume_vendor_deferred",
                request_id=str(live.id),
                error_code=exc.code,
            )
            return live, ""
        raise PartnerKycError("KYC vendor unavailable.", status_code=502) from exc
    if vendor_status.url:
        return live, vendor_status.url
    if vendor_status.status == "authenticated":
        return live, ""
    if vendor_status.status in ("failed", "expired") or live.expires_at < _now():
        await _expire_request(db, live.id)
        return None
    if vendor_status.status == "created":
        if not vendor_status.url and not vendor.supports_resume_url:
            # API Sathi (and similar): ``created`` + 422 fetch is normal until the user
            # finishes DigiLocker — poll-only resume, do not bill another init.
            cached_url = await _load_consent_url(live.id) or ""
            return live, cached_url
        if not vendor_status.url:
            # Setu-style: consent link expired and vendor cannot return a URL — new session.
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
    vendor_name = await active_kyc_vendor_name(db)

    row = KycVerificationRequest(
        id=request_id,
        pujari_id=pujari_id,
        vendor=vendor_name,
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
    phone = (
        await db.execute(
            select(User.phone)
            .join(Pujari, Pujari.user_id == User.id)
            .where(Pujari.id == pujari_id)
        )
    ).scalar_one_or_none()

    vendor = get_kyc_vendor(vendor_name)
    try:
        started = await vendor.start_digilocker(
            redirect_url=redirect_with_nonce,
            reference=str(request_id),
            mobile=phone,
        )
    except KycVendorError as exc:
        log.error(
            "kyc_vendor_error",
            vendor=vendor.vendor_name,
            error_code=exc.code,
            pujari_id=str(pujari_id),
        )
        if exc.code in ("vendor_auth", "vendor_config"):
            log.error("kyc_vendor_auth_misconfig", pujari_id=str(pujari_id))
            raise PartnerKycError("KYC vendor misconfigured.", status_code=500) from exc
        if exc.code == "invalid_mobile":
            raise PartnerKycError(str(exc), status_code=422) from exc
        raise PartnerKycError("KYC vendor unavailable.", status_code=502) from exc

    stored_vendor_id = started.vendor_request_id
    if vendor.vendor_name == "apisathi":
        stored_vendor_id = storage_vendor_request_id(
            started.vendor_request_id, request_id=request_id
        )

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
                "vid": stored_vendor_id,
                "exp": started.expires_at,
                "id": str(request_id),
                "placeholder": placeholder_vendor_id,
            },
        )
    ).rowcount
    if updated != 1:
        raise PartnerKycError("Failed to bind vendor request.", status_code=409)

    await db.refresh(row)
    row.vendor_request_id = stored_vendor_id
    row.expires_at = started.expires_at
    log.info(
        "kyc_request_started",
        request_id=str(request_id),
        vendor=vendor.vendor_name,
        status="created",
        pujari_id=str(pujari_id),
    )
    if started.url:
        await _store_consent_url(request_id, started.url, expires_at=row.expires_at)
    return row, started.url


async def _request_by_vendor_id(
    db: AsyncSession, vendor_request_id: str
) -> KycVerificationRequest | None:
    """Resolve a KYC row; API Sathi redirects use bare txn while DB may store ``txn::uuid``."""
    row = (
        await db.execute(
            select(KycVerificationRequest).where(
                KycVerificationRequest.vendor_request_id == vendor_request_id
            )
        )
    ).scalar_one_or_none()
    if row is not None:
        return row
    if "::" in vendor_request_id:
        return None
    return (
        await db.execute(
            select(KycVerificationRequest)
            .where(
                KycVerificationRequest.vendor == "apisathi",
                KycVerificationRequest.vendor_request_id.like(
                    f"{vendor_request_id}::%"
                ),
            )
            .order_by(KycVerificationRequest.created_at.desc())
            .limit(1)
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
    if not nonce:
        raise PartnerKycError("Invalid or missing nonce.", status_code=403)
    if not hmac.compare_digest(_hash_nonce(nonce), row.nonce_hash):
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


_PRIVATE_V4_RE = re.compile(
    r"^(10\.\d{1,3}\.\d{1,3}\.\d{1,3}|"
    r"192\.168\.\d{1,3}\.\d{1,3}|"
    r"172\.(1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})$"
)


def _vendor_doc_download_allowed(hostname: str | None) -> bool:
    """HTTPS vendor document links only; block loopback and private IPs (SSRF guard)."""
    if not hostname:
        return False
    host = hostname.lower().strip(".")
    if host in ("localhost", "127.0.0.1", "::1") or host.endswith(".local"):
        return False
    if _PRIVATE_V4_RE.match(host):
        return False
    return True


async def _download_url(url: str) -> bytes:
    parsed = urlparse((url or "").strip())
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("KYC vendor document URL must use HTTPS")
    if not _vendor_doc_download_allowed(parsed.hostname):
        raise ValueError("KYC vendor document URL host not allowed")

    max_bytes = settings.S3_KYC_MAX_BYTES
    timeout = httpx.Timeout(15.0)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        async with client.stream("GET", url) as resp:
            resp.raise_for_status()
            chunks: list[bytes] = []
            total = 0
            async for chunk in resp.aiter_bytes():
                total += len(chunk)
                if total > max_bytes:
                    raise ValueError("KYC vendor document exceeds size limit")
                chunks.append(chunk)
            return b"".join(chunks)


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
    if doc_type == "photo":
        await clear_customer_profile_photo_if_reference_stale(db, pujari_id=pujari_id)
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
    identity_key: str,
) -> list[str]:
    """Record the identity fingerprint; return admin review flags on a match.

    Matches never block onboarding — admins decide on flagged partners.
    """
    digest = _hash_digilocker_id(identity_key)
    existing = (
        await db.execute(
            select(KycIdentityRegistry).where(
                KycIdentityRegistry.digilocker_id_hash == digest
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        if existing.state == "denied":
            log.warning(
                "kyc_identity_blocked_match",
                pujari_id=str(pujari_id),
                registry_id=str(existing.id),
            )
            return ["identity_blocked"]
        if existing.pujari_id != pujari_id:
            log.warning(
                "kyc_identity_duplicate",
                pujari_id=str(pujari_id),
                other_pujari_id=str(existing.pujari_id),
            )
            return ["duplicate_identity"]
        return []

    now = _now()
    try:
        async with db.begin_nested():
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
    except IntegrityError:
        log.warning("kyc_identity_duplicate_race", pujari_id=str(pujari_id))
        return ["duplicate_identity"]
    return []


def _address_has_content(address: KycAadhaarAddress | None) -> bool:
    if address is None:
        return False
    return bool(
        address.pin
        or address.state
        or address.district
        or address.locality
        or address.house
        or address.street
    )


def _address_snapshot_dict(address: KycAadhaarAddress) -> dict[str, str | None]:
    return {
        "care_of": address.care_of,
        "country": address.country,
        "district": address.district,
        "house": address.house,
        "landmark": address.landmark,
        "locality": address.locality,
        "pin": address.pin,
        "state": address.state,
        "street": address.street,
        "sub_district": address.sub_district,
        "vtc": address.vtc,
    }


async def _ingest_aadhaar_demographic_snapshots(
    db: AsyncSession,
    *,
    identity: KycIdentity,
    pujari_id: uuid.UUID,
    vendor_prefix: str,
    partner_folder: str,
    skip_types: frozenset[str],
) -> list[str]:
    """When vendor fetch has demographics but no downloadable files (common in TEST keys)."""
    created: list[str] = []
    if (
        "identity_proof" not in skip_types
        and (identity.name or identity.masked_number)
    ):
        payload = {
            "source": "vendor_demographic_snapshot_v1",
            "name": identity.name,
            "masked_aadhaar": identity.masked_number,
            "dob": identity.date_of_birth,
            "gender": identity.gender,
        }
        key = (
            f"kyc/{partner_folder}/identity_proof/{vendor_prefix}/demographic.json"
        )
        store_kyc_bytes(
            s3_key=key,
            body=json.dumps(payload, separators=(",", ":")).encode(),
            content_type="application/json",
        )
        await _upsert_document(
            db,
            pujari_id=pujari_id,
            doc_type="identity_proof",
            file_url=key,
            vendor_request_id=vendor_prefix,
        )
        created.append("identity_proof")

    if "address_proof" not in skip_types and _address_has_content(identity.address):
        assert identity.address is not None
        payload = {
            "source": "vendor_address_snapshot_v1",
            **_address_snapshot_dict(identity.address),
        }
        key = (
            f"kyc/{partner_folder}/address_proof/{vendor_prefix}/address_snapshot.json"
        )
        store_kyc_bytes(
            s3_key=key,
            body=json.dumps(payload, separators=(",", ":")).encode(),
            content_type="application/json",
        )
        await _upsert_document(
            db,
            pujari_id=pujari_id,
            doc_type="address_proof",
            file_url=key,
            vendor_request_id=vendor_prefix,
        )
        created.append("address_proof")
    return created


async def _ingest_aadhaar_vendor_files(
    db: AsyncSession,
    *,
    identity: KycIdentity,
    pujari_id: uuid.UUID,
    vendor_prefix: str,
    partner_folder: str,
) -> list[str]:
    created: list[str] = []
    if identity.photo_base64:
        try:
            photo_bytes = base64.b64decode(identity.photo_base64)
        except (ValueError, TypeError):
            log.warning("kyc_photo_base64_invalid", pujari_id=str(pujari_id))
        else:
            key = (
                f"kyc/{partner_folder}/identity_proof/{vendor_prefix}/aadhaar_photo.jpg"
            )
            store_kyc_bytes(
                s3_key=key, body=photo_bytes, content_type="image/jpeg"
            )
            await _upsert_document(
                db,
                pujari_id=pujari_id,
                doc_type="identity_proof",
                file_url=key,
                vendor_request_id=vendor_prefix,
            )
            created.append("identity_proof")

    if identity.xml_file_url:
        try:
            xml_bytes = await _download_url(identity.xml_file_url)
        except (httpx.HTTPError, ValueError) as exc:
            log.warning(
                "kyc_xml_download_failed",
                pujari_id=str(pujari_id),
                error=str(exc),
            )
        else:
            key = (
                f"kyc/{partner_folder}/address_proof/{vendor_prefix}/aadhaar.xml"
            )
            store_kyc_bytes(
                s3_key=key, body=xml_bytes, content_type="application/xml"
            )
            await _upsert_document(
                db,
                pujari_id=pujari_id,
                doc_type="address_proof",
                file_url=key,
                vendor_request_id=vendor_prefix,
            )
            created.append("address_proof")

    created.extend(
        await _ingest_aadhaar_demographic_snapshots(
            db,
            identity=identity,
            pujari_id=pujari_id,
            vendor_prefix=vendor_prefix,
            partner_folder=partner_folder,
            skip_types=frozenset(created),
        )
    )
    return created


async def _missing_digilocker_doc_types(
    db: AsyncSession, pujari_id: uuid.UUID
) -> set[str]:
    rows = (
        await db.execute(
            select(PujariDocument.doc_type).where(
                PujariDocument.pujari_id == pujari_id,
                PujariDocument.is_current.is_(True),
                PujariDocument.doc_type.in_(("identity_proof", "address_proof")),
                PujariDocument.status.in_(("pending", "verified")),
            )
        )
    ).scalars().all()
    have = set(rows)
    return {"identity_proof", "address_proof"} - have


async def _backfill_digilocker_docs(
    db: AsyncSession, row: KycVerificationRequest
) -> list[str]:
    missing = await _missing_digilocker_doc_types(db, row.pujari_id)
    if not missing:
        return []
    vendor = get_kyc_vendor(row.vendor)
    try:
        identity = await vendor.fetch_aadhaar(row.vendor_request_id)
    except KycVendorError as exc:
        log.warning(
            "kyc_backfill_fetch_failed",
            request_id=str(row.id),
            error_code=exc.code,
        )
        return []
    user = (
        await db.execute(
            select(User.phone)
            .join(Pujari, Pujari.user_id == User.id)
            .where(Pujari.id == row.pujari_id)
        )
    ).scalar_one_or_none()
    partner_folder = kyc_partner_folder(user or "", row.pujari_id)
    try:
        created = await _ingest_aadhaar_vendor_files(
            db,
            identity=identity,
            pujari_id=row.pujari_id,
            vendor_prefix=row.vendor_request_id,
            partner_folder=partner_folder,
        )
    except (KycStorageNotConfigured, KycStorageError) as exc:
        log.warning("kyc_backfill_storage_failed", request_id=str(row.id), error=str(exc))
        return []
    return [doc_type for doc_type in created if doc_type in missing]


async def _finalize_locked(
    db: AsyncSession,
    row: KycVerificationRequest,
) -> list[str]:
    if row.status == "success":
        return list(SCOPE_TO_DOC_TYPES.get("ADHAR", ()))

    vendor = get_kyc_vendor(row.vendor)
    if not await _acquire_vendor_status_poll(
        vendor=row.vendor, vendor_request_id=row.vendor_request_id
    ):
        log.debug(
            "kyc_status_poll_throttled",
            request_id=str(row.id),
            vendor=row.vendor,
        )
        await db.refresh(row)
        return []
    try:
        vendor_status = await vendor.get_request_status(row.vendor_request_id)
    except KycVendorError as exc:
        if exc.retryable:
            log.warning(
                "kyc_vendor_poll_deferred",
                request_id=str(row.id),
                vendor=vendor.vendor_name,
                error_code=exc.code,
            )
            await db.refresh(row)
            return []
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
                SET status = :st,
                    scope = :scope,
                    error_code = COALESCE(:ec, error_code),
                    error_message = COALESCE(:em, error_message),
                    updated_at = now()
                WHERE id = :id AND status IN ('created', 'authenticated')
                """
            ),
            {
                "st": vendor_status.status,
                "scope": vendor_status.scope,
                "ec": vendor_status.error_code,
                "em": vendor_status.error_message,
                "id": str(row.id),
            },
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
    identity_key = (
        vendor_status.digilocker_id
        or identity.digilocker_id
        or _aadhaar_demographic_key(identity)
    )
    if identity_key:
        flags.extend(
            await _register_identity(db, pujari_id=row.pujari_id, identity_key=identity_key)
        )
    else:
        flags.append("identity_check_unavailable")
    age = _age_from_dob(identity.date_of_birth)
    if age is not None and age < 18:
        flags.append("age_under_18")
    aadhaar_name = (identity.name or "").strip()
    if aadhaar_name:
        legal_name = aadhaar_name[:150]
        if _is_placeholder_name(user.full_name):
            user.full_name = legal_name
            user.updated_at = _now()
        elif _names_mismatch(user.full_name, aadhaar_name):
            flags.append("name_mismatch")

    vendor_prefix = row.vendor_request_id
    created_types: list[str] = []
    partner_folder = kyc_partner_folder(user.phone, row.pujari_id)

    try:
        created_types.extend(
            await _ingest_aadhaar_vendor_files(
                db,
                identity=identity,
                pujari_id=row.pujari_id,
                vendor_prefix=vendor_prefix,
                partner_folder=partner_folder,
            )
        )
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
    try:
        await redis_delete(_consent_url_redis_key(row.id))
    except Exception:
        pass
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
        if row.status == "success" and row.kind == "digilocker":
            created = await _backfill_digilocker_docs(db, row)
            if created:
                return row, created
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


async def upload_selfie_body(
    db: AsyncSession,
    *,
    pujari_id: uuid.UUID,
    document_id: uuid.UUID,
    body: bytes,
    content_type: str,
) -> None:
    """Store selfie bytes server-side (mobile→API→S3; avoids OCI presigned PUT quirks)."""
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
    if doc.status != "uploading":
        raise PartnerKycError(
            f"Selfie document is already {doc.status}.",
            status_code=409,
        )

    ct = (content_type or "").split(";")[0].strip().lower()
    if ct not in SELFIE_CONTENT_TYPES:
        raise PartnerKycError(
            f"Unsupported selfie content type: {content_type or '(missing)'}",
            status_code=422,
        )
    expected_suffix = f".{SELFIE_CONTENT_TYPES[ct]}"
    if not doc.file_url.lower().endswith(expected_suffix):
        raise PartnerKycError(
            "Selfie Content-Type does not match the presigned document.",
            status_code=422,
        )

    try:
        store_kyc_bytes(s3_key=doc.file_url, body=body, content_type=ct)
    except KycStorageNotConfigured as exc:
        raise PartnerKycError(
            "KYC document storage not configured.",
            status_code=502,
        ) from exc
    except ValueError as exc:
        raise PartnerKycError(str(exc), status_code=422) from exc
    except KycStorageError as exc:
        raise PartnerKycError(str(exc), status_code=502) from exc


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
    await recompute_pujari_verification(db, pujari_id)
    return doc


async def _photo_change_under_review(
    db: AsyncSession, *, pujari_id: uuid.UUID
) -> bool:
    """Slice C — partner re-uploaded photo; ops must approve before customers see it."""
    pub = (
        await db.execute(
            text(
                """
                SELECT customer_profile_photo_doc_id::text
                FROM pujaris WHERE id = :pid
                """
            ),
            {"pid": str(pujari_id)},
        )
    ).scalar_one_or_none()
    published_id = uuid.UUID(pub) if pub else None

    current = (
        await db.execute(
            select(PujariDocument.id, PujariDocument.status).where(
                PujariDocument.pujari_id == pujari_id,
                PujariDocument.doc_type == "photo",
                PujariDocument.is_current.is_(True),
            )
        )
    ).first()
    if current is None:
        return False
    cur_id, cur_status = current[0], current[1]
    if cur_status not in ("pending", "rejected"):
        return False

    if published_id is not None and published_id != cur_id:
        return True

    legacy_verified_photo = (
        await db.execute(
            select(
                exists().where(
                    PujariDocument.pujari_id == pujari_id,
                    PujariDocument.doc_type == "photo",
                    PujariDocument.is_current.is_(False),
                    PujariDocument.status == "verified",
                )
            )
        )
    ).scalar()
    return bool(legacy_verified_photo)


async def get_partner_kyc_status(
    db: AsyncSession, pujari_id: uuid.UUID
) -> tuple[
    str,
    list[tuple[str, str | None, uuid.UUID | None]],
    KycVerificationRequest | None,
    bool,
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
    photo_change = await _photo_change_under_review(db, pujari_id=pujari_id)
    return pujari.verification_status, required, live, photo_change


async def digilocker_resume_url(live: KycVerificationRequest) -> str | None:
    """Best-effort vendor URL for an in-flight `created` request (service-layer vendor call)."""
    if live.status != "created" or live.vendor_request_id.startswith("local:"):
        return None
    cached = await _load_consent_url(live.id)
    if cached:
        return cached
    vendor = get_kyc_vendor(live.vendor)
    if not vendor.supports_resume_url:
        return None
    if not await _acquire_vendor_status_poll(
        vendor=live.vendor, vendor_request_id=live.vendor_request_id
    ):
        return None
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
