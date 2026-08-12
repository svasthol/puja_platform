"""Catalogue media storage — S3 presign + HEAD confirm (SPEC_AMENDMENTS §20.2)."""
from __future__ import annotations

import uuid
from typing import Any

import boto3
from botocore.client import BaseClient
from botocore.config import Config
from botocore.exceptions import ClientError

from app.core.config import get_settings

EntityType = str
MediaEntityType = str  # puja | category | gallery

ALLOWED_CONTENT_TYPES: dict[str, str] = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}


class CatalogMediaError(Exception):
    """Base error for catalogue storage operations."""


class CatalogStorageNotConfigured(CatalogMediaError):
    """S3 credentials or catalogue bucket not configured."""


def extension_for_content_type(content_type: str) -> str:
    ext = ALLOWED_CONTENT_TYPES.get(content_type)
    if ext is None:
        raise ValueError(f"Unsupported content type: {content_type}")
    return ext


def build_s3_key(entity_type: str, media_id: uuid.UUID, content_type: str) -> str:
    ext = extension_for_content_type(content_type)
    return f"catalog/{entity_type}/{media_id}.{ext}"


def public_url(s3_key: str) -> str | None:
    settings = get_settings()
    base = (settings.S3_CATALOG_PUBLIC_URL or "").strip().rstrip("/")
    if not base:
        return None
    return f"{base}/{s3_key.lstrip('/')}"


def catalog_storage_configured() -> bool:
    settings = get_settings()
    return bool(
        settings.S3_ACCESS_KEY
        and settings.S3_SECRET_KEY
        and settings.S3_BUCKET_CATALOG
    )


def _effective_s3_endpoint(raw: str) -> str | None:
    """Use custom endpoint only when it is a real URL (ignore .env inline comments)."""
    s = (raw or "").strip()
    if not s or s.startswith("#"):
        return None
    if s.startswith("http://") or s.startswith("https://"):
        return s
    return None


def get_s3_client() -> BaseClient:
    settings = get_settings()
    if not catalog_storage_configured():
        raise CatalogStorageNotConfigured(
            "S3_ACCESS_KEY, S3_SECRET_KEY, and S3_BUCKET_CATALOG must be set."
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


def presign_catalog_put(
    *,
    s3_key: str,
    content_type: str,
    content_length: int,
) -> tuple[str, int]:
    """Return (presigned_put_url, expires_in_seconds)."""
    settings = get_settings()
    if content_length < 1 or content_length > settings.S3_CATALOG_MAX_BYTES:
        raise ValueError(
            f"content_length must be between 1 and {settings.S3_CATALOG_MAX_BYTES}."
        )
    extension_for_content_type(content_type)

    client = get_s3_client()
    expires = settings.S3_CATALOG_URL_EXPIRE_SECONDS
    url = client.generate_presigned_url(
        ClientMethod="put_object",
        Params={
            "Bucket": settings.S3_BUCKET_CATALOG,
            "Key": s3_key,
            "ContentType": content_type,
        },
        ExpiresIn=expires,
        HttpMethod="PUT",
    )
    return url, expires


def put_catalog_object(*, s3_key: str, body: bytes, content_type: str) -> None:
    """Server-side PUT — avoids browser→S3 CORS (admin / E2E proxy path)."""
    settings = get_settings()
    if len(body) < 1 or len(body) > settings.S3_CATALOG_MAX_BYTES:
        raise ValueError(
            f"body size must be between 1 and {settings.S3_CATALOG_MAX_BYTES}."
        )
    extension_for_content_type(content_type)
    client = get_s3_client()
    try:
        client.put_object(
            Bucket=settings.S3_BUCKET_CATALOG,
            Key=s3_key,
            Body=body,
            ContentType=content_type,
        )
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        hint = (
            " Check IAM policy allows s3:PutObject on "
            f"arn:aws:s3:::{settings.S3_BUCKET_CATALOG}/catalog/*"
            if code == "AccessDenied"
            else ""
        )
        raise CatalogMediaError(f"S3 put_object failed: {code}.{hint}") from exc


def head_catalog_object(s3_key: str) -> dict[str, Any]:
    """HEAD object metadata — raises CatalogMediaError if missing."""
    settings = get_settings()
    client = get_s3_client()
    try:
        resp = client.head_object(Bucket=settings.S3_BUCKET_CATALOG, Key=s3_key)
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code in ("404", "NoSuchKey", "NotFound"):
            raise CatalogMediaError("Object not found in storage.") from exc
        raise CatalogMediaError(f"S3 head_object failed: {code}") from exc
    return {
        "content_length": int(resp.get("ContentLength", 0)),
        "content_type": resp.get("ContentType", ""),
    }


def validate_head_for_confirm(
    *,
    head: dict[str, Any],
    expected_content_type: str,
) -> None:
    settings = get_settings()
    length = head.get("content_length", 0)
    if length < 1 or length > settings.S3_CATALOG_MAX_BYTES:
        raise CatalogMediaError(
            f"Uploaded object size {length} is outside allowed range."
        )
    actual_type = (head.get("content_type") or "").split(";")[0].strip().lower()
    expected = expected_content_type.lower()
    if actual_type != expected:
        raise CatalogMediaError(
            f"Content-Type mismatch: expected {expected}, got {actual_type or 'unknown'}."
        )
