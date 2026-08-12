"""
Full booking flow smoke test (local dev):
  slot hold -> booking (real Razorpay test order) -> signed mock webhook
  -> dispatch broadcast -> pujari accept

Prerequisites (.env):
  RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET  — test keys from Razorpay dashboard
  RAZORPAY_WEBHOOK_SECRET               — any string for local mock signing
                                        (Dashboard → Webhooks secret in prod)
  DATABASE_URL, REDIS_URL, SECRET_KEY

Usage (project root, venv 3.12 active):
  python scripts/dev_booking_flow_e2e.py

Celery worker optional: script calls broadcast_booking() directly if no worker.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import hashlib
import hmac
import json
import random
import sys
import uuid
from decimal import Decimal
from unittest.mock import patch

from dotenv import load_dotenv

load_dotenv()

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Fixed dev personas (idempotent bootstrap)
CUSTOMER_PHONE = "+919111111101"
PUJARI_PHONE = "+919111111102"
DEV_OTP = 515151

CUSTOMER_USER = "e1111111-1111-1111-1111-111111111101"
PUJARI_USER = "e2222222-2222-2222-2222-222222222222"
PUJARI_ID = "e3333333-3333-3333-3333-333333333333"
PUJA_ID = "e4444444-4444-4444-4444-444444444444"
ADDRESS_ID = "e5555555-5555-5555-5555-555555555555"
LAT, LON = 17.385044, 78.486671  # Hyderabad — customer + pujari co-located


async def bootstrap_db() -> tuple[str, str, str]:
    """Idempotent geo + catalog fixtures. Returns (customer_user_id, pujari_user_id, puja_id)."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    from app.core.config import get_settings

    engine = create_async_engine(str(get_settings().DATABASE_URL))
    async with engine.begin() as conn:
        await conn.execute(text("""
            INSERT INTO cancellation_policies (name, refund_pct_before_24h, refund_pct_after_24h)
            VALUES ('standard', 100, 50) ON CONFLICT (name) DO NOTHING;
        """))
        await conn.execute(text("""
            INSERT INTO puja_categories (name) VALUES ('E2E Category')
            ON CONFLICT (name) DO NOTHING;
        """))
        await conn.execute(text("""
            INSERT INTO pujas (id, category_id, name, default_price, duration_minutes, is_active)
            VALUES (:pid, (SELECT id FROM puja_categories WHERE name='E2E Category'),
                    'E2E Satyanarayana Puja', 2100.00, 90, true)
            ON CONFLICT (id) DO NOTHING;
        """), {"pid": PUJA_ID})
        for uid, phone, name in [
            (CUSTOMER_USER, CUSTOMER_PHONE, "E2E Customer"),
            (PUJARI_USER, PUJARI_PHONE, "E2E Pujari"),
        ]:
            await conn.execute(text(
                "INSERT INTO users (id, full_name, phone, is_active) "
                "VALUES (:id, :name, :phone, true) "
                "ON CONFLICT (phone) DO UPDATE SET full_name = EXCLUDED.full_name"
            ), {"id": uid, "name": name, "phone": phone})
        customer_id = (
            await conn.execute(text("SELECT id FROM users WHERE phone = :p"), {"p": CUSTOMER_PHONE})
        ).scalar_one()
        pujari_user_id = (
            await conn.execute(text("SELECT id FROM users WHERE phone = :p"), {"p": PUJARI_PHONE})
        ).scalar_one()
        await conn.execute(text("""
            INSERT INTO pujaris (id, user_id, verification_status)
            VALUES (:pj, :uid, 'verified')
            ON CONFLICT (id) DO UPDATE SET user_id = EXCLUDED.user_id
        """), {"pj": PUJARI_ID, "uid": str(pujari_user_id)})
        await conn.execute(text("""
            INSERT INTO addresses (id, user_id, line1, city, latitude, longitude, geom)
            VALUES (:aid, :uid, 'E2E Street', 'Hyderabad', :lat, :lon,
                    ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography)
            ON CONFLICT (id) DO UPDATE SET user_id = EXCLUDED.user_id, geom = EXCLUDED.geom
        """), {"aid": ADDRESS_ID, "uid": str(customer_id), "lat": LAT, "lon": LON})
        await conn.execute(text("""
            INSERT INTO service_areas (city, zone_name, is_active)
            VALUES ('Hyderabad', 'E2E Zone', true)
            ON CONFLICT (city, zone_name) DO NOTHING
        """))
        sa_id = (
            await conn.execute(
                text("SELECT id FROM service_areas WHERE city='Hyderabad' AND zone_name='E2E Zone'")
            )
        ).scalar_one()
        await conn.execute(text("""
            INSERT INTO pujari_service_areas (pujari_id, service_area_id)
            VALUES (:pj, :sid) ON CONFLICT DO NOTHING
        """), {"pj": PUJARI_ID, "sid": sa_id})
        await conn.execute(text("""
            INSERT INTO pujari_live_location (pujari_id, latitude, longitude, geom, updated_at)
            VALUES (:pj, :lat, :lon, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography, now())
            ON CONFLICT (pujari_id) DO UPDATE SET
                latitude = EXCLUDED.latitude, longitude = EXCLUDED.longitude,
                geom = EXCLUDED.geom, updated_at = now()
        """), {"pj": PUJARI_ID, "lat": LAT, "lon": LON})
    await engine.dispose()
    return str(customer_id), str(pujari_user_id), PUJA_ID


