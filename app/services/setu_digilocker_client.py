"""Setu DigiLocker KYC client — async httpx (request-path), mirrors razorpay_client.create_order."""
from __future__ import annotations

import datetime as dt
from typing import Any
from urllib.parse import urljoin

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


def _timeout() -> httpx.Timeout:
    read_s = max(5.0, float(get_settings().KYC_SETU_READ_TIMEOUT))
    return httpx.Timeout(connect=3.0, read=read_s, write=3.0, pool=3.0)

_SETU_STATUS_MAP = {
    "unauthenticated": "created",
    "authenticated": "authenticated",
    "revoked": "failed",
}


def _parse_iso(ts: str | None) -> dt.datetime | None:
    if not ts:
        return None
    try:
        return dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def _headers(*, product_instance_id: str | None = None) -> dict[str, str]:
    settings = get_settings()
    instance = (product_instance_id or settings.KYC_SETU_DIGILOCKER_PRODUCT_ID or "").strip()
    if not instance:
        raise KycVendorError(
            "Setu product instance id not configured",
            code="vendor_config",
            retryable=False,
        )
    return {
        "x-client-id": settings.KYC_SETU_CLIENT_ID,
        "x-client-secret": settings.KYC_SETU_CLIENT_SECRET,
        "x-product-instance-id": instance,
        "Content-Type": "application/json",
    }


def _pan_headers() -> dict[str, str]:
    settings = get_settings()
    pid = (settings.KYC_SETU_PAN_PRODUCT_ID or "").strip()
    if not pid:
        raise KycVendorError(
            "KYC_SETU_PAN_PRODUCT_ID not configured",
            code="vendor_config",
            retryable=False,
        )
    return _headers(product_instance_id=pid)


def _base_url() -> str:
    return get_settings().KYC_SETU_BASE_URL.rstrip("/")


def _map_status(setu_status: str) -> str:
    return _SETU_STATUS_MAP.get(setu_status.lower(), "created")


