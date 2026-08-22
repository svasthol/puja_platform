"""Private KYC document storage — presigned GET (A-KYC)."""
from __future__ import annotations

import re
import uuid
from typing import Any
from urllib.parse import urlparse

import boto3
from botocore.client import BaseClient
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import get_settings

_NON_DIGIT_RE = re.compile(r"\D")


class KycStorageNotConfigured(Exception):
    """S3 credentials or KYC bucket not configured."""


class KycStorageError(Exception):
    """S3 upload or presign failed (credentials, bucket, or network)."""

    def __init__(self, message: str, aws_error_code: str | None = None) -> None:
        self.aws_error_code = aws_error_code
        super().__init__(message)


def kyc_partner_folder(phone: str | None, pujari_id: uuid.UUID) -> str:
    """Human-readable S3 prefix: E.164 digits (e.g. 917675834207) or pujari_id fallback."""
    digits = _NON_DIGIT_RE.sub("", (phone or "").strip())
    if digits:
        return digits
    return str(pujari_id)


def kyc_storage_configured() -> bool:
    settings = get_settings()
    bucket = (settings.S3_BUCKET_KYC or "").strip()
    if not bucket:
        return False
    ak = (settings.S3_ACCESS_KEY or "").strip()
    sk = (settings.S3_SECRET_KEY or "").strip()
    # Explicit keys or IAM role / instance profile via default boto3 chain.
    return bool(ak and sk) or (not ak and not sk)


def _effective_s3_endpoint(raw: str) -> str | None:
    s = (raw or "").strip()
    if not s or s.startswith("#"):
        return None
    if s.startswith("http://") or s.startswith("https://"):
        return s
    return None


def _s3_client_kwargs(settings: Any) -> dict[str, Any]:
    custom_endpoint = _effective_s3_endpoint(settings.S3_ENDPOINT_URL)
    aws_endpoint = (
        None
        if custom_endpoint
        else f"https://s3.{settings.S3_REGION}.amazonaws.com"
    )
    use_endpoint = custom_endpoint or aws_endpoint
    kwargs: dict[str, Any] = {
        "service_name": "s3",
        "region_name": settings.S3_REGION,
        "config": Config(signature_version="s3v4"),
    }
    ak = (settings.S3_ACCESS_KEY or "").strip()
    sk = (settings.S3_SECRET_KEY or "").strip()
    if ak and sk:
        kwargs["aws_access_key_id"] = ak
        kwargs["aws_secret_access_key"] = sk
    if use_endpoint:
        kwargs["endpoint_url"] = use_endpoint
    return kwargs


def get_s3_client() -> BaseClient:
    settings = get_settings()
    if not kyc_storage_configured():
        raise KycStorageNotConfigured(
            "S3_BUCKET_KYC must be set; provide S3_ACCESS_KEY+S3_SECRET_KEY or use IAM role."
        )
    kwargs = _s3_client_kwargs(settings)
    return boto3.client(**kwargs)


def file_url_to_s3_key(file_url: str) -> str:
    """Normalize stored file_url to an S3 object key."""
    s = (file_url or "").strip()
    if s.startswith("http://") or s.startswith("https://"):
        path = urlparse(s).path.lstrip("/")
        settings = get_settings()
        bucket = settings.S3_BUCKET_KYC
        if path.startswith(f"{bucket}/"):
            return path[len(bucket) + 1 :]
        return path
    return s.lstrip("/")


def fetch_kyc_bytes(file_url: str) -> tuple[bytes, str | None]:
    """Download a KYC object from S3. Returns (body, content_type)."""
    if not kyc_storage_configured():
        raise KycStorageNotConfigured("KYC S3 bucket is not configured.")
    settings = get_settings()
    key = file_url_to_s3_key(file_url)
    client = get_s3_client()
    try:
        resp = client.get_object(Bucket=settings.S3_BUCKET_KYC, Key=key)
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "ClientError")
        if code in ("404", "NoSuchKey", "NotFound"):
            raise KycStorageError(
                "KYC object not found in S3 — upload via presigned PUT first.",
                aws_error_code=code,
            ) from exc
        raise _storage_error_from_client(exc, "download") from exc
    except BotoCoreError as exc:
        raise KycStorageError(f"KYC S3 download failed: {exc}") from exc
    content_type = resp.get("ContentType")
    return resp["Body"].read(), content_type


