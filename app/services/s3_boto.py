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
    # OCI compat API: put_object fails with NotImplemented on virtual-hosted-style URLs.
    if custom_endpoint:
        return Config(signature_version="s3v4", s3={"addressing_style": "path"})
    return Config(signature_version="s3v4")