class SetuDigiLockerClient:
    vendor_name = "setu_digilocker"

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        not_found_code: str = "request_not_found",
        not_found_message: str = "Setu request not found",
    ) -> dict[str, Any]:
        url = urljoin(_base_url() + "/", path.lstrip("/"))
        hdrs = headers if headers is not None else _headers()
        try:
            async with httpx.AsyncClient(timeout=_timeout()) as client:
                resp = await client.request(method, url, headers=hdrs, json=json)
        except httpx.ReadTimeout as exc:
            log.error(
                "kyc_vendor_error",
                vendor=self.vendor_name,
                error_code="read_timeout",
                error="Setu DigiLocker read timeout",
            )
            raise KycVendorError(
                "DigiLocker is taking too long to respond. Try again in a minute.",
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

        if resp.status_code in (401, 403):
            raise KycVendorError(
                "Setu authentication failed — check KYC_SETU credentials",
                code="vendor_auth",
                retryable=False,
            )
        if resp.status_code >= 500:
            detail = f"Setu upstream error {resp.status_code}"
            try:
                err_body = resp.json()
                if isinstance(err_body.get("message"), str):
                    detail = err_body["message"]
                req_id = err_body.get("request_id")
                if req_id:
                    detail = f"{detail} (request_id={req_id})"
            except ValueError:
                pass
            raise KycVendorError(
                detail,
                code="upstream_error",
                retryable=True,
            )
        if resp.status_code == 404:
            raise KycVendorError(
                not_found_message,
                code=not_found_code,
                retryable=False,
            )

        try:
            body = resp.json()
        except ValueError as exc:
            raise KycVendorError("Invalid JSON from Setu", retryable=True) from exc

        if resp.status_code >= 400:
            err = body.get("error") or {}
            raise KycVendorError(
                str(err.get("detail") or body),
                code=str(err.get("code") or "bad_request"),
                retryable=resp.status_code >= 500,
            )

        return body

    async def start_digilocker(self, *, redirect_url: str) -> KycStartResult:
        body = await self._request(
            "POST",
            "/api/digilocker/",
            json={"redirectUrl": redirect_url},
        )
        expires = _parse_iso(body.get("validUpto"))
        if expires is None:
            raise KycVendorError("Setu start missing validUpto", retryable=True)
        return KycStartResult(
            vendor_request_id=str(body["id"]),
            status=_map_status(str(body.get("status", "unauthenticated"))),
            url=str(body["url"]),
            expires_at=expires,
        )

    async def get_request_status(self, vendor_request_id: str) -> KycStatusResult:
        body = await self._request("GET", f"/api/digilocker/{vendor_request_id}/status")
        user_details = body.get("digilockerUserDetails") or {}
        scope_raw = body.get("scope")
        scope = str(scope_raw) if scope_raw else None
        return KycStatusResult(
            vendor_request_id=str(body["id"]),
            status=_map_status(str(body.get("status", "unauthenticated"))),
            url=body.get("url"),
            expires_at=_parse_iso(body.get("validUpto")),
            scope=scope,
            digilocker_id=user_details.get("digilockerId"),
        )

    async def fetch_aadhaar(self, vendor_request_id: str) -> KycIdentity:
        body = await self._request("GET", f"/api/digilocker/{vendor_request_id}/aadhaar")
        aadhaar = body.get("aadhaar") or {}
        address_raw = aadhaar.get("address") or {}
        xml = aadhaar.get("xml") or {}
        address = KycAadhaarAddress(
            care_of=address_raw.get("careOf"),
            country=address_raw.get("country"),
            district=address_raw.get("district"),
            house=address_raw.get("house"),
            landmark=address_raw.get("landmark"),
            locality=address_raw.get("locality"),
            pin=address_raw.get("pin"),
            state=address_raw.get("state"),
            street=address_raw.get("street"),
            sub_district=address_raw.get("subDistrict"),
            vtc=address_raw.get("vtc"),
        )
        return KycIdentity(
            name=aadhaar.get("name"),
            date_of_birth=aadhaar.get("dateOfBirth"),
            gender=aadhaar.get("gender"),
            masked_number=aadhaar.get("maskedNumber"),
            photo_base64=aadhaar.get("photo"),
            address=address,
            xml_file_url=xml.get("fileUrl"),
            digilocker_id=None,
        )

    async def revoke(self, vendor_request_id: str) -> None:
        try:
            await self._request("GET", f"/api/digilocker/{vendor_request_id}/revoke")
        except KycVendorError as exc:
            if exc.code in ("request_not_found", "user_not_authenticated"):
                log.info(
                    "kyc_revoke_skipped",
                    vendor_request_id=vendor_request_id,
                    code=exc.code,
                )
                return
            raise

    async def verify_pan(
        self, *, pan: str, consent: bool, reason: str
    ) -> KycPanVerifyResult:
        """Setu PAN verification (POST /api/verify/pan). Docs: docs.setu.co/data/pan/quickstart."""
        if not consent:
            raise KycVendorError(
                "Consent must be Y for Setu PAN verification",
                code="consent_required",
                retryable=False,
            )
        reason = reason.strip()
        if len(reason) < 20:
            raise KycVendorError(
                "Reason must be at least 20 characters for Setu PAN verification",
                code="reason_too_short",
                retryable=False,
            )
        body = await self._request(
            "POST",
            "/api/verify/pan",
            json={
                "pan": pan.strip().upper(),
                "consent": "Y",
                "reason": reason,
            },
            headers=_pan_headers(),
            not_found_code="pan_not_found",
            not_found_message="PAN not found with income tax authority",
        )
        verification = str(body.get("verification") or "").lower()
        data = body.get("data") if isinstance(body.get("data"), dict) else {}
        return KycPanVerifyResult(
            verification=verification or "failed",
            message=str(body.get("message") or ""),
            full_name=data.get("full_name") if isinstance(data, dict) else None,
            category=data.get("category") if isinstance(data, dict) else None,
            trace_id=str(body.get("traceId") or body.get("trace_id") or "") or None,
        )

    def verify_webhook_signature(self, body: bytes, signature: str) -> bool:
        return False

    def parse_webhook(self, payload: dict[str, Any]) -> KycWebhookEvent:
        return KycWebhookEvent(
            vendor_request_id=str(payload.get("id", "")),
            status=str(payload.get("status", "")),
            raw=payload,
        )