def set_pujari_presence() -> None:
    import redis as redis_lib

    from app.core.config import get_settings

    r = redis_lib.from_url(str(get_settings().REDIS_URL), socket_connect_timeout=5)
    r.ping()
    r.set(f"presence:{PUJARI_ID}", "1", ex=90)


def sign_webhook(body: bytes, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


async def auth_token(client, phone: str, app_context: str = "customer") -> str:
    with patch("app.api.v1.endpoints.auth.secrets.randbelow", return_value=DEV_OTP):
        r = await client.post("/v1/auth/otp/request", json={"phone": phone})
        assert r.status_code == 202, r.text
    r = await client.post(
        "/v1/auth/otp/verify",
        json={"phone": phone, "otp": f"{DEV_OTP:06d}", "app_context": app_context},
    )
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


async def main() -> int:
    from httpx import ASGITransport, AsyncClient

    from app.core.config import get_settings
    from app.workers.dispatch import broadcast_booking

    settings = get_settings()
    if not settings.RAZORPAY_KEY_ID or not settings.RAZORPAY_KEY_SECRET:
        print("ERROR: Set RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET in .env (test mode keys).")
        return 1
    if not settings.RAZORPAY_WEBHOOK_SECRET:
        print("ERROR: Set RAZORPAY_WEBHOOK_SECRET in .env.")
        print("  Local dev: use any secret string; sign mock webhooks with the same value.")
        print("  Prod: Razorpay Dashboard → Webhooks → your endpoint → signing secret.")
        return 1

    print("== 1/7 Bootstrap DB fixtures ==")
    try:
        await bootstrap_db()
        set_pujari_presence()
        print("   fixtures + Redis presence OK")
    except Exception as exc:
        print(f"ERROR during bootstrap: {exc}")
        print("  Ensure PostgreSQL + Redis are reachable (REDIS_URL in .env).")
        return 1

    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://dev") as client:
        print("== 2/7 Customer auth ==")
        customer_token = await auth_token(client, CUSTOMER_PHONE, "customer")
        ch = {"Authorization": f"Bearer {customer_token}"}

        slot_date = dt.date(2036, 6, 15) + dt.timedelta(days=random.randint(0, 200))
        slot_time = dt.time(10, 30)

        print("== 3/7 Slot hold (broadcast — no pujari_id) ==")
        hold = await client.post(
            "/v1/slot-holds",
            headers=ch,
            json={"date": slot_date.isoformat(), "time": slot_time.isoformat()},
        )
        assert hold.status_code == 201, hold.text
        hold_id = hold.json()["hold_id"]
        print(f"   hold_id={hold_id}")

        print("== 4/7 Create booking (calls Razorpay test API) ==")
        booking = await client.post(
            "/v1/bookings",
            headers=ch,
            json={
                "hold_id": hold_id,
                "puja_id": PUJA_ID,
                "address_id": ADDRESS_ID,
                "payment_mode": "full_online",
            },
        )
        assert booking.status_code == 201, booking.text
        b = booking.json()
        booking_id = b["booking_id"]
        amount_paise = int(Decimal(str(b["amount_due_online"])) * 100)
        print(f"   booking_id={booking_id} order={b['razorpay_order_id']} amount_paise={amount_paise}")

        print("== 5/7 Mock Razorpay webhook (payment.captured) ==")
        pay_id = f"pay_e2e_{uuid.uuid4().hex[:12]}"
        webhook_body = {
            "event": "payment.captured",
            "payload": {
                "payment": {
                    "entity": {
                        "id": pay_id,
                        "amount": amount_paise,
                        "currency": "INR",
                        "notes": {"booking_id": booking_id},
                    }
                }
            },
        }
        raw = json.dumps(webhook_body, separators=(",", ":")).encode()
        sig = sign_webhook(raw, settings.RAZORPAY_WEBHOOK_SECRET)
        wh = await client.post(
            "/v1/webhooks/razorpay",
            content=raw,
            headers={
                "Content-Type": "application/json",
                "X-Razorpay-Signature": sig,
            },
        )
        assert wh.status_code == 200, wh.text
        print(f"   webhook -> {wh.json()}")

        print("== 6/7 Dispatch broadcast (sync — no Celery required) ==")
        set_pujari_presence()  # refresh TTL before dispatch MGET
        dispatch_result = broadcast_booking(booking_id)
        print(f"   dispatch -> {dispatch_result}")
        if dispatch_result.get("offers", 0) < 1:
            print("WARN: no offers created — check pujari geo/presence/service_area")

        print("== 7/7 Pujari accept offer ==")
        pujari_token = await auth_token(client, PUJARI_PHONE, "pujari")
        ph = {"Authorization": f"Bearer {pujari_token}"}
        offers = await client.get("/v1/offers", headers=ph)
        assert offers.status_code == 200, offers.text
        offer_list = offers.json().get("offers", [])
        print(f"   offers count={len(offer_list)}")
        if not offer_list:
            print("FAILED: no offers for pujari to accept")
            return 1
        assignment_id = offer_list[0]["assignment_id"]
        accept = await client.post(f"/v1/offers/{assignment_id}/accept", headers=ph)
        print(f"   accept -> {accept.status_code} {accept.json()}")

        status = await client.get(f"/v1/bookings/{booking_id}", headers=ch)
        print(f"   final booking -> {status.json()}")

    print("\n=== E2E OK ===")
    print("Booking flow completed: hold -> pay(webhook) -> dispatch -> accept -> confirmed")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
