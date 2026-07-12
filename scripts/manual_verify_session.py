"""
Interactive manual booking-flow verifier — final pre-launch walkthrough.

Enter your own customer + pujari phones, register a pujari (KYC skipped for dev),
run the full hold → pay → webhook → dispatch → notification → accept loop,
and inspect DB + Redis after each step.

Prerequisites:
  - uvicorn: uvicorn app.main:app --reload --port 8000
  - DEBUG=true  → OTP in uvicorn log as otp_dev_only=XXXXXX
  - Redis + Postgres + RAZORPAY_* in .env
  - Optional (production-like dispatch): Celery worker + Beat running

Usage:
  python scripts/manual_verify_session.py
  python scripts/manual_verify_session.py --use-celery
  python scripts/manual_verify_session.py --clean
  python scripts/manual_verify_session.py --base-url http://127.0.0.1:8000
"""
from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import hashlib
import hmac
import json
import random
import sys
import textwrap
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv()

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

DEFAULT_CUSTOMER_PHONE = "+917675834207"
DEFAULT_PUJARI_PHONE = "+919111111102"
DEFAULT_PUJA_ID = "e4444444-4444-4444-4444-444444444444"
DEFAULT_LAT, DEFAULT_LON = 17.385044, 78.486671


@dataclass
class SessionConfig:
    customer_phone: str
    customer_name: str
    pujari_phone: str
    pujari_name: str
    pujari_bio: str
    city: str
    zone_name: str
    lat: float
    lon: float
    puja_id: str
    puja_name: str
    puja_price: str
    payment_mode: str
    slot_date: str | None = None
    slot_time: str | None = None
    pujari_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    pujari_user_id: str | None = None


def pause(msg: str = "Press Enter to continue...") -> None:
    input(f"\n── {msg} ")


def section(title: str) -> None:
    print("\n" + "=" * 72)
    print(title)
    print("=" * 72)


def show(label: str, data: object) -> None:
    print(f"\n[{label}]")
    if isinstance(data, (dict, list)):
        print(json.dumps(data, indent=2, default=str))
    else:
        print(data)


def prompt(label: str, default: str) -> str:
    raw = input(f"{label} [{default}]: ").strip()
    return raw if raw else default


def prompt_float(label: str, default: float) -> float:
    raw = input(f"{label} [{default}]: ").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        print("  Invalid number — using default.")
        return default


def collect_session_config() -> SessionConfig:
    section("SESSION SETUP — enter test personas (Enter = default)")
    print(textwrap.dedent("""
        Customer and pujari will log in via OTP like the real apps.
        Pujari profile is registered in DB with verification_status='verified'
        (KYC / document upload skipped for this dev run).
    """))

    customer_phone = prompt("Customer phone (E.164, e.g. +91…)", DEFAULT_CUSTOMER_PHONE)
    customer_name = prompt("Customer display name", "Test Customer")
    pujari_phone = prompt("Pujari phone (E.164)", DEFAULT_PUJARI_PHONE)
    pujari_name = prompt("Pujari full name", "Test Pujari")
    pujari_bio = prompt("Pujari bio (short)", "Experienced pujari — dev profile")
    city = prompt("Service city", "Hyderabad")
    zone_name = prompt("Service zone", "E2E Zone")
    lat = prompt_float("Customer / pujari latitude", DEFAULT_LAT)
    lon = prompt_float("Customer / pujari longitude", DEFAULT_LON)
    puja_name = prompt("Puja name for catalog", "E2E Satyanarayana Puja")
    puja_price = prompt("Puja price (INR)", "2100.00")
    payment_mode = prompt("Payment mode (full_online | advance_balance)", "full_online")
    if payment_mode not in ("full_online", "advance_balance"):
        print("  Unknown mode — using full_online.")
        payment_mode = "full_online"

    use_custom_slot = prompt("Custom slot date/time? (y/N)", "N").lower() in ("y", "yes")
    slot_date = slot_time = None
    if use_custom_slot:
        slot_date = prompt("Slot date (YYYY-MM-DD)", (dt.date.today() + dt.timedelta(days=30)).isoformat())
        slot_time = prompt("Slot time (HH:MM:SS)", "10:30:00")

    cfg = SessionConfig(
        customer_phone=customer_phone,
        customer_name=customer_name,
        pujari_phone=pujari_phone,
        pujari_name=pujari_name,
        pujari_bio=pujari_bio,
        city=city,
        zone_name=zone_name,
        lat=lat,
        lon=lon,
        puja_id=DEFAULT_PUJA_ID,
        puja_name=puja_name,
        puja_price=puja_price,
        payment_mode=payment_mode,
        slot_date=slot_date,
        slot_time=slot_time,
    )
    show("session config", cfg.__dict__)
    return cfg


