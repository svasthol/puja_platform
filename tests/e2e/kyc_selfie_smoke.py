#!/usr/bin/env python3
"""
TEST ONLY — Selfie KYC smoke (no DigiLocker).

  python tests/e2e/kyc_selfie_smoke.py
  python tests/e2e/kyc_selfie_smoke.py --phone +917675834207
  python tests/e2e/kyc_selfie_smoke.py --exif   # verify EXIF strip via S3 fetch

Requires: uvicorn :8000, DEBUG=true, S3_BUCKET_KYC + credentials in .env.

Exit: 0 = OK, 1 = API/S3 failure, 2 = missing config / unreachable.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_E2E_DIR = Path(__file__).resolve().parent
if str(_E2E_DIR) not in sys.path:
    sys.path.insert(0, str(_E2E_DIR))

from kyc_e2e_common import (
    API_BASE,
    EXIF_JPEG,
    api_health_ok,
    fetch_s3_body,
    jpeg_has_exif,
    pujari_session,
    require_s3,
    selfie_upload_confirm,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Selfie KYC E2E smoke (presign → PUT → confirm)")
    parser.add_argument("--phone", default=None, help="Pujari phone (default: random +91)")
    parser.add_argument(
        "--exif",
        action="store_true",
        help="Upload JPEG with EXIF segment and verify strip after confirm",
    )
    args = parser.parse_args()

    if not api_health_ok():
        print(f"ERROR: API unhealthy at {API_BASE}/health — start uvicorn.", file=sys.stderr)
        return 2
    try:
        require_s3()
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    body = EXIF_JPEG if args.exif else None
    print(f"API: {API_BASE}")
    try:
        client, headers, phone = pujari_session(phone=args.phone)
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    try:
        if body is not None:
            print("Uploading JPEG with EXIF segment...")
            result = selfie_upload_confirm(client, headers, body=body)
            stored = fetch_s3_body(result["file_url"])
            if jpeg_has_exif(stored):
                print("FAIL: EXIF segment still present after confirm", file=sys.stderr)
                return 1
            print("EXIF strip OK")
        else:
            result = selfie_upload_confirm(client, headers)

        status = client.get(f"{API_BASE}/v1/pujari/kyc/status", headers=headers)
        photo = next(r for r in status.json()["required"] if r["doc_type"] == "photo")
        print(f"Phone: {phone}")
        print(f"document_id={result['document_id']}")
        print(f"file_url={result['file_url']}")
        print(f"kyc/status photo: status={photo['status']} document_id={photo['document_id']}")
        print("OK: selfie presign -> PUT -> confirm")
        return 0
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    finally:
        client.close()


if __name__ == "__main__":
    sys.exit(main())
