"""Shared helpers for live KYC E2E tests (selfie + optional admin)."""
from __future__ import annotations

import os
import time
import uuid
from pathlib import Path

import httpx
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")

API_BASE = os.environ.get("E2E_API_UPSTREAM", "http://127.0.0.1:8000").rstrip("/")

MIN_JPEG = (
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

EXIF_JPEG = (
    b"\xff\xd8\xff\xe1\x00\x10Exif\x00\x00MM\x00\x00\x00\x00\x00\x00"
    + MIN_JPEG[2:]
)


def api_root() -> str:
    return API_BASE.replace("/v1", "").rstrip("/")


def api_health_ok() -> bool:
    try:
        with httpx.Client(timeout=5.0) as client:
            res = client.get(f"{api_root()}/health")
        return res.status_code == 200
    except httpx.HTTPError:
        return False


def s3_configured() -> bool:
    return bool(os.environ.get("S3_BUCKET_KYC", "").strip())


def require_s3() -> None:
    if not s3_configured():
        raise RuntimeError("S3_BUCKET_KYC not set in .env")


def admin_headers() -> dict[str, str] | None:
    phone = os.environ.get("ADMIN_TEST_PHONE", "").strip()
    secret = os.environ.get("ADMIN_TOTP_SECRET", "").strip()
    if not phone or not secret:
        return None
    from app.core import totp

    code = totp.totp_at(secret, at=int(time.time()))
    with httpx.Client(timeout=15.0) as client:
        res = client.post(
            f"{API_BASE}/v1/admin/auth/login",
            json={"phone": phone, "code": code},
        )
    if res.status_code != 200:
        raise RuntimeError(f"Admin login failed ({res.status_code}): {res.text}")
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def pujari_session(
    *,
    phone: str | None = None,
    register: bool = True,
) -> tuple[httpx.Client, dict[str, str], str]:
    """Return (client, auth_headers, phone). Client is left open for caller."""
    phone = phone or f"+919{uuid.uuid4().int % 1_000_000_000:09d}"
    client = httpx.Client(timeout=60.0)
    headers: dict[str, str] | None = None
    last_err = ""
    for attempt in range(5):
        otp_req = client.post(f"{API_BASE}/v1/auth/otp/request", json={"phone": phone})
        if otp_req.status_code == 429:
            time.sleep(1.0 + attempt * 0.5)
            continue
        if otp_req.status_code != 202:
            last_err = f"otp/request → {otp_req.status_code} {otp_req.text}"
            time.sleep(0.5)
            continue
        otp_body = otp_req.json()
        otp = otp_body.get("otp_dev_only")
        if not otp and phone == os.environ.get("KYC_TEST_PHONE", "").strip():
            otp = os.environ.get("KYC_TEST_OTP", "").strip()
        if not otp:
            client.close()
            raise RuntimeError(
                "Set DEBUG=true for otp_dev_only on API, or pass --phone with KYC_TEST_OTP"
            )
        verify = client.post(
            f"{API_BASE}/v1/auth/otp/verify",
            json={"phone": phone, "otp": str(otp), "app_context": "pujari"},
        )
        if verify.status_code == 200:
            headers = {"Authorization": f"Bearer {verify.json()['access_token']}"}
            break
        last_err = f"otp/verify → {verify.status_code} {verify.text}"
        time.sleep(0.4 + attempt * 0.3)
    if headers is None:
        client.close()
        raise RuntimeError(last_err or "OTP login failed")
    if register:
        reg = client.post(
            f"{API_BASE}/v1/pujari/register",
            headers=headers,
            json={"bio": "KYC selfie E2E", "years_experience": 3},
        )
        if reg.status_code not in (200, 201):
            client.close()
            raise RuntimeError(f"register → {reg.status_code} {reg.text}")
    return client, headers, phone


def presign_selfie(
    client: httpx.Client,
    headers: dict[str, str],
    *,
    content_type: str = "image/jpeg",
    body: bytes = MIN_JPEG,
) -> dict:
    res = client.post(
        f"{API_BASE}/v1/pujari/documents",
        headers=headers,
        json={"content_type": content_type, "content_length": len(body)},
    )
    if res.status_code != 200:
        raise RuntimeError(f"presign → {res.status_code} {res.text}")
    return res.json()


def put_selfie(upload_url: str, body: bytes, content_type: str = "image/jpeg") -> None:
    with httpx.Client(timeout=60.0) as client:
        res = client.put(
            upload_url,
            content=body,
            headers={"Content-Type": content_type},
        )
    if res.status_code not in (200, 201):
        raise RuntimeError(f"S3 PUT → {res.status_code} {res.text}")


def confirm_selfie(
    client: httpx.Client,
    headers: dict[str, str],
    document_id: str,
) -> dict:
    res = client.post(
        f"{API_BASE}/v1/pujari/documents/{document_id}/confirm",
        headers=headers,
    )
    if res.status_code != 200:
        raise RuntimeError(f"confirm → {res.status_code} {res.text}")
    return res.json()


def selfie_upload_confirm(
    client: httpx.Client,
    headers: dict[str, str],
    *,
    body: bytes = MIN_JPEG,
    content_type: str = "image/jpeg",
) -> dict:
    presign = presign_selfie(client, headers, content_type=content_type, body=body)
    put_selfie(presign["upload_url"], body, content_type=content_type)
    confirm = confirm_selfie(client, headers, presign["document_id"])
    return {**presign, **confirm}


def fetch_s3_body(file_url: str) -> bytes:
    from app.services.kyc_storage import fetch_kyc_bytes

    body, _ = fetch_kyc_bytes(file_url)
    return body


def jpeg_has_exif(data: bytes) -> bool:
    i = 2
    while i < len(data) - 1:
        if data[i] != 0xff:
            break
        marker = data[i + 1]
        if marker == 0xe1:
            return True
        if marker in (0xd8, 0xd9):
            i += 2
            continue
        if i + 3 >= len(data):
            break
        seg_len = int.from_bytes(data[i + 2:i + 4], "big")
        i += 2 + seg_len
    return False
