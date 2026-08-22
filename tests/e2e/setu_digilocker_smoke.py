#!/usr/bin/env python3
"""
TEST ONLY — Setu DigiLocker KYC smoke (tests/e2e only).

Modes:

  direct  — POST Setu sandbox /api/digilocker (confirms creds, no uvicorn)
  api     — full stack via running API (register → start → poll)
  api-full — api + selfie presign/confirm + admin approve → verified

Usage:

  # 1) Direct Setu credential check:
  python tests/e2e/setu_digilocker_smoke.py direct

  # 2) Full API flow (uvicorn on :8000, DEBUG=true for otp_dev_only):
  python tests/e2e/setu_digilocker_smoke.py api --phone +917675834207

  # 3) Full path including selfie + admin approve (needs S3 + admin TOTP):
  python tests/e2e/setu_digilocker_smoke.py api-full --phone +917675834207

After `api` prints the DigiLocker URL, complete consent in browser (sandbox Aadhaar
999999990019), then the script polls until success or timeout.

Env (see tests/e2e/README.md § Setu DigiLocker):
  KYC_REDIRECT_URL, KYC_SETU_CLIENT_ID, KYC_SETU_CLIENT_SECRET,
  KYC_SETU_DIGILOCKER_PRODUCT_ID, KYC_IDENTITY_PEPPER, SECRET_KEY, DATABASE_URL, REDIS_URL

Exit codes: 0 = OK, 1 = vendor/API failure, 2 = missing config / unreachable.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from pathlib import Path

import httpx
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")

DEFAULT_API = os.environ.get("E2E_API_UPSTREAM", "http://127.0.0.1:8000").rstrip("/")
SETU_BASE = os.environ.get("KYC_SETU_BASE_URL", "https://dg-sandbox.setu.co").rstrip("/")
SETU_TIMEOUT_S = float(os.environ.get("KYC_SETU_E2E_TIMEOUT_S", "90"))
POLL_INTERVAL_S = 3
POLL_TIMEOUT_S = int(os.environ.get("KYC_E2E_POLL_TIMEOUT_S", "300"))

_MIN_JPEG = (
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

# Setu returns 201 Created for POST /api/digilocker/ (docs sometimes say 200).
_SETU_CREATE_OK = frozenset({200, 201})


def _setu_create_ok(status: int, body: dict) -> bool:
    return status in _SETU_CREATE_OK and body.get("id")


def _require(name: str) -> str:
    val = os.environ.get(name, "").strip()
    if not val:
        print(f"ERROR: {name} missing in .env", file=sys.stderr)
        sys.exit(2)
    return val


def _setu_headers() -> dict[str, str]:
    return {
        "x-client-id": _require("KYC_SETU_CLIENT_ID"),
        "x-client-secret": _require("KYC_SETU_CLIENT_SECRET"),
        "x-product-instance-id": _require("KYC_SETU_DIGILOCKER_PRODUCT_ID"),
        "Content-Type": "application/json",
    }


def _setu_post(
    redirect: str,
    *,
    timeout: float = SETU_TIMEOUT_S,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    url = f"{SETU_BASE}/api/digilocker/"
    with httpx.Client(timeout=timeout) as client:
        return client.post(
            url,
            headers=headers or _setu_headers(),
            json={"redirectUrl": redirect},
        )


def _print_setu_upstream_help(status: int, body: dict | None, redirect: str) -> None:
    req_id = (body or {}).get("request_id", "")
    print(
        f"\nSetu returned HTTP {status} — your request reached Setu but their upstream failed.\n"
        f"  message: {(body or {}).get('message', '')}\n"
        f"  request_id: {req_id}  ← share with Setu support if needed\n\n"
        "Your Bridge dashboard shows **KYC INCOMPLETE** and "
        "**Resume configuration with DigiLocker** — complete that first:\n"
        "  1. Setu Bridge → Mana Guruji - DigiLocker → click **Resume configuration**\n"
        "  2. Finish DigiLocker bridge setup (redirect URL, branding, agreements)\n"
        "  3. Register redirect URL exactly:\n"
        f"     {redirect}\n"
        "  4. Wait until product status is no longer KYC INCOMPLETE, then re-run smoke.\n\n"
        "Our API integration (headers, path, body) matches Setu docs — this is a Setu-side setup issue.\n",
        file=sys.stderr,
    )


def _print_setu_timeout_help(redirect: str, elapsed: float) -> None:
    print(
        f"\nTIMEOUT: Setu did not respond within {elapsed:.0f}s (not a local Python bug).\n"
        "Diagnostics we have seen on sandbox:\n"
        "  • Wrong client id/secret → fast 401 (your creds likely pass auth)\n"
        "  • Empty product id → fast 403\n"
        "  • Wrong / non-DigiLocker product instance id → often HANGS (no JSON error)\n"
        "  • Setu sandbox upstream slow/down → same hang\n\n"
        "Checklist:\n"
        "  1. Setu Bridge → Products → open **DigiLocker** (not PAN) → copy Product Instance ID\n"
        "     into KYC_SETU_DIGILOCKER_PRODUCT_ID\n"
        "  2. Register redirect URL in that same DigiLocker product (exact match):\n"
        f"     {redirect}\n"
        "  3. Retry with a known-good redirect to isolate ngrok:\n"
        "     python tests/e2e/setu_digilocker_smoke.py direct --redirect https://setu.co\n"
        "  4. If still timing out, contact Setu support (sandbox may be stuck on your product).\n",
        file=sys.stderr,
    )


def cmd_auth() -> int:
    """Fast credential check — does not wait for a full DigiLocker create."""
    bad_headers = {
        "x-client-id": "invalid",
        "x-client-secret": "invalid",
        "x-product-instance-id": _require("KYC_SETU_DIGILOCKER_PRODUCT_ID"),
        "Content-Type": "application/json",
    }
    print("Probe 1: invalid client credentials (expect fast 401)...")
    try:
        res = _setu_post("https://setu.co", timeout=15.0, headers=bad_headers)
        print(f"HTTP {res.status_code} {res.text[:120]}")
    except httpx.ReadTimeout:
        print("unexpected timeout on invalid creds — network or Setu issue")
        return 2

    product = _require("KYC_SETU_DIGILOCKER_PRODUCT_ID")
    if not product:
        print("ERROR: KYC_SETU_DIGILOCKER_PRODUCT_ID empty", file=sys.stderr)
        return 2

    print("Probe 2: your credentials + https://setu.co redirect (may take up to 90s)...")
    try:
        res = _setu_post("https://setu.co", timeout=SETU_TIMEOUT_S)
        print(f"HTTP {res.status_code}")
        print(res.text[:500])
        if _setu_create_ok(res.status_code, res.json()):
            print("OK: Setu accepted create request.")
            return 0
        if res.status_code in (502, 503, 504):
            try:
                body = res.json()
            except json.JSONDecodeError:
                body = None
            _print_setu_upstream_help(res.status_code, body, "https://setu.co")
            return 1
        return 1
    except httpx.ReadTimeout:
        _print_setu_timeout_help(os.environ.get("KYC_REDIRECT_URL", "https://setu.co"))
        return 2


def cmd_direct(redirect_override: str | None = None) -> int:
    redirect = redirect_override or _require("KYC_REDIRECT_URL")
    url = f"{SETU_BASE}/api/digilocker/"
    print(f"POST {url}")
    print(f"redirectUrl={redirect}")
    print(f"timeout={SETU_TIMEOUT_S}s")
    try:
        res = _setu_post(redirect, timeout=SETU_TIMEOUT_S)
    except httpx.ReadTimeout:
        _print_setu_timeout_help(redirect)
        return 2
    print(f"HTTP {res.status_code}")
    try:
        body = res.json()
    except json.JSONDecodeError:
        print(res.text)
        return 1
    print(json.dumps(body, indent=2))
    if res.status_code in (502, 503, 504):
        _print_setu_upstream_help(res.status_code, body, redirect)
        return 1
    if not _setu_create_ok(res.status_code, body):
        print("FAIL: Setu did not return a DigiLocker request id.", file=sys.stderr)
        return 1
    print(f"OK: Setu sandbox accepted — request_id={body['id']}")
    if body.get("url"):
        print(f"Open in browser: {body['url']}")
    return 0


def _api_health(base: str) -> bool:
    root = base.replace("/v1", "").rstrip("/")
    try:
        with httpx.Client(timeout=5.0) as client:
            res = client.get(f"{root}/health")
        return res.status_code == 200
    except httpx.HTTPError:
        return False


def _otp_login(base: str, phone: str, otp: str | None) -> str:
    """Return pujari access token."""
    with httpx.Client(timeout=30.0) as client:
        req = client.post(f"{base}/v1/auth/otp/request", json={"phone": phone})
        if req.status_code != 202:
            print(f"ERROR: otp/request → {req.status_code} {req.text}", file=sys.stderr)
            sys.exit(2)
        body = req.json()
        if not otp:
            dev_otp = body.get("otp_dev_only")
            if dev_otp:
                otp = str(dev_otp)
                print(f"Using otp_dev_only from API response: {otp}")
            else:
                otp = input("Enter OTP from SMS or uvicorn otp_dev_only log: ").strip()
        verify = client.post(
            f"{base}/v1/auth/otp/verify",
            json={"phone": phone, "otp": otp, "app_context": "pujari"},
        )
        if verify.status_code != 200:
            print(f"ERROR: otp/verify → {verify.status_code} {verify.text}", file=sys.stderr)
            sys.exit(1)
        return verify.json()["access_token"]


def _admin_token(base: str) -> str | None:
    phone = os.environ.get("ADMIN_TEST_PHONE", "").strip()
    secret = os.environ.get("ADMIN_TOTP_SECRET", "").strip()
    if not phone or not secret:
        print("WARN: ADMIN_TEST_PHONE + ADMIN_TOTP_SECRET not set — skipping admin approve.")
        return None
    from app.core import totp

    code = totp.totp_at(secret, at=int(time.time()))
    with httpx.Client(timeout=30.0) as client:
        res = client.post(
            f"{base}/v1/admin/auth/login",
            json={"phone": phone, "code": code},
        )
    if res.status_code != 200:
        print(f"ERROR: admin login → {res.status_code} {res.text}", file=sys.stderr)
        return None
    return res.json()["access_token"]


def _selfie_upload(client: httpx.Client, base: str, headers: dict[str, str]) -> bool:
    if not os.environ.get("S3_BUCKET_KYC", "").strip():
        print("WARN: S3_BUCKET_KYC not set — skipping selfie step.", file=sys.stderr)
        return False
    presign = client.post(
        f"{base}/v1/pujari/documents",
        headers=headers,
        json={"content_type": "image/jpeg", "content_length": len(_MIN_JPEG)},
    )
    if presign.status_code != 200:
        print(f"ERROR: selfie presign → {presign.status_code} {presign.text}", file=sys.stderr)
        return False
    body = presign.json()
    put = client.put(
        body["upload_url"],
        content=_MIN_JPEG,
        headers={"Content-Type": "image/jpeg"},
    )
    if put.status_code not in (200, 201):
        print(f"ERROR: selfie PUT → {put.status_code} {put.text}", file=sys.stderr)
        return False
    confirm = client.post(
        f"{base}/v1/pujari/documents/{body['document_id']}/confirm",
        headers=headers,
    )
    if confirm.status_code != 200:
        print(f"ERROR: selfie confirm → {confirm.status_code} {confirm.text}", file=sys.stderr)
        return False
    print(f"Selfie confirmed: document_id={body['document_id']}")
    return True


def _admin_approve_all(base: str, pujari_id: str) -> bool:
    token = _admin_token(base)
    if not token:
        return False
    headers = {"Authorization": f"Bearer {token}"}
    with httpx.Client(timeout=30.0) as client:
        summary = client.get(
            f"{base}/v1/admin/kyc/pujaris/{pujari_id}",
            headers=headers,
        )
        if summary.status_code != 200:
            print(f"ERROR: admin kyc summary → {summary.status_code} {summary.text}", file=sys.stderr)
            return False
        docs = summary.json()["documents"]
        pending = [
            d for d in docs if d.get("document_id") and d.get("status") == "pending"
        ]
        if len(pending) < 3:
            print(f"WARN: expected 3 pending docs, found {len(pending)}", file=sys.stderr)
        for doc in pending:
            res = client.post(
                f"{base}/v1/admin/kyc/{doc['document_id']}/approve",
                headers=headers,
                json={"change_reason": "E2E smoke approve"},
            )
            if res.status_code != 200:
                print(
                    f"ERROR: approve {doc['doc_type']} → {res.status_code} {res.text}",
                    file=sys.stderr,
                )
                return False
            print(f"Approved {doc['doc_type']}: {doc['document_id']}")
        final = client.get(
            f"{base}/v1/admin/kyc/pujaris/{pujari_id}",
            headers=headers,
        )
        status = final.json().get("pujari_verification_status")
        print(f"Pujari verification_status={status}")
        return status == "verified"


def cmd_api(phone: str, base: str, full: bool = False) -> int:
    if not _api_health(base):
        print(f"ERROR: API unhealthy at {base}/health — start uvicorn first.", file=sys.stderr)
        return 2

    _require("KYC_REDIRECT_URL")
    _require("KYC_IDENTITY_PEPPER")
    otp_override = os.environ.get("KYC_TEST_OTP", "").strip() or None

    print(f"API base: {base}")
    print(f"Pujari phone: {phone}")
    token = _otp_login(base, phone, otp_override)
    headers = {"Authorization": f"Bearer {token}"}

    with httpx.Client(timeout=60.0) as client:
        reg = client.post(
            f"{base}/v1/pujari/register",
            headers=headers,
            json={"bio": "E2E KYC test", "years_experience": 5},
        )
        if reg.status_code not in (200, 201):
            print(f"ERROR: register → {reg.status_code} {reg.text}", file=sys.stderr)
            return 1
        reg_body = reg.json()
        pujari_id = str(reg_body["pujari_id"])
        print(f"Register: {reg_body}")

        start = client.post(f"{base}/v1/pujari/kyc/digilocker", headers=headers)
        if start.status_code not in (200, 201):
            print(f"ERROR: kyc/digilocker -> {start.status_code} {start.text}", file=sys.stderr)
            print(
                "If this is 409, expire the leftover row then retry:\n"
                "  UPDATE kyc_verification_requests SET status = 'expired', updated_at = now()\n"
                "  WHERE pujari_id = '<pujari_id>' AND status IN ('created','authenticated');",
                file=sys.stderr,
            )
            return 1
        payload = start.json()
        request_id = payload["request_id"]
        digi_url = payload["url"]
        print("\n--- ACTION REQUIRED ---")
        print("1. Open this URL in a browser (complete DigiLocker consent):")
        print(f"   {digi_url}")
        print("2. This is usually the REAL DigiLocker site — use an existing DigiLocker account")
        print("   (Sign in). Do not use test Aadhaar 999999990019 on digitallocker.gov.in.")
        print("3. Script will poll until status=success or timeout.\n")

        deadline = time.time() + POLL_TIMEOUT_S
        last_status = None
        while time.time() < deadline:
            poll = client.get(
                f"{base}/v1/pujari/kyc/requests/{request_id}",
                headers=headers,
            )
            if poll.status_code != 200:
                print(f"Poll error {poll.status_code}: {poll.text}")
                time.sleep(POLL_INTERVAL_S)
                continue
            data = poll.json()
            status = data.get("status")
            if status != last_status:
                print(
                    f"poll status={status} scope={data.get('scope')} "
                    f"docs={data.get('doc_types_created')} flags={data.get('review_flags')}"
                )
                last_status = status
            if status == "success":
                kyc_status = client.get(f"{base}/v1/pujari/kyc/status", headers=headers)
                print(f"KYC status: {kyc_status.json()}")
                if not full:
                    print("OK: DigiLocker finalize succeeded.")
                    return 0
                if not _selfie_upload(client, base, headers):
                    return 1
                kyc_status = client.get(f"{base}/v1/pujari/kyc/status", headers=headers)
                print(f"KYC status after selfie: {kyc_status.json()}")
                if not _admin_approve_all(base, pujari_id):
                    return 1
                print("OK: Full KYC path — verified.")
                return 0
            if status in ("failed", "expired"):
                print(f"FAIL: request ended as {status} — {data.get('error_message')}")
                return 1
            time.sleep(POLL_INTERVAL_S)

    print(f"TIMEOUT: no success within {POLL_TIMEOUT_S}s — complete DigiLocker in browser and re-poll manually.")
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Setu DigiLocker KYC E2E smoke")
    parser.add_argument(
        "mode",
        choices=("direct", "api", "api-full", "auth"),
        help="direct=Setu create, auth=fast cred check, api=full stack, api-full=+selfie+admin",
    )
    parser.add_argument("--phone", default=os.environ.get("KYC_TEST_PHONE", "+917675834207"))
    parser.add_argument("--api", default=DEFAULT_API, help="API base (default E2E_API_UPSTREAM)")
    parser.add_argument(
        "--redirect",
        default=None,
        help="Override redirectUrl for direct mode (e.g. https://setu.co)",
    )
    args = parser.parse_args()
    if args.mode == "direct":
        return cmd_direct(args.redirect)
    if args.mode == "auth":
        return cmd_auth()
    if args.mode == "api-full":
        return cmd_api(args.phone, args.api.rstrip("/"), full=True)
    return cmd_api(args.phone, args.api.rstrip("/"))


if __name__ == "__main__":
    sys.exit(main())
