#!/usr/bin/env python3
"""
TEST ONLY — FAST2SMS smoke (tests/e2e only, no app imports).

Confirms FAST2SMS_API_KEY from .env before running full E2E UI flow.

Usage:

    # 1) Direct vendor API (no uvicorn):
    python tests/e2e/fast2sms_smoke.py direct --phone +919876543210

    # 2) Via running API (uvicorn on :8000):
    python tests/e2e/fast2sms_smoke.py api --phone +919876543210

Exit codes: 0 = OK, 1 = vendor/API rejected, 2 = unreachable / missing config.
"""
from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")

FAST2SMS_BULK_URL = "https://www.fast2sms.com/dev/bulkV2"
DEFAULT_API = os.environ.get("E2E_API_UPSTREAM", "http://127.0.0.1:8000").rstrip("/")


def _ten_digit(phone: str) -> str:
    digits = "".join(c for c in phone if c.isdigit())
    if digits.startswith("91") and len(digits) == 12:
        return digits[2:]
    return digits[-10:]


def cmd_direct(phone: str) -> int:
    key = os.environ.get("FAST2SMS_API_KEY", "").strip()
    if not key:
        print("ERROR: FAST2SMS_API_KEY missing in .env", file=sys.stderr)
        return 2
    route = os.environ.get("FAST2SMS_OTP_ROUTE", "otp")
    mobile = _ten_digit(phone)
    otp = f"{secrets.randbelow(10**6):06d}"
    payload = {"route": route, "variables_values": otp, "numbers": mobile}
    headers = {"authorization": key}
    print(f"POST {FAST2SMS_BULK_URL} route={route} numbers={mobile}")
    with httpx.Client(timeout=25.0) as client:
        res = client.post(FAST2SMS_BULK_URL, data=payload, headers=headers)
    print(f"→ HTTP {res.status_code}")
    try:
        body = res.json()
    except json.JSONDecodeError:
        print(res.text)
        return 1
    print(json.dumps(body, indent=2))
    if res.status_code != 200 or body.get("return") is not True:
        print("FAIL: FAST2SMS did not accept send.", file=sys.stderr)
        return 1
    print(f"OK: FAST2SMS accepted (request_id={body.get('request_id')}). Check phone for OTP SMS.")
    print(f"NOTE: OTP sent was {otp} (for manual verify if needed).")
    return 0


def cmd_api(phone: str, base: str) -> int:
    url = f"{base.rstrip('/')}/auth/otp/request"
    root = base.replace("/v1", "").replace("/proxy/v1", "").rstrip("/")
    with httpx.Client(timeout=25.0) as client:
        try:
            health = client.get(f"{root}/health")
            if health.status_code != 200:
                print(f"ERROR: API unhealthy at {root}/health", file=sys.stderr)
                return 2
        except httpx.HTTPError as exc:
            print(f"ERROR: API not reachable at {root}: {exc}", file=sys.stderr)
            return 2
        res = client.post(url, json={"phone": phone})
    print(f"POST {url} → {res.status_code}")
    try:
        body = res.json()
    except json.JSONDecodeError:
        print(res.text)
        return 1
    print(json.dumps(body, indent=2))
    if res.status_code != 202:
        return 1
    if body.get("sms_sent") is True and body.get("sms_provider") == "fast2sms":
        print("OK: API routed OTP via fast2sms. Check phone for SMS.")
        return 0
    print(
        "FAIL: sms_sent=false or provider != fast2sms. "
        "Check .env FAST2SMS_API_KEY, SMS_PROVIDER_ORDER, MSG91_ENABLED=false, uvicorn logs.",
        file=sys.stderr,
    )
    return 1


def main() -> int:
    p = argparse.ArgumentParser(description="FAST2SMS smoke (tests/e2e only)")
    p.add_argument(
        "--base",
        default=DEFAULT_API + "/v1",
        help="API base including /v1 (for api subcommand)",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("direct", help="Call FAST2SMS bulkV2 directly")
    d.add_argument("--phone", required=True, help="+91XXXXXXXXXX")

    a = sub.add_parser("api", help="POST /auth/otp/request on running API")
    a.add_argument("--phone", required=True, help="+91XXXXXXXXXX")

    args = p.parse_args()
    if args.cmd == "direct":
        return cmd_direct(args.phone)
    return cmd_api(args.phone, args.base)


if __name__ == "__main__":
    raise SystemExit(main())