async def db_query(sql: str, params: dict | None = None) -> list[dict]:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    from app.core.config import get_settings

    engine = create_async_engine(str(get_settings().DATABASE_URL))
    async with engine.connect() as conn:
        rows = (await conn.execute(text(sql), params or {})).mappings().all()
    await engine.dispose()
    return [dict(r) for r in rows]


async def db_execute(sql: str, params: dict | None = None) -> None:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    from app.core.config import get_settings

    engine = create_async_engine(str(get_settings().DATABASE_URL))
    async with engine.begin() as conn:
        await conn.execute(text(sql), params or {})
    await engine.dispose()


async def clean_dev_data(flush_redis: bool) -> None:
    sql_path = Path(__file__).parent / "clean_dev_data.sql"
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    from app.core.config import get_settings

    engine = create_async_engine(str(get_settings().DATABASE_URL))
    async with engine.begin() as conn:
        await conn.execute(text(sql_path.read_text(encoding="utf-8")))
    await engine.dispose()
    print("PostgreSQL: transactional tables truncated (clean_dev_data.sql).")

    if flush_redis:
        import redis as redis_lib

        r = redis_lib.from_url(str(get_settings().REDIS_URL), socket_connect_timeout=5)
        r.flushdb()
        print("Redis: FLUSHDB — all keys removed (OTP limits, presence, Celery queues).")
        print("      Restart Celery worker + Beat after flush.")


