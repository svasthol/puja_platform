"""API Sathi KYC client (DigiLocker Aadhaar + PAN) — async httpx, same contract as Setu.

Docs: https://apisathi.in/docs/ (OpenAPI: https://apisathi.in/docs/openapi.json).
Every product is ``POST {base}/{slug}/`` with ``X-API-Key``; errors are
``{"error": {"code", "message", "call_id"}}``.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import re
import time
import uuid
from typing import Any
from urllib.parse import urlparse

import httpx
import structlog

from app.core.config import get_settings
from app.services.kyc_types import (
    KycAadhaarAddress,
    KycIdentity,
    KycPanVerifyResult,
    KycStartResult,
    KycStatusResult,
    KycVendorError,
    KycWebhookEvent,
)

log = structlog.get_logger()

_INIT_SLUG = "aadhaar-digilocker-init-v1"
_FETCH_SLUG = "aadhaar-digilocker-fetch-v1"
_PAN_SLUG = "pan-verification-v1"

_MAX_REDIRECT_URL_LEN = 512
_MAX_UID_LEN = 80
_TXN_ID_RE = re.compile(r"^[0-9]{6,32}$")
_MOBILE_RE = re.compile(r"^[6-9][0-9]{9}$")
# Customer-side DigiLocker outcomes (declined consent / no eAadhaar / Aadhaar not selected).
_CUSTOMER_FAILURE_RE = re.compile(r"DG100[123]")
# Vendor-side cooldown / idempotency (dashboard: DUPLICATE_REQUEST_THROTTLED).
_VENDOR_POLL_COOLDOWN_RE = re.compile(r"DUPLICATE|THROTTLE", re.IGNORECASE)

# A successful fetch is billed; status poll + Aadhaar fetch in one finalize must reuse it.
_VERIFIED_CACHE_TTL_SECONDS = 900
_VERIFIED_CACHE_MAX = 256

# API Sathi TEST keys return a fixed OpenAPI example transaction id; our DB key is
# (vendor, vendor_request_id). Namespace stored ids so retries and other partners
# do not collide while vendor API calls still use the bare transaction id.
_APISATHI_TEST_VID_SEP = "::"


def vendor_txn_for_api(vendor_request_id: str) -> str:
    """Strip in-app suffix before calling API Sathi."""
    return vendor_request_id.partition(_APISATHI_TEST_VID_SEP)[0]


def is_placeholder_kyc_url(url: str) -> bool:
    """OpenAPI/docs example hosts (e.g. digilocker.example) are not real DigiLocker links."""
    raw = (url or "").strip()
    if not raw:
        return False
    host = (urlparse(raw).hostname or "").lower()
    if not host:
        return False
    return host.endswith(".example") or host in ("localhost", "127.0.0.1")


def storage_vendor_request_id(
    vendor_txn: str, *, request_id: uuid.UUID | str | None = None
) -> str:
    """Persist a unique vendor_request_id when the vendor returns a shared test txn."""
    key = (_api_key() or "").strip()
    if key.startswith("test_") and request_id is not None:
        return f"{vendor_txn}{_APISATHI_TEST_VID_SEP}{request_id}"
    return vendor_txn


def _timeout() -> httpx.Timeout:
    read_s = max(5.0, float(get_settings().KYC_APISATHI_READ_TIMEOUT))
    return httpx.Timeout(connect=3.0, read=read_s, write=3.0, pool=3.0)


def _api_key() -> str:
    key = (get_settings().KYC_APISATHI_API_KEY or "").strip()
    if not key:
        raise KycVendorError(
            "KYC_APISATHI_API_KEY not configured",
            code="vendor_config",
            retryable=False,
        )
    return key


def _url(slug: str) -> str:
    # API Sathi requires the trailing slash on every product path.
    return f"{get_settings().KYC_APISATHI_BASE_URL.rstrip('/')}/{slug}/"


def normalize_indian_mobile(phone: str | None) -> str | None:
    """+91XXXXXXXXXX / 0XXXXXXXXXX / XXXXXXXXXX → 10-digit mobile, else None."""
    digits = re.sub(r"\D", "", phone or "")
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    return digits if _MOBILE_RE.match(digits) else None


def _error_parts(body: Any) -> tuple[str, str]:
    err = body.get("error") if isinstance(body, dict) else None
    if not isinstance(err, dict):
        return "", ""
    return str(err.get("code") or ""), str(err.get("message") or "")


def _strip_data_uri(value: str | None) -> str | None:
    if not value:
        return None
    if value.startswith("data:") and "," in value:
        return value.split(",", 1)[1]
    return value


class ApiSathiKycClient:
    vendor_name = "apisathi"
    supports_resume_url = False

    def __init__(self) -> None:
        self._verified: dict[str, tuple[float, dict[str, Any]]] = {}

    def _cache_get(self, transaction_id: str) -> dict[str, Any] | None:
        hit = self._verified.get(transaction_id)
        if hit is None:
            return None
        if time.monotonic() - hit[0] > _VERIFIED_CACHE_TTL_SECONDS:
            self._verified.pop(transaction_id, None)
            return None
        return hit[1]

    def _cache_put(self, transaction_id: str, body: dict[str, Any]) -> None:
        if len(self._verified) >= _VERIFIED_CACHE_MAX:
            oldest = min(self._verified, key=lambda k: self._verified[k][0])
            self._verified.pop(oldest, None)
        self._verified[transaction_id] = (time.monotonic(), body)

    async def _post(
        self,
        slug: str,
        payload: dict[str, Any],
        *,
        idempotency_key: str | None = None,
    ) -> tuple[int, Any]:
        """POST a product call; raise on transport/auth/billing/upstream errors.

        Returns ``(status_code, body)`` for 2xx and 4xx bodies the caller interprets.
        """
        headers = {
            "X-API-Key": _api_key(),
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key[:128]
        try:
            async with httpx.AsyncClient(timeout=_timeout()) as client:
                resp = await client.post(_url(slug), headers=headers, json=payload)
        except httpx.TimeoutException as exc:
            log.error("kyc_vendor_error", vendor=self.vendor_name, error_code="read_timeout")
            raise KycVendorError(
                "Verification service is taking too long to respond. Try again in a minute.",
                code="read_timeout",
                retryable=True,
            ) from exc
        except httpx.HTTPError as exc:
            log.error(
                "kyc_vendor_error",
                vendor=self.vendor_name,
                error_code="http_error",
                error=str(exc),
            )
            raise KycVendorError(str(exc), code="http_error", retryable=True) from exc

        try:
            body: Any = resp.json()
        except ValueError:
            body = {}
        code, message = _error_parts(body)
        status = resp.status_code

        if status in (401, 403):
            raise KycVendorError(
                "API Sathi rejected the API key — check KYC_APISATHI_API_KEY and product scope",
                code="vendor_auth",
                retryable=False,
            )
        if status == 402:
            log.error("kyc_vendor_wallet_empty", vendor=self.vendor_name, product=slug)
            raise KycVendorError(
                "API Sathi wallet balance too low",
                code="insufficient_balance",
                retryable=False,
            )
        if status == 410:
            log.error("kyc_vendor_product_retired", vendor=self.vendor_name, product=slug)
            raise KycVendorError(
                f"API Sathi product retired: {slug}",
                code="product_retired",
                retryable=False,
            )
        if status == 429 or status >= 500:
            raise KycVendorError(
                message or f"API Sathi upstream error {status}",
                code="rate_limited" if status == 429 else "upstream_error",
                retryable=True,
            )
        if status >= 400:
            return status, body
        if not isinstance(body, dict):
            raise KycVendorError("Invalid JSON from API Sathi", retryable=True)
        if code:
            raise KycVendorError(message or code, code=code.lower(), retryable=False)
        return status, body

    async def start_digilocker(
        self, *, redirect_url: str, reference: str, mobile: str | None = None
    ) -> KycStartResult:
        if len(redirect_url) > _MAX_REDIRECT_URL_LEN:
            raise KycVendorError(
                "KYC redirect URL exceeds API Sathi limit (512 chars)",
                code="vendor_config",
                retryable=False,
            )
        normalized_mobile = normalize_indian_mobile(mobile)
        if normalized_mobile is None:
            raise KycVendorError(
                "A valid Indian mobile number is required for DigiLocker verification",
                code="invalid_mobile",
                retryable=False,
            )
        status, body = await self._post(
            _INIT_SLUG,
            {
                "uid": reference[:_MAX_UID_LEN],
                "mobile": normalized_mobile,
                "redirectionUrl": redirect_url,
            },
            idempotency_key=f"digilocker-init:{reference[:_MAX_UID_LEN]}",
        )
        if status >= 400:
            code, message = _error_parts(body)
            raise KycVendorError(
                message or "API Sathi rejected the DigiLocker start request",
                code=(code or "bad_request").lower(),
                retryable=False,
            )
        transaction_id = str(body.get("transaction_id") or "")
        raw_kyc_url = str(body.get("kyc_url") or "")
        kyc_url = "" if is_placeholder_kyc_url(raw_kyc_url) else raw_kyc_url
        if raw_kyc_url and not kyc_url:
            log.info(
                "apisathi_placeholder_kyc_url",
                vendor=self.vendor_name,
                host=urlparse(raw_kyc_url).hostname,
            )
        if not body.get("verified") or not transaction_id:
            raise KycVendorError("API Sathi did not issue a DigiLocker link", retryable=True)
        if not kyc_url and not is_placeholder_kyc_url(raw_kyc_url):
            raise KycVendorError("API Sathi did not issue a DigiLocker link", retryable=True)
        # API Sathi returns no link expiry; the request TTL is ours.
        ttl = dt.timedelta(minutes=get_settings().KYC_REQUEST_TTL_MINUTES)
        return KycStartResult(
            vendor_request_id=transaction_id,
            status="created",
            url=kyc_url,
            expires_at=dt.datetime.now(dt.UTC) + ttl,
        )

    async def _fetch(self, transaction_id: str) -> KycStatusResult | dict[str, Any]:
        """Verified body (cached), or a non-success ``KycStatusResult``."""
        api_txn = vendor_txn_for_api(transaction_id)
        cached = self._cache_get(api_txn)
        if cached is not None:
            return cached
        if not _TXN_ID_RE.match(api_txn):
            raise KycVendorError(
                "Unknown API Sathi transaction id",
                code="request_not_found",
                retryable=False,
            )
        status, body = await self._post(
            _FETCH_SLUG,
            {"transaction_id": api_txn},
            idempotency_key=f"digilocker-fetch:{api_txn}",
        )
        if status == 200:
            if body.get("verified") is True:
                self._cache_put(api_txn, body)
                return body
            return KycStatusResult(
                vendor_request_id=transaction_id,
                status="failed",
                url=None,
                expires_at=None,
                scope=None,
                digilocker_id=None,
                error_code="not_verified",
                error_message=str(body.get("message") or "DigiLocker verification failed"),
            )
        code, message = _error_parts(body)
        if status == 422 and _VENDOR_POLL_COOLDOWN_RE.search(f"{code} {message}"):
            return KycStatusResult(
                vendor_request_id=transaction_id,
                status="created",
                url=None,
                expires_at=None,
                scope=None,
                digilocker_id=None,
            )
        if status in (400, 404):
            raise KycVendorError(
                message or "API Sathi transaction not found",
                code="request_not_found",
                retryable=False,
            )
        if status == 422 and _CUSTOMER_FAILURE_RE.search(f"{code} {message}"):
            return KycStatusResult(
                vendor_request_id=transaction_id,
                status="failed",
                url=None,
                expires_at=None,
                scope=None,
                digilocker_id=None,
                error_code=code or "customer_declined",
                error_message=message or None,
            )
        # 422 "transaction id for digilocker is not success" = customer has not finished yet.
        return KycStatusResult(
            vendor_request_id=transaction_id,
            status="created",
            url=None,
            expires_at=None,
            scope=None,
            digilocker_id=None,
        )

    async def get_request_status(self, vendor_request_id: str) -> KycStatusResult:
        result = await self._fetch(vendor_request_id)
        if isinstance(result, KycStatusResult):
            return result
        return KycStatusResult(
            vendor_request_id=vendor_request_id,
            status="authenticated",
            url=None,
            expires_at=None,
            scope="ADHAR",
            digilocker_id=None,
        )

    async def fetch_aadhaar(self, vendor_request_id: str) -> KycIdentity:
        result = await self._fetch(vendor_request_id)
        if isinstance(result, KycStatusResult):
            raise KycVendorError(
                "DigiLocker verification is not complete",
                code="not_ready",
                retryable=result.status == "created",
            )
        body = result
        addr = body.get("address") if isinstance(body.get("address"), dict) else {}
        address = KycAadhaarAddress(
            care_of=body.get("care_of") or addr.get("co") or addr.get("care_of"),
            country=addr.get("country"),
            district=addr.get("dist") or addr.get("district"),
            house=addr.get("house"),
            landmark=addr.get("landmark") or addr.get("lm"),
            locality=addr.get("loc") or addr.get("locality"),
            pin=addr.get("pc") or addr.get("pin"),
            state=addr.get("state"),
            street=addr.get("street"),
            sub_district=addr.get("subdist") or addr.get("sub_district"),
            vtc=addr.get("vtc"),
        )
        xml_url: str | None = None
        documents = body.get("documents")
        if isinstance(documents, list):
            for doc in documents:
                if not isinstance(doc, dict):
                    continue
                if str(doc.get("docExtension") or "").lower() == "xml" and doc.get("docLink"):
                    xml_url = str(doc["docLink"])
                    break
        return KycIdentity(
            name=body.get("name"),
            date_of_birth=body.get("dob"),
            gender=body.get("gender"),
            masked_number=body.get("masked_aadhaar"),
            photo_base64=_strip_data_uri(body.get("photo_base64")),
            address=address,
            xml_file_url=xml_url,
            digilocker_id=None,
        )

    async def revoke(self, vendor_request_id: str) -> None:
        self._verified.pop(vendor_txn_for_api(vendor_request_id), None)

    def pan_verification_enabled(self) -> bool:
        return bool((get_settings().KYC_APISATHI_API_KEY or "").strip())

    async def verify_pan(
        self, *, pan: str, consent: bool, reason: str
    ) -> KycPanVerifyResult:
        if not consent:
            raise KycVendorError(
                "Consent is required for PAN verification",
                code="consent_required",
                retryable=False,
            )
        pan_norm = pan.strip().upper()
        pan_key = hashlib.sha256(pan_norm.encode()).hexdigest()[:32]
        status, body = await self._post(
            _PAN_SLUG,
            {"pan": pan_norm},
            idempotency_key=f"pan-verify:{pan_key}",
        )
        if status >= 400:
            code, message = _error_parts(body)
            raise KycVendorError(
                message or "PAN could not be verified. Check the PAN and try again.",
                code="pan_not_found" if status == 422 else (code or "bad_request").lower(),
                retryable=False,
            )
        verified = body.get("verified") is True
        return KycPanVerifyResult(
            verification="success" if verified else "failed",
            message=str(
                body.get("message")
                or ("PAN verified successfully." if verified else "PAN could not be verified.")
            ),
            full_name=body.get("name"),
            category=body.get("category"),
        )

    def verify_webhook_signature(self, body: bytes, signature: str) -> bool:
        return False

    def parse_webhook(self, payload: dict[str, Any]) -> KycWebhookEvent:
        return KycWebhookEvent(
            vendor_request_id=str(payload.get("transaction_id", "")),
            status=str(payload.get("status", "")),
            raw=payload,
        )
