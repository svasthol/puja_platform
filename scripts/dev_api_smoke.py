"""
Dev-only API smoke walkthrough (no running server required — uses ASGI transport).

Usage (from project root, venv active, .env present):
    python scripts/dev_api_smoke.py

OTP is pinned via unittest.mock so verify works without reading server logs.
"""
from __future__ import annotations

import asyncio
import sys
from unittest.mock import patch

from dotenv import load_dotenv
from httpx import ASGITransport, AsyncClient

load_dotenv()

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

DEV_PHONE = "+919876543210"
DEV_OTP = 424242


async def main() -> int:
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://dev") as client:
        health = await client.get("/health")
        print(f"[health] {health.status_code} {health.json()}")

        with patch(
            "app.api.v1.endpoints.auth.secrets.randbelow",
            return_value=DEV_OTP,
        ):
            otp_req = await client.post(
                "/v1/auth/otp/request",
                json={"phone": DEV_PHONE},
            )
        print(f"[otp/request] {otp_req.status_code} {otp_req.json()}")

        verify = await client.post(
            "/v1/auth/otp/verify",
            json={"phone": DEV_PHONE, "otp": f"{DEV_OTP:06d}"},
        )
        print(f"[otp/verify] {verify.status_code}")
        if verify.status_code != 200:
            print(verify.text)
            return 1
        token = verify.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        pujas = await client.get("/v1/pujas", headers=headers)
        print(f"[pujas] {pujas.status_code} count={len(pujas.json().get('pujas', []))}")

        quote = await client.get(
            "/v1/checkout/quote",
            params={"puja_id": pujas.json()["pujas"][0]["id"] if pujas.json().get("pujas") else ""},
            headers=headers,
        )
        print(f"[checkout/quote] {quote.status_code}")
        if quote.status_code == 200:
            q = quote.json()
            print(
                f"  total={q.get('total_amount')} advance={q.get('advance_amount')} "
                f"modes={[m.get('payment_mode') for m in q.get('payment_options', [])]}"
            )

    print("smoke_ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
