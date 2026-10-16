"""
TEST ONLY — confirm payment_pending booking via signed Razorpay webhook.

Uses RAZORPAY_WEBHOOK_SECRET from project .env (same as mock webhook button).
Never import from app/.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import uuid
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row

PROJECT_ROOT = Path(__file__).resolve().parents[2]

def _booking_for_payment_sql(conn) -> str:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'bookings'
              AND column_name = 'booking_fee'
            LIMIT 1
            """
        )
        has_fee = cur.fetchone() is not None
    fee_col = "b.booking_fee," if has_fee else "NULL::numeric AS booking_fee,"
    return f"""
SELECT
  b.id::text AS booking_id,
  st.code AS status,
  b.amount_due_online,
  {fee_col}
  b.payment_mode,
  b.paid_at
FROM bookings b
JOIN status_types st ON st.id = b.status_id
WHERE b.id = %s::uuid
LIMIT 1
"""


def _payment_amount_paise(row: dict) -> int:
    """Sprint 1: Razorpay = booking_fee. Legacy: amount_due_online."""
    mode = row.get("payment_mode") or ""
    fee = row.get("booking_fee")
    if mode == "booking_fee" and fee is not None:
        return int(Decimal(str(fee)) * 100)
    if fee is not None and Decimal(str(row.get("amount_due_online") or 0)) == 0:
        return int(Decimal(str(fee)) * 100)
    return int(Decimal(str(row.get("amount_due_online") or 0)) * 100)


def _normalize_db_url(url: str) -> str:
    return url.replace("postgresql+psycopg://", "postgresql://").replace(
        "postgresql+psycopg2://", "postgresql://"
    )


def confirm_booking_payment(
    booking_id: str,
    *,
    api_base: str | None = None,
) -> dict[str, Any]:
    """
    POST payment.captured webhook to the running API for one booking.

    Idempotent when payment already captured (API returns already_processed).
    """
    load_dotenv(PROJECT_ROOT / ".env")
    db_url = os.environ.get("DATABASE_URL", "")
    secret = os.environ.get("RAZORPAY_WEBHOOK_SECRET", "").strip()
    upstream = (api_base or os.environ.get("E2E_API_UPSTREAM", "http://127.0.0.1:8000")).rstrip(
        "/"
    )

    if not db_url:
        raise RuntimeError("DATABASE_URL not set in .env")
    if not secret:
        raise RuntimeError(
            "RAZORPAY_WEBHOOK_SECRET not set in .env — required for mock payment confirm"
        )

    with psycopg.connect(_normalize_db_url(db_url), row_factory=dict_row) as conn:
        sql = _booking_for_payment_sql(conn)
        with conn.cursor() as cur:
            cur.execute(sql, (booking_id,))
            row = cur.fetchone()
    if row is None:
        raise ValueError(f"Booking not found: {booking_id}")

    if row["paid_at"] is not None:
        return {
            "ok": True,
            "status": "already_paid",
            "booking_id": booking_id,
            "message": "Booking already has paid_at set",
        }

    amount_paise = _payment_amount_paise(row)
    payment_id = f"pay_e2e_{uuid.uuid4().hex[:12]}"
    body = {
        "event": "payment.captured",
        "payload": {
            "payment": {
                "entity": {
                    "id": payment_id,
                    "amount": amount_paise,
                    "currency": "INR",
                    "notes": {"booking_id": booking_id},
                }
            }
        },
    }
    raw = json.dumps(body, separators=(",", ":")).encode()
    sig = hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()
    url = f"{upstream}/v1/webhooks/razorpay"
    req = Request(
        url,
        data=raw,
        headers={
            "Content-Type": "application/json",
            "X-Razorpay-Signature": sig,
        },
        method="POST",
    )
    try:
        with urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode() or "{}")
            return {
                "ok": True,
                "http_status": resp.status,
                "booking_id": booking_id,
                "amount_paise": amount_paise,
                "payment_id": payment_id,
                "webhook": data,
            }
    except HTTPError as exc:
        detail = exc.read().decode()
        try:
            parsed = json.loads(detail)
        except json.JSONDecodeError:
            parsed = {"raw": detail}
        return {
            "ok": False,
            "http_status": exc.code,
            "booking_id": booking_id,
            "detail": parsed,
        }
