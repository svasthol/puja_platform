#!/usr/bin/env python3
"""
TEST ONLY — OTP / MSG91 smoke against a running API (no app imports).

Same contract as E2E UI Customer tab OTP buttons. Use to confirm MSG91 integration
without changing app/ code.

Usage:

    # Terminal 1: uvicorn app.main:app --reload --port 8000
    # .env: MSG91_AUTH_KEY, MSG91_TEMPLATE_ID (optional DEBUG=true)

    python tests/e2e_ui/otp_smoke.py request --phone +919876543210
    python tests/e2e_ui/otp_smoke.py verify --phone +919876543210 --otp 123456

    # Via E2E proxy (serve.py on :8765):
    python tests/e2e_ui/otp_smoke.py request --base http://127.0.0.1:8765/proxy/v1 --phone +91...

Exit codes: 0 = OK, 1 = HTTP/validation failure, 2 = API unreachable.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")

DEFAULT_BASE = os.environ.get("E2E_API_UPSTREAM", "http://127.0.0.1:8000").rstrip("/")


def _api_root(base: str) -> str:
    """Strip /v1 or /proxy/v1 suffix for /health."""
    for suffix in ("/proxy/v1", "/v1"):
        if base.rstrip("/").endswith(suffix):
            return base.rstrip("/")[: -len(suffix)]
    return base.rstrip("/")


def _health(client: httpx.Client, base: str) -> bool:
    root = _api_root(base)
    try:
        r = client.get(f"{root}/health")
        return r.status_code == 200
    except httpx.HTTPError:
        return False


def cmd_request(base: str, phone: str) -> int:
    url = f"{base.rstrip('/')}/auth/otp/request"
    with httpx.Client(timeout=20.0) as client:
        if not _health(client, base):
            print(f"ERROR: API not reachable (check uvicorn on {DEFAULT_BASE})", file=sys.stderr)
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
    sms = body.get("sms_sent")
    if sms is True:
        print("OK: MSG91 accepted send (check phone for SMS).")
    else:
        print("NOTE: sms_sent=false — use DEBUG=true and copy otp_dev_only from uvicorn log.")
    return 0


def cmd_verify(base: str, phone: str, otp: str, app_context: str) -> int:
    url = f"{base.rstrip('/')}/auth/otp/verify"
    with httpx.Client(timeout=15.0) as client:
        res = client.post(url, json={"phone": phone, "otp": otp, "app_context": app_context})
    print(f"POST {url} → {res.status_code}")
    try:
        body = res.json()
    except json.JSONDecodeError:
        print(res.text)
        return 1
    if res.status_code == 200:
        print("OK: access_token received (first 20 chars):", (body.get("access_token") or "")[:20] + "...")
        return 0
    print(json.dumps(body, indent=2))
    return 1


def main() -> int:
    p = argparse.ArgumentParser(description="OTP smoke test (tests/e2e_ui only)")
    p.add_argument(
        "--base",
        default=DEFAULT_BASE + "/v1",
        help="API base including /v1 (default: E2E_API_UPSTREAM/v1)",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("request", help="POST /auth/otp/request")
    r.add_argument("--phone", required=True)

    v = sub.add_parser("verify", help="POST /auth/otp/verify")
    v.add_argument("--phone", required=True)
    v.add_argument("--otp", required=True)
    v.add_argument("--app-context", default="customer", choices=("customer", "pujari"))

    args = p.parse_args()
    if args.cmd == "request":
        return cmd_request(args.base, args.phone)
    return cmd_verify(args.base, args.phone, args.otp, args.app_context)


if __name__ == "__main__":
    raise SystemExit(main())
