"""Private KYC document storage — presigned GET (A-KYC)."""
from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import boto3
from botocore.client import BaseClient
from botocore.config import Config

from app.core.config import get_settings


class KycStorageNotConfigured(Exception):
    """S3 credentials or KYC bucket not configured."""


def kyc_storage_configured() -> bool:
    settings = get_settings()
    return bool(
        settings.S3_ACCESS_KEY and settings.S3_SECRET_KEY and settings.S3_BUCKET_KYC
    )


def _effective_s3_endpoint(raw: str) -> str | None:
    s = (raw or "").strip()
    if not s or s.startswith("#"):
        return None
    if s.startswith("http://") or s.startswith("https://"):
        return s
    return None


def get_s3_client() -> BaseClient:
    settings = get_settings()
    if not kyc_storage_configured():
        raise KycStorageNotConfigured(
            "S3_ACCESS_KEY, S3_SECRET_KEY, and S3_BUCKET_KYC must be set."
        )
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
        "aws_access_key_id": settings.S3_ACCESS_KEY,
        "aws_secret_access_key": settings.S3_SECRET_KEY,
        "config": Config(signature_version="s3v4"),
    }
    if use_endpoint:
        kwargs["endpoint_url"] = use_endpoint
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