def presign_kyc_get(file_url: str) -> tuple[str | None, int]:
    """Return (presigned_get_url, expires_in) or (None, 0) if storage not configured."""
    if not kyc_storage_configured():
        return None, 0
    settings = get_settings()
    key = file_url_to_s3_key(file_url)
    client = get_s3_client()
    expires = settings.S3_KYC_URL_EXPIRE_SECONDS
    url = client.generate_presigned_url(
        ClientMethod="get_object",
        Params={"Bucket": settings.S3_BUCKET_KYC, "Key": key},
        ExpiresIn=expires,
        HttpMethod="GET",
    )
    return url, expires


SELFIE_CONTENT_TYPES: dict[str, str] = {
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}


def presign_kyc_put(
    *,
    s3_key: str,
    content_type: str,
    content_length: int,
) -> tuple[str, int]:
    """Return (presigned_put_url, expires_in_seconds) for a private KYC object."""
    settings = get_settings()
    if not kyc_storage_configured():
        raise KycStorageNotConfigured("KYC S3 bucket is not configured.")
    ext = SELFIE_CONTENT_TYPES.get(content_type.lower())
    if ext is None:
        raise ValueError(f"Unsupported content type: {content_type}")
    if content_length < 1 or content_length > settings.S3_KYC_MAX_BYTES:
        raise ValueError(
            f"content_length must be between 1 and {settings.S3_KYC_MAX_BYTES}."
        )
    client = get_s3_client()
    expires = settings.S3_KYC_URL_EXPIRE_SECONDS
    params: dict[str, str] = {
        "Bucket": settings.S3_BUCKET_KYC,
        "Key": s3_key,
        "ContentType": content_type,
    }
    url = client.generate_presigned_url(
        ClientMethod="put_object",
        Params=params,
        ExpiresIn=expires,
        HttpMethod="PUT",
    )
    return url, expires


def _storage_error_from_client(exc: ClientError, action: str) -> KycStorageError:
    err = exc.response.get("Error", {})
    code = err.get("Code", "ClientError")
    msg = err.get("Message", str(exc))
    if code == "InvalidAccessKeyId":
        detail = (
            f"KYC S3 {action} failed ({code}): invalid S3_ACCESS_KEY — "
            "key not found in AWS. Regenerate IAM access keys and update .env."
        )
    elif code == "SignatureDoesNotMatch":
        detail = (
            f"KYC S3 {action} failed ({code}): S3_SECRET_KEY does not match "
            "S3_ACCESS_KEY. Re-copy both from IAM and restart the API."
        )
    elif code == "AccessDenied":
        detail = (
            f"KYC S3 {action} failed ({code}): IAM user lacks permission. "
            "Attach s3:PutObject and s3:GetObject on the KYC bucket (and kms:GenerateDataKey "
            "if the bucket uses SSE-KMS)."
        )
    else:
        detail = f"KYC S3 {action} failed ({code}): {msg}"
    return KycStorageError(detail, aws_error_code=code)


def store_kyc_bytes(
    *,
    s3_key: str,
    body: bytes,
    content_type: str,
) -> str:
    """Upload bytes to the private KYC bucket. Returns stored key."""
    settings = get_settings()
    if not kyc_storage_configured():
        raise KycStorageNotConfigured("KYC S3 bucket is not configured.")
    if len(body) < 1 or len(body) > settings.S3_KYC_MAX_BYTES:
        raise ValueError(
            f"body size must be between 1 and {settings.S3_KYC_MAX_BYTES}."
        )
    client = get_s3_client()
    put_kwargs: dict[str, object] = {
        "Bucket": settings.S3_BUCKET_KYC,
        "Key": s3_key,
        "Body": body,
        "ContentType": content_type,
    }
    # SSE-KMS on AWS only — MinIO/R2 custom endpoints often reject aws:kms.
    if not _effective_s3_endpoint(settings.S3_ENDPOINT_URL):
        put_kwargs["ServerSideEncryption"] = "aws:kms"
    try:
        client.put_object(**put_kwargs)
    except ClientError as exc:
        raise _storage_error_from_client(exc, "upload") from exc
    except BotoCoreError as exc:
        raise KycStorageError(f"KYC S3 upload failed: {exc}") from exc
    return s3_key