async def bootstrap_fixtures(cfg: SessionConfig) -> None:
    """Catalog, service area, pujari profile (verified — KYC skipped)."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    from app.core.config import get_settings

    engine = create_async_engine(str(get_settings().DATABASE_URL))
    async with engine.begin() as conn:
        await conn.execute(text("""
            INSERT INTO cancellation_policies (name, refund_pct_before_24h, refund_pct_after_24h)
            VALUES ('standard', 100, 50) ON CONFLICT (name) DO NOTHING
        """))
        await conn.execute(text("""
            INSERT INTO puja_categories (name) VALUES ('E2E Category') ON CONFLICT (name) DO NOTHING
        """))
        await conn.execute(
            text("""
                INSERT INTO pujas (id, category_id, name, default_price, duration_minutes, is_active)
                VALUES (:pid, (SELECT id FROM puja_categories WHERE name='E2E Category'),
                        :name, :price, 90, true)
                ON CONFLICT (id) DO UPDATE SET
                    name = EXCLUDED.name,
                    default_price = EXCLUDED.default_price,
                    is_active = true
            """),
            {"pid": cfg.puja_id, "name": cfg.puja_name, "price": cfg.puja_price},
        )
        # Pujari user (may already exist from prior OTP runs)
        await conn.execute(
            text("""
                INSERT INTO users (id, full_name, phone, is_active, created_at, updated_at)
                VALUES (gen_random_uuid(), :name, :ph, true, now(), now())
                ON CONFLICT (phone) DO UPDATE SET full_name = EXCLUDED.full_name
            """),
            {"name": cfg.pujari_name, "ph": cfg.pujari_phone},
        )
        uid = (
            await conn.execute(text("SELECT id FROM users WHERE phone = :ph"), {"ph": cfg.pujari_phone})
        ).scalar_one()
        cfg.pujari_user_id = str(uid)

        existing_pj = (
            await conn.execute(text("SELECT id FROM pujaris WHERE user_id = :uid"), {"uid": str(uid)})
        ).scalar_one_or_none()
        if existing_pj:
            cfg.pujari_id = str(existing_pj)
            await conn.execute(
                text("""
                    UPDATE pujaris SET bio = :bio, verification_status = 'verified', updated_at = now()
                    WHERE id = :pj
                """),
                {"pj": cfg.pujari_id, "bio": cfg.pujari_bio},
            )
        else:
            await conn.execute(
                text("""
                    INSERT INTO pujaris (id, user_id, bio, years_experience, verification_status, created_at, updated_at)
                    VALUES (:pj, :uid, :bio, 5, 'verified', now(), now())
                """),
                {"pj": cfg.pujari_id, "uid": str(uid), "bio": cfg.pujari_bio},
            )

        await conn.execute(
            text("""
                INSERT INTO service_areas (city, zone_name, is_active)
                VALUES (:city, :zone, true) ON CONFLICT (city, zone_name) DO NOTHING
            """),
            {"city": cfg.city, "zone": cfg.zone_name},
        )
        sa = (
            await conn.execute(
                text("SELECT id FROM service_areas WHERE city=:city AND zone_name=:zone"),
                {"city": cfg.city, "zone": cfg.zone_name},
            )
        ).scalar_one()
        await conn.execute(
            text("""
                INSERT INTO pujari_service_areas (pujari_id, service_area_id)
                VALUES (:pj, :sa) ON CONFLICT DO NOTHING
            """),
            {"pj": cfg.pujari_id, "sa": sa},
        )
        await conn.execute(
            text("""
                INSERT INTO pujari_live_location (pujari_id, latitude, longitude, geom, updated_at)
                VALUES (:pj, :lat, :lon, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography, now())
                ON CONFLICT (pujari_id) DO UPDATE SET
                    latitude = EXCLUDED.latitude,
                    longitude = EXCLUDED.longitude,
                    geom = EXCLUDED.geom,
                    updated_at = now()
            """),
            {"pj": cfg.pujari_id, "lat": cfg.lat, "lon": cfg.lon},
        )
    await engine.dispose()


def set_presence(pujari_id: str) -> None:
    import redis as redis_lib

    from app.core.config import get_settings

    r = redis_lib.from_url(str(get_settings().REDIS_URL), socket_connect_timeout=5)
    r.set(f"presence:{pujari_id}", "1", ex=90)
    print(f"Redis whiteboard: SET presence:{pujari_id} TTL 90s → OK")


async def ensure_customer_address(cfg: SessionConfig, user_id: str) -> str:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    from app.core.config import get_settings

    engine = create_async_engine(str(get_settings().DATABASE_URL))
    async with engine.begin() as conn:
        existing = (
            await conn.execute(
                text(
                    "SELECT id FROM addresses WHERE user_id = :uid "
                    "AND geom IS NOT NULL ORDER BY created_at DESC LIMIT 1"
                ),
                {"uid": user_id},
            )
        ).scalar_one_or_none()
        if existing:
            await engine.dispose()
            return str(existing)

        new_id = str(uuid.uuid4())
        line1 = prompt("Customer address line1", "Home")
        await conn.execute(
            text("""
                INSERT INTO addresses (id, user_id, line1, city, latitude, longitude, geom)
                VALUES (:aid, :uid, :line1, :city, :lat, :lon,
                        ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography)
            """),
            {
                "aid": new_id,
                "uid": user_id,
                "line1": line1,
                "city": cfg.city,
                "lat": cfg.lat,
                "lon": cfg.lon,
            },
        )
    await engine.dispose()
    return new_id


def pick_slot(cfg: SessionConfig) -> tuple[str, str]:
    if cfg.slot_date and cfg.slot_time:
        return cfg.slot_date, cfg.slot_time
    slot_date_obj = dt.date.today() + dt.timedelta(days=random.randint(14, 90))
    slot_hour = random.randint(8, 17)
    slot_minute = random.choice([0, 30])
    return slot_date_obj.isoformat(), f"{slot_hour:02d}:{slot_minute:02d}:00"


async def simulate_pujari_notification(
    cfg: SessionConfig, booking_id: str, assignment_id: str
) -> None:
    """Dev stand-in for FCM push: DB notification row + notification worker log."""
    if not cfg.pujari_user_id:
        print("WARN: pujari_user_id unknown — skip notification insert.")
        return

    notif_id = str(uuid.uuid4())
    await db_execute(
        """
        INSERT INTO notifications (
            id, user_id, app_context, related_type, related_id,
            title, body, created_at
        ) VALUES (
            :nid, :uid, 'pujari', 'assignment', :aid,
            'New booking offer',
            'You have a new puja request nearby. Open the app to view and accept.',
            now()
        )
        """,
        {
            "nid": notif_id,
            "uid": cfg.pujari_user_id,
            "aid": assignment_id,
        },
    )
    show("DB notifications (inserted dev in-app notification)", await db_query(
        "SELECT id, title, body, related_type, related_id, read_at, created_at "
        "FROM notifications WHERE user_id = :uid ORDER BY created_at DESC LIMIT 3",
        {"uid": cfg.pujari_user_id},
    ))

    from app.workers.notifications import notify_offers

    result = notify_offers(booking_id)
    show("notify_offers() worker stub (FCM/SMS would fire in prod)", result)
    print(textwrap.dedent("""
        📱 Pujari notification path (dev):
          • In-app row inserted in notifications table (above)
          • Celery worker logs notify_offers if worker is running
          • Real app: FCM push + pujari polls GET /v1/offers as safety net
          • Watch Celery terminal for: notify_offers booking_id=...
    """))


async def wait_for_assignments(booking_id: str, timeout_s: int = 45) -> list[dict]:
    print(f"Waiting up to {timeout_s}s for Celery dispatch worker to create offers…")
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        rows = await verify_assignments(booking_id)
        if rows:
            return rows
        await asyncio.sleep(2)
    return []


async def verify_otp_rows(phone: str) -> None:
    rows = await db_query(
        """
        SELECT id, phone, attempts, verified_at IS NOT NULL AS verified,
               expires_at > now() AS still_valid, created_at,
               left(otp_hash, 12) || '…' AS otp_hash_prefix
        FROM otp_verifications WHERE phone = :ph
        ORDER BY created_at DESC LIMIT 3
        """,
        {"ph": phone},
    )
    show("DB otp_verifications (latest 3)", rows)


async def verify_user(phone: str) -> str | None:
    rows = await db_query(
        "SELECT id, full_name, phone, is_active, created_at FROM users WHERE phone = :ph",
        {"ph": phone},
    )
    show("DB users", rows)
    return str(rows[0]["id"]) if rows else None


async def verify_session(phone: str) -> None:
    rows = await db_query(
        """
        SELECT s.id, s.app_context, s.issued_at, s.expires_at, s.revoked_at IS NOT NULL AS revoked
        FROM auth_sessions s
        JOIN users u ON u.id = s.user_id
        WHERE u.phone = :ph
        ORDER BY s.issued_at DESC LIMIT 3
        """,
        {"ph": phone},
    )
    show("DB auth_sessions (latest 3)", rows)


async def verify_pujari_profile(cfg: SessionConfig) -> None:
    rows = await db_query(
        """
        SELECT p.id, p.user_id, u.full_name, u.phone, p.verification_status, p.bio,
               p.is_online, pll.latitude, pll.longitude
        FROM pujaris p
        JOIN users u ON u.id = p.user_id
        LEFT JOIN pujari_live_location pll ON pll.pujari_id = p.id
        WHERE p.id = :pid
        """,
        {"pid": cfg.pujari_id},
    )
    show("DB pujaris (registered — KYC skipped, status=verified)", rows)


async def verify_hold(hold_id: str) -> None:
    rows = await db_query(
        """
        SELECT id, user_id, pujari_id, slot_date, slot_time,
               expires_at > now() AS active, released_at, converted_at
        FROM slot_holds WHERE id = :hid
        """,
        {"hid": hold_id},
    )
    show("DB slot_holds", rows)


async def verify_booking(booking_id: str) -> None:
    rows = await db_query(
        """
        SELECT b.id, st.code AS status, b.payment_mode,
               b.total_amount, b.amount_due_online, b.paid_at,
               b.dispatch_mode, b.pujari_id, b.hold_id, b.cancelled_at
        FROM bookings b
        JOIN status_types st ON st.id = b.status_id
        WHERE b.id = :bid
        """,
        {"bid": booking_id},
    )
    show("DB bookings", rows)


async def verify_payment(booking_id: str) -> None:
    rows = await db_query(
        """
        SELECT id, amount, status, gateway_txn_id, idempotency_key, created_at
        FROM payments WHERE booking_id = :bid ORDER BY created_at DESC
        """,
        {"bid": booking_id},
    )
    show("DB payments", rows)


async def verify_assignments(booking_id: str) -> list[dict]:
    rows = await db_query(
        """
        SELECT ba.id AS assignment_id, ba.pujari_id, st.code AS status,
               ba.offered_at, ba.expires_at, ba.responded_at
        FROM booking_assignments ba
        JOIN status_types st ON st.id = ba.status_id
        WHERE ba.booking_id = :bid
        ORDER BY ba.offered_at
        """,
        {"bid": booking_id},
    )
    show("DB booking_assignments", rows)
    return rows


def sign_webhook(body: bytes, secret: str) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


async def run(base_url: str, *, use_celery: bool, do_clean: bool) -> int:
    from app.core.config import get_settings

    settings = get_settings()
    if not settings.DEBUG:
        print("WARN: DEBUG is false — OTP will NOT appear in uvicorn logs.")

    cfg = collect_session_config()

    if do_clean:
        section("CLEAN — reset dev data")
        flush = prompt("Also FLUSH Redis db0? (y/N)", "N").lower() in ("y", "yes")
        await clean_dev_data(flush_redis=flush)
        pause()

    section("STEP 0 — Register pujari + catalog bootstrap (KYC skipped)")
    print(textwrap.dedent("""
        Creating/updating:
          • Puja catalog entry
          • Pujari user + pujaris row (verification_status='verified' — no documents)
          • Service area + live location (for dispatch radius)
        Real app: pujari would upload KYC docs; admin verifies. We skip that here.
    """))
    await bootstrap_fixtures(cfg)
    await verify_pujari_profile(cfg)
    set_presence(cfg.pujari_id)
    pause()

    async with httpx.AsyncClient(base_url=base_url, timeout=30.0) as client:
        section(f"STEP 1 — Health check ({base_url})")
        h = await client.get("/health")
        show("HTTP /health", {"status": h.status_code, "body": h.json()})
        if h.status_code != 200 or h.json().get("status") != "ok":
            return 1
        pause()

        section(f"STEP 2 — Customer OTP ({cfg.customer_phone})")
        print("Watch uvicorn for otp_dev_only=XXXXXX")
        r = await client.post("/v1/auth/otp/request", json={"phone": cfg.customer_phone})
        show("HTTP POST /v1/auth/otp/request [API → Redis whiteboard rate limit]", {
            "status": r.status_code,
            "body": r.json() if r.status_code < 500 else r.text,
        })
        if r.status_code >= 500:
            return 1
        await verify_otp_rows(cfg.customer_phone)
        otp = input("\nEnter customer OTP from uvicorn log: ").strip()
        pause()

        section("STEP 3 — Customer verify → JWT + address")
        r = await client.post(
            "/v1/auth/otp/verify",
            json={"phone": cfg.customer_phone, "otp": otp},
        )
        show("HTTP POST /v1/auth/otp/verify", {
            "status": r.status_code,
            "body": r.json() if r.status_code == 200 else r.text,
        })
        if r.status_code != 200:
            return 1
        customer_token = r.json()["access_token"]
        ch = {"Authorization": f"Bearer {customer_token}"}
        user_id = await verify_user(cfg.customer_phone)
        await verify_session(cfg.customer_phone)
        address_id = await ensure_customer_address(cfg, str(user_id))
        show("address_id", address_id)
        pause()

        section("STEP 4 — Slot hold")
        slot_date, slot_time = pick_slot(cfg)
        show("slot", {"date": slot_date, "time": slot_time})
        r = await client.post(
            "/v1/slot-holds",
            headers=ch,
            json={"date": slot_date, "time": slot_time},
        )
        show("HTTP POST /v1/slot-holds", {"status": r.status_code, "body": r.json()})
        if r.status_code != 201:
            return 1
        hold_id = r.json()["hold_id"]
        await verify_hold(hold_id)
        pause()

        section("STEP 5 — Create booking (Razorpay test order)")
        r = await client.post(
            "/v1/bookings",
            headers=ch,
            json={
                "hold_id": hold_id,
                "puja_id": cfg.puja_id,
                "address_id": address_id,
                "payment_mode": cfg.payment_mode,
            },
        )
        show("HTTP POST /v1/bookings", {
            "status": r.status_code,
            "body": r.json() if r.status_code in (201, 409) else r.text,
        })
        if r.status_code not in (201, 409):
            return 1
        booking = r.json()
        booking_id = booking["booking_id"]
        if not booking.get("razorpay_order_id"):
            print("ERROR: missing razorpay_order_id — cannot continue to webhook.")
            return 1
        amount_paise = int(float(booking["amount_due_online"]) * 100)
        await verify_booking(booking_id)
        pause()

        section("STEP 6 — Mock Razorpay webhook (payment.captured)")
        if not settings.RAZORPAY_WEBHOOK_SECRET:
            print("Set RAZORPAY_WEBHOOK_SECRET in .env")
            return 1
        pay_id = f"pay_manual_{uuid.uuid4().hex[:10]}"
        payload = {
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
        raw = json.dumps(payload, separators=(",", ":")).encode()
        sig = sign_webhook(raw, settings.RAZORPAY_WEBHOOK_SECRET)
        r = await client.post(
            "/v1/webhooks/razorpay",
            content=raw,
            headers={"Content-Type": "application/json", "X-Razorpay-Signature": sig},
        )
        show("HTTP POST /v1/webhooks/razorpay [API → broker enqueue if Celery]", {
            "status": r.status_code,
            "body": r.json(),
        })
        await verify_booking(booking_id)
        await verify_payment(booking_id)
        pause()

        section("STEP 7 — Dispatch broadcast")
        set_presence(cfg.pujari_id)
        if use_celery:
            print("Using Celery: webhook should have enqueued broadcast_booking.")
            print("Ensure worker is running: celery -A app.workers.celery_app worker ...")
            assignments = await wait_for_assignments(booking_id)
            if not assignments:
                print("No offers from Celery — falling back to direct broadcast_booking().")
                from app.workers.dispatch import broadcast_booking

                show("broadcast_booking() fallback", broadcast_booking(booking_id))
                assignments = await verify_assignments(booking_id)
        else:
            print("Direct dispatch (dev): calling broadcast_booking() — skips broker queue.")
            from app.workers.dispatch import broadcast_booking

            show("broadcast_booking()", broadcast_booking(booking_id))
            assignments = await verify_assignments(booking_id)

        if not assignments:
            print("No offers — check pujari geom, service_area, Redis presence.")
            return 1
        assignment_id = str(assignments[0]["assignment_id"])
        pause()

        section("STEP 7b — Pujari notification (dev simulation)")
        await simulate_pujari_notification(cfg, booking_id, assignment_id)
        pause()

        section(f"STEP 8 — Pujari app login + accept ({cfg.pujari_phone})")
        print(textwrap.dedent("""
            Simulating pujari opening the app after notification:
              1) OTP login (app_context=pujari)
              2) PUT /me/heartbeat (go online — like real app)
              3) GET /v1/offers (poll — safety net if push missed)
              4) POST accept
        """))
        r = await client.post("/v1/auth/otp/request", json={"phone": cfg.pujari_phone})
        show("pujari otp/request", r.status_code)
        pujari_otp = input("Pujari OTP from uvicorn log: ").strip()
        r = await client.post(
            "/v1/auth/otp/verify?app_context=pujari",
            json={"phone": cfg.pujari_phone, "otp": pujari_otp},
        )
        if r.status_code != 200:
            show("pujari verify failed", r.text)
            return 1
        ph = {"Authorization": f"Bearer {r.json()['access_token']}"}
        r = await client.put(
            "/v1/me/heartbeat",
            headers=ph,
            json={"lat": cfg.lat, "lng": cfg.lon},
        )
        show("PUT /v1/me/heartbeat [API → Redis presence + DB location]", {
            "status": r.status_code,
            "body": r.json() if r.status_code == 200 else r.text,
        })
        offers = await client.get("/v1/offers", headers=ph)
        show("GET /v1/offers (what pujari sees)", offers.json())
        if not offers.json().get("offers"):
            print("No live offers for pujari token — check app_context and assignment.")
            return 1
        live_aid = offers.json()["offers"][0]["assignment_id"]
        r = await client.post(f"/v1/offers/{live_aid}/accept", headers=ph)
        show("POST accept", {"status": r.status_code, "body": r.json()})
        await verify_booking(booking_id)
        await verify_assignments(booking_id)
        hist = await db_query(
            """
            SELECT st.code, h.changed_at
            FROM booking_status_history h
            JOIN status_types st ON st.id = h.status_id
            WHERE h.booking_id = :bid ORDER BY h.changed_at
            """,
            {"bid": booking_id},
        )
        show("DB booking_status_history", hist)

    section("DONE — Final pre-launch manual verification complete")
    print(f"Customer:  {cfg.customer_phone} ({cfg.customer_name})")
    print(f"Pujari:    {cfg.pujari_phone} ({cfg.pujari_name}) id={cfg.pujari_id}")
    print(f"Booking:   {booking_id}")
    print("Expected:  status=confirmed, pujari_id set, assignment accepted")
    print("KYC:       skipped (verification_status=verified set in bootstrap)")
    return 0


def main() -> None:
    p = argparse.ArgumentParser(description="Interactive full booking-flow verifier")
    p.add_argument("--base-url", default="http://127.0.0.1:8000")
    p.add_argument(
        "--use-celery",
        action="store_true",
        help="Wait for Celery worker dispatch after webhook (production-like)",
    )
    p.add_argument(
        "--clean",
        action="store_true",
        help="Truncate dev transactional tables before run (see clean_dev_data.sql)",
    )
    args = p.parse_args()
    raise SystemExit(asyncio.run(run(args.base_url, use_celery=args.use_celery, do_clean=args.clean)))


if __name__ == "__main__":
    main()
