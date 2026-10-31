#!/usr/bin/env python3
"""
One clean Razorpay test payment on staging — real webhook from Razorpay servers.

Uses the public staging API + Razorpay test card API (no local mock signature).
Creates exactly one booking (booking_fee mode, far-future slot). Tag in logs:
  phone default +919811119999  (search Admin / DB by this phone to audit)

Prerequisites:
  - STAGING_API_BASE_URL=https://api-stg.managuruji.in
  - RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET (test mode) in env
  - Dashboard webhook → https://api-stg.managuruji.in/v1/webhooks/razorpay
  - RAZORPAY_WEBHOOK_SECRET matches dashboard (on API server api.env)
  - Catalog: at least one active puja on staging
  - SMS OTP for the smoke phone (staging DEBUG=false) OR pass --otp

Run on stg-aio-1 (recommended — keys already in api.env):
  set -a && source /etc/mana-guruji/api.env && set +a
  export STAGING_API_BASE_URL=https://api-stg.managuruji.in
  /opt/mana-guruji/venv/bin/python scripts/staging_razorpay_webhook_smoke.py --otp 123456

From laptop (same env vars):
  python scripts/staging_razorpay_webhook_smoke.py --otp 123456
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import random
import sys
import time
import uuid
from decimal import Decimal

import httpx

RAZORPAY_API = "https://api.razorpay.com/v1"
DEFAULT_PHONE = "+919811119999"
HYD_LAT, HYD_LON = "17.385044", "78.486671"
TEST_CARD = {
    "number": "4111111111111111",
    "name": "Staging Smoke",
    "expiry_month": "12",
    "expiry_year": "2030",
    "cvv": "100",
}


def _env(name: str) -> str:
    v = (os.environ.get(name) or "").strip()
    if not v:
        print(f"ERROR: missing env {name}", file=sys.stderr)
        sys.exit(1)
    return v


def otp_login(client: httpx.Client, phone: str, otp: str | None) -> str:
    r = client.post("/v1/auth/otp/request", json={"phone": phone})
    if r.status_code != 202:
        print(f"ERROR otp/request {r.status_code}: {r.text[:400]}", file=sys.stderr)
        sys.exit(1)
    body = r.json()
    if not otp:
        otp = body.get("otp_dev_only")
    if not otp:
        print(
            "ERROR: no --otp and API did not return otp_dev_only (staging uses real SMS).\n"
            "  Request OTP to this phone, then re-run with --otp XXXXXX",
            file=sys.stderr,
        )
        sys.exit(1)
    v = client.post(
        "/v1/auth/otp/verify",
        json={"phone": phone, "otp": str(otp).zfill(6), "app_context": "customer"},
    )
    if v.status_code != 200:
        print(f"ERROR otp/verify {v.status_code}: {v.text[:400]}", file=sys.stderr)
        sys.exit(1)
    return v.json()["access_token"]


def ensure_address(client: httpx.Client) -> str:
    r = client.get("/v1/addresses?limit=1")
    r.raise_for_status()
    addrs = r.json().get("addresses") or []
    if addrs:
        return str(addrs[0]["id"])
    sa = client.get("/v1/service-areas")
    sa.raise_for_status()
    areas = sa.json().get("service_areas") or sa.json().get("areas") or []
    if not areas:
        print("ERROR: no active service areas on staging", file=sys.stderr)
        sys.exit(1)
    sa_id = areas[0]["id"]
    cr = client.post(
        "/v1/addresses",
        json={
            "line1": "STG Razorpay smoke (safe to delete user)",
            "city": "Hyderabad",
            "latitude": HYD_LAT,
            "longitude": HYD_LON,
            "service_area_id": sa_id,
            "is_default": True,
        },
    )
    if cr.status_code != 201:
        print(f"ERROR create address {cr.status_code}: {cr.text[:400]}", file=sys.stderr)
        sys.exit(1)
    return str(cr.json()["id"])


def pick_puja(client: httpx.Client) -> str:
    r = client.get("/v1/pujas?limit=20")
    r.raise_for_status()
    pujas = r.json().get("pujas") or []
    if not pujas:
        print("ERROR: no pujas — run bootstrap_catalog.py on staging first", file=sys.stderr)
        sys.exit(1)
    return str(pujas[0]["id"])


def razorpay_pay_order(
    *, key_id: str, key_secret: str, order_id: str, amount_paise: int, phone: str
) -> str:
    payload = {
        "amount": amount_paise,
        "currency": "INR",
        "order_id": order_id,
        "email": "staging-smoke@managuruji.in",
        "contact": phone.replace("+91", "")[-10:],
        "method": "card",
        "card": TEST_CARD,
    }
    with httpx.Client(timeout=60.0) as rz:
        resp = rz.post(
            f"{RAZORPAY_API}/payments/create/json",
            json=payload,
            auth=(key_id, key_secret),
        )
    if resp.status_code >= 400:
        print(f"ERROR Razorpay payment {resp.status_code}: {resp.text[:500]}", file=sys.stderr)
        sys.exit(1)
    data = resp.json()
    pay_id = data.get("razorpay_payment_id") or data.get("id") or ""
    status = data.get("status") or data.get("razorpay_payment_id")
    print(f"   Razorpay payment id={pay_id} status={status}")
    return str(pay_id)


def wait_booking_paid(client: httpx.Client, booking_id: str, timeout_s: int = 45) -> str:
    deadline = time.time() + timeout_s
    last_status = ""
    while time.time() < deadline:
        r = client.get(f"/v1/bookings/{booking_id}")
        if r.status_code == 200:
            last_status = r.json().get("status") or ""
            if last_status in ("requested", "assigned", "confirmed"):
                return last_status
        time.sleep(2)
    return last_status or "timeout"


def main() -> int:
    parser = argparse.ArgumentParser(description="Single staging Razorpay webhook smoke")
    parser.add_argument("--phone", default=DEFAULT_PHONE, help="Customer phone (SMS OTP)")
    parser.add_argument("--otp", default=None, help="6-digit OTP from SMS (required unless DEBUG)")
    parser.add_argument("--webhook-wait", type=int, default=45, help="Seconds to poll booking status")
    args = parser.parse_args()

    base = _env("STAGING_API_BASE_URL").rstrip("/")
    key_id = _env("RAZORPAY_KEY_ID")
    key_secret = _env("RAZORPAY_KEY_SECRET")
    if not (os.environ.get("RAZORPAY_WEBHOOK_SECRET") or "").strip():
        print("WARN: RAZORPAY_WEBHOOK_SECRET not in local env (must be set in /etc/mana-guruji/api.env on VM)")

    print(f"== Staging Razorpay smoke → {base} phone={args.phone} ==")

    with httpx.Client(base_url=base, timeout=60.0) as client:
        token = otp_login(client, args.phone, args.otp)
        client.headers["Authorization"] = f"Bearer {token}"

        address_id = ensure_address(client)
        puja_id = pick_puja(client)
        print(f"   address_id={address_id} puja_id={puja_id}")

        slot_date = (dt.date.today() + dt.timedelta(days=random.randint(120, 240))).isoformat()
        slot_time = "11:30:00"
        hold = client.post("/v1/slot-holds", json={"date": slot_date, "time": slot_time})
        if hold.status_code != 201:
            print(f"ERROR slot-holds {hold.status_code}: {hold.text[:400]}", file=sys.stderr)
            return 1
        hold_id = hold.json()["hold_id"]
        print(f"   hold_id={hold_id} slot={slot_date} {slot_time}")

        booking = client.post(
            "/v1/bookings",
            json={
                "hold_id": hold_id,
                "puja_id": puja_id,
                "address_id": address_id,
                "payment_mode": "booking_fee",
            },
        )
        if booking.status_code != 201:
            print(f"ERROR bookings {booking.status_code}: {booking.text[:400]}", file=sys.stderr)
            return 1
        b = booking.json()
        booking_id = b["booking_id"]
        order_id = b.get("razorpay_order_id") or ""
        fee = Decimal(str(b.get("razorpay_amount") or b.get("booking_fee") or "0"))
        amount_paise = int(fee * 100)
        print(
            f"   booking_id={booking_id} order={order_id} "
            f"razorpay_amount={fee} INR (booking_fee — minimal charge)"
        )

    if not order_id:
        print("ERROR: no razorpay_order_id on booking response", file=sys.stderr)
        return 1

    print("== Pay with Razorpay test card (triggers dashboard webhook) ==")
    razorpay_pay_order(
        key_id=key_id,
        key_secret=key_secret,
        order_id=order_id,
        amount_paise=amount_paise,
        phone=args.phone,
    )

    print(f"== Wait up to {args.webhook_wait}s for Razorpay → staging webhook ==")
    with httpx.Client(
        base_url=base,
        timeout=30.0,
        headers={"Authorization": f"Bearer {token}"},
    ) as client:
        status = wait_booking_paid(client, booking_id, args.webhook_wait)

    if status in ("requested", "assigned", "confirmed"):
        print(f"OK booking {booking_id} status={status} (payment captured via webhook)")
        print("   Verify Razorpay Dashboard → Webhooks → latest delivery HTTP 200")
        print(f"   Admin: filter customer phone {args.phone}")
        return 0

    print(
        f"WARN booking still status={status!r}. Check:\n"
        "  - Razorpay webhook URL + secret on dashboard vs api.env\n"
        "  - nginx 443 → API, Celery worker running\n"
        "  - API logs: journalctl -u mana-guruji-api -n 80",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
