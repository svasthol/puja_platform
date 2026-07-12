"""Print X-Razorpay-Signature for a mock webhook body (local dev).

Usage:
  python scripts/sign_razorpay_webhook.py --booking-id <uuid> --amount-paise 210000

Uses RAZORPAY_WEBHOOK_SECRET from .env.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import uuid

from dotenv import load_dotenv

load_dotenv()


def main() -> None:
    from app.core.config import get_settings

    p = argparse.ArgumentParser()
    p.add_argument("--booking-id", required=True)
    p.add_argument("--amount-paise", type=int, required=True)
    p.add_argument("--payment-id", default=f"pay_test_{uuid.uuid4().hex[:12]}")
    args = p.parse_args()

    secret = get_settings().RAZORPAY_WEBHOOK_SECRET
    if not secret:
        raise SystemExit("Set RAZORPAY_WEBHOOK_SECRET in .env")

    body = {
        "event": "payment.captured",
        "payload": {
            "payment": {
                "entity": {
                    "id": args.payment_id,
                    "amount": args.amount_paise,
                    "currency": "INR",
                    "notes": {"booking_id": args.booking_id},
                }
            }
        },
    }
    raw = json.dumps(body, separators=(",", ":")).encode()
    sig = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    print("BODY:")
    print(raw.decode())
    print("\nX-Razorpay-Signature:")
    print(sig)


if __name__ == "__main__":
    main()
