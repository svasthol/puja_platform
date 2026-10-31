#!/usr/bin/env python3
"""Smoke-test S3/OCI Object Storage for catalogue + KYC (reads app Settings from env).

Run on stg-aio-1 after /etc/mana-guruji/api.env is configured:

  cd /opt/mana-guruji/src/puja_platform
  /opt/mana-guruji/venv/bin/python scripts/verify_staging_storage.py --strict

  (Script loads ENV_FILE or /etc/mana-guruji/api.env automatically; or:
   set -a && source /etc/mana-guruji/api.env && set +a)

Used by: .github/workflows/staging-storage-smoke.yml
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv()
_env_file = os.environ.get("ENV_FILE", "/etc/mana-guruji/api.env")
if Path(_env_file).is_file():
    load_dotenv(_env_file, override=False)

from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import get_settings
from app.services.catalog_media import catalog_storage_configured, get_s3_client as catalog_client
from app.services.kyc_storage import get_s3_client as kyc_client, kyc_storage_configured


def _head_bucket(client, bucket: str, label: str, errors: list[str]) -> None:
    try:
        client.head_bucket(Bucket=bucket)
        print(f"storage: {label} head_bucket OK ({bucket})")
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        errors.append(f"{label}: head_bucket failed ({code}) — check name, keys, endpoint, IAM policy")
    except BotoCoreError as exc:
        errors.append(f"{label}: network/SDK error — {exc}")


def _roundtrip_put_delete(client, bucket: str, label: str, errors: list[str]) -> None:
    key = f"_smoke/{label}-verify.txt"
    body = b"mana-guruji-staging-storage-smoke"
    try:
        client.put_object(Bucket=bucket, Key=key, Body=body, ContentType="text/plain")
        got = client.get_object(Bucket=bucket, Key=key)["Body"].read()
        if got != body:
            errors.append(f"{label}: get_object content mismatch")
        else:
            print(f"storage: {label} put/get OK")
        client.delete_object(Bucket=bucket, Key=key)
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code == "NotImplemented":
            errors.append(
                f"{label}: put/get NotImplemented — deploy latest s3_boto.py "
                "(OCI: path-style + request_checksum_calculation=when_required); not IAM"
            )
        else:
            errors.append(f"{label}: put/get failed ({code}) — check IAM policy and endpoint")
    except BotoCoreError as exc:
        errors.append(f"{label}: roundtrip error — {exc}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify catalogue + KYC object storage")
    parser.add_argument("--strict", action="store_true", help="Exit 1 on any failure")
    parser.add_argument(
        "--skip-roundtrip",
        action="store_true",
        help="Only head_bucket (no put/get/delete)",
    )
    args = parser.parse_args()

    get_settings.cache_clear()
    settings = get_settings()
    errors: list[str] = []

    endpoint = (settings.S3_ENDPOINT_URL or "").strip()
    if not endpoint.startswith("http"):
        errors.append("S3_ENDPOINT_URL must be https://…compat.objectstorage… (OCI) or empty for AWS default")

    if not catalog_storage_configured():
        errors.append(
            "Catalog: set S3_ACCESS_KEY, S3_SECRET_KEY, S3_BUCKET_CATALOG (no duplicate S3_* lines in api.env)"
        )
    if not kyc_storage_configured():
        errors.append("KYC: set S3_BUCKET_KYC (+ same or separate keys per kyc_storage_configured rules)")

    if errors and args.strict:
        for e in errors:
            print(f"storage: FAIL {e}", file=sys.stderr)
        return 1

    if catalog_storage_configured():
        c = catalog_client()
        _head_bucket(c, settings.S3_BUCKET_CATALOG, "catalog", errors)
        if not args.skip_roundtrip:
            _roundtrip_put_delete(c, settings.S3_BUCKET_CATALOG, "catalog", errors)

    if kyc_storage_configured():
        k = kyc_client()
        _head_bucket(k, settings.S3_BUCKET_KYC, "kyc", errors)
        if not args.skip_roundtrip:
            _roundtrip_put_delete(k, settings.S3_BUCKET_KYC, "kyc", errors)

    if errors:
        for e in errors:
            print(f"storage: FAIL {e}", file=sys.stderr)
        return 1 if args.strict else 0

    print("storage: all checks OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
