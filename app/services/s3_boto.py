"""Shared boto3 S3 settings — AWS and S3-compatible (OCI Object Storage, MinIO)."""
from __future__ import annotations

from botocore.config import Config


def effective_s3_endpoint(raw: str) -> str | None:
    s = (raw or "").strip()
    if not s or s.startswith("#"):
        return None
    if s.startswith("http://") or s.startswith("https://"):
        return s
    return None


def s3_boto_config(custom_endpoint: str | None) -> Config:
    """Boto Config for S3 and S3-compatible endpoints (OCI, MinIO).

    OCI: path-style URLs + disable default AWS SDK checksums (boto3 >= 1.36).
    """
    if custom_endpoint:
        return Config(
            signature_version="s3v4",
            s3={"addressing_style": "path"},
            request_checksum_calculation="when_required",
            response_checksum_validation="when_required",
        )
    return Config(signature_version="s3v4")
