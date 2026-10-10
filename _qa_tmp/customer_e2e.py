"""QA Phase 3: Customer app E2E against the running API (booking_fee launch flow)."""
from __future__ import annotations

import asyncio
import datetime as dt
import hashlib
import hmac
import json
import sys
import uuid
from decimal import Decimal

import httpx
from dotenv import load_dotenv

load_dotenv()
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

BASE = "http://127.0.0.1:8000"
CUSTOMER_PHONE = "+919300000031"
PUJARI_PHONE = "+919300000032"
LAT, LON = 17.385044, 78.486671
OUT: list[str] = []


def log(msg: str) -> None:
    OUT.append(msg)
    print(msg)


async def setup() -> dict:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine
    from app.core.config import get_settings
    from app.services.partner_dispatch_readiness import ensure_partner_dispatch_readiness

    eng = create_async_engine(str(get_settings().DATABASE_URL))
    info: dict = {}
    async with eng.begin() as conn:
        # customer
        cust = (await conn.execute(text(
            "INSERT INTO users (id, full_name, phone, is_active) VALUES (gen_random_uuid(),'QA Customer',:p,true) "
            "ON CONFLICT (phone) DO UPDATE SET full_name='QA Customer' RETURNING id"), {"p": CUSTOMER_PHONE})).scalar_one()
        # service area
        await conn.execute(text(
            "INSERT INTO service_areas (city, zone_name, is_active) VALUES ('Hyderabad','QA Zone',true) "
            "ON CONFLICT (city, zone_name) DO NOTHING"))
        sa = (await conn.execute(text("SELECT id FROM service_areas WHERE city='Hyderabad' AND zone_name='QA Zone'"))).scalar_one()
        # address
        addr = (await conn.execute(text(
            "INSERT INTO addresses (id, user_id, line1, city, latitude, longitude, service_area_id, geom) "
            "VALUES (gen_random_uuid(), :uid, 'QA Street', 'Hyderabad', :lat, :lon, :sa, "
            "ST_SetSRID(ST_MakePoint(:lon,:lat),4326)::geography) "
            "ON CONFLICT DO NOTHING RETURNING id"), {"uid": str(cust), "lat": LAT, "lon": LON, "sa": str(sa)})).scalar_one_or_none()
        if addr is None:
            addr = (await conn.execute(text("SELECT id FROM addresses WHERE user_id=:uid AND line1='QA Street' LIMIT 1"), {"uid": str(cust)})).scalar_one()
        # pujari
        puj_user = (await conn.execute(text(
            "INSERT INTO users (id, full_name, phone, is_active) VALUES (gen_random_uuid(),'QA Pujari',:p,true) "
            "ON CONFLICT (phone) DO UPDATE SET full_name='QA Pujari' RETURNING id"), {"p": PUJARI_PHONE})).scalar_one()
        puj = (await conn.execute(text(
            "INSERT INTO pujaris (id, user_id, verification_status) VALUES (gen_random_uuid(), :uid, 'verified') "
            "ON CONFLICT (user_id) DO UPDATE SET verification_status='verified' RETURNING id"), {"uid": str(puj_user)})).scalar_one()
        # pick a real active puja (griha-pravesham if present)
        puja = (await conn.execute(text(
            "SELECT id, name, default_price FROM pujas WHERE is_active=true AND slug='griha-pravesham' LIMIT 1"))).first()
        if puja is None:
            puja = (await conn.execute(text(
                "SELECT id, name, default_price FROM pujas WHERE is_active=true AND name NOT ILIKE '%test%' "
                "AND name NOT ILIKE '%puja%range%' ORDER BY default_price DESC LIMIT 1"))).first()
        info["puja_id"], info["puja_name"], info["puja_price"] = str(puja[0]), puja[1], str(puja[2])
        await ensure_partner_dispatch_readiness(conn, pujari_id=uuid.UUID(str(puj)))
        info["customer_id"], info["address_id"] = str(cust), str(addr)
        info["pujari_id"], info["pujari_user_id"] = str(puj), str(puj_user)
    await eng.dispose()

    # presence
    import redis as redis_lib
    r = redis_lib.from_url(str(get_settings().REDIS_URL), socket_connect_timeout=5)
    r.set(f"presence:{info['pujari_id']}", "1", ex=300)
    info["presence_set"] = True
    return info


def sign(body: bytes) -> str:
    from app.core.config import get_settings
    secret = str(get_settings().RAZORPAY_WEBHOOK_SECRET)
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def login(phone: str, ctx: str) -> str:
    with httpx.Client(base_url=BASE, timeout=30) as c:
        r = c.post("/v1/auth/otp/request", json={"phone": phone})
        otp = r.json().get("otp_dev_only")
        v = c.post("/v1/auth/otp/verify", json={"phone": phone, "otp": otp, "app_context": ctx})
        v.raise_for_status()
        return v.json()["access_token"]


def main() -> int:
    info = asyncio.run(setup())
    log(f"[setup] puja={info['puja_name']!r} price={info['puja_price']} pujari={info['pujari_id']} addr={info['address_id']}")

    token = login(CUSTOMER_PHONE, "customer")
    h = {"Authorization": f"Bearer {token}"}
    c = httpx.Client(base_url=BASE, timeout=30, headers=h)

    # catalog
    r = c.get("/v1/pujas?limit=5")
    log(f"[GET /v1/pujas] {r.status_code} count={len(r.json().get('pujas', []))}")

    # puja detail
    r = c.get(f"/v1/pujas/{info['puja_id']}")
    d = r.json() if r.status_code == 200 else {}
    log(f"[GET /v1/pujas/id] {r.status_code} name={d.get('name')!r} content_items={len(d.get('content') or d.get('content_items') or [])} addons={len(d.get('addons') or [])}")

    # panchangam
    try:
        r = c.get("/v1/panchangam?city=Hyderabad")
        log(f"[GET /v1/panchangam] {r.status_code} body_keys={list(r.json().keys())[:8] if r.status_code==200 else r.text[:120]}")
    except Exception as e:
        log(f"[GET /v1/panchangam] ERROR {e}")

    # quote
    r = c.get(f"/v1/checkout/quote?puja_id={info['puja_id']}")
    q = r.json()
    log(f"[GET /v1/checkout/quote] {r.status_code} total={q.get('total_amount')} booking_fee={q.get('booking_fee')} razorpay_amount={q.get('razorpay_amount')} mode={q.get('payment_mode')}")

    # slot hold (advance, far-future daytime) - randomized to avoid idempotent duplicate
    import random as _rnd
    slot_date = (dt.date.today() + dt.timedelta(days=_rnd.randint(15, 180))).isoformat()
    slot_time = f"{_rnd.randint(9, 17):02d}:{_rnd.choice(['00','15','30','45'])}:00"
    r = c.post("/v1/slot-holds", json={"date": slot_date, "time": slot_time})
    log(f"[POST /v1/slot-holds] {r.status_code} class={r.json().get('advisory_booking_class')} warnings={r.json().get('gate_warnings')}")
    hold_id = r.json()["hold_id"]

    # create booking (booking_fee)
    r = c.post("/v1/bookings", json={"hold_id": hold_id, "puja_id": info["puja_id"], "address_id": info["address_id"], "payment_mode": "booking_fee"})
    if r.status_code != 201:
        log(f"[POST /v1/bookings] FAIL {r.status_code} {r.text[:300]}")
        return 1
    b = r.json()
    booking_id = b["booking_id"]
    razor_amt = Decimal(str(b["razorpay_amount"]))
    log(f"[POST /v1/bookings] 201 booking_id={booking_id} class={b['booking_class']} order={b.get('razorpay_order_id')} razorpay_amount={razor_amt} total={b.get('total_amount')}")

    # webhook payment.captured
    pay_id = f"pay_qa_{uuid.uuid4().hex[:12]}"
    amount_paise = int(razor_amt * 100)
    body = {"event": "payment.captured", "payload": {"payment": {"entity": {"id": pay_id, "amount": amount_paise, "currency": "INR", "notes": {"booking_id": booking_id}}}}}
    raw = json.dumps(body, separators=(",", ":")).encode()
    wr = httpx.Client(base_url=BASE, timeout=30).post("/v1/webhooks/razorpay", content=raw, headers={"Content-Type": "application/json", "X-Razorpay-Signature": sign(raw)})
    log(f"[POST /v1/webhooks/razorpay] {wr.status_code} {wr.text[:160]}")

    # dispatch
    import time
    from app.workers.dispatch import broadcast_booking
    import redis as redis_lib
    from app.core.config import get_settings
    redis_lib.from_url(str(get_settings().REDIS_URL)).set(f"presence:{info['pujari_id']}", "1", ex=300)
    time.sleep(2)  # let the running sweep attempt a round too
    disp = broadcast_booking(booking_id)
    log(f"[dispatch.broadcast_booking] -> {disp}")

    # booking detail
    r = c.get(f"/v1/bookings/{booking_id}")
    bd = r.json()
    log(f"[GET /v1/bookings/id] {r.status_code} status={bd.get('status')} payment_mode={bd.get('payment_mode')} razorpay_amount={bd.get('razorpay_amount')} history={[hh.get('status') for hh in bd.get('history',[])]}")

    # notifications fired?
    import psycopg
    time.sleep(4)
    dburl = str(get_settings().DATABASE_URL).replace("postgresql+psycopg://", "postgresql://")

    def q(sql, params):
        with psycopg.connect(dburl) as pc:
            with pc.cursor() as cur:
                cur.execute(sql, params)
                return cur.fetchall()

    nrows = q("SELECT app_context, title FROM notifications WHERE related_id = %s", (booking_id,))
    offers = q("SELECT ba.id, st.code FROM booking_assignments ba JOIN status_types st ON st.id=ba.status_id WHERE ba.booking_id = %s", (booking_id,))
    log(f"[notifications] rows_for_booking={len(nrows)} sample={nrows[:2]} offers={len(offers)} offer_status={[o[1] for o in offers]}")

    # cancel -> refund
    r = c.post(f"/v1/bookings/{booking_id}/cancel")
    log(f"[POST /v1/bookings/id/cancel] {r.status_code} {r.text[:200]}")
    time.sleep(2)
    rf = q("SELECT status, amount FROM refunds WHERE booking_id = %s ORDER BY created_at DESC LIMIT 1", (booking_id,))
    offers_after = q("SELECT st.code FROM booking_assignments ba JOIN status_types st ON st.id=ba.status_id WHERE ba.booking_id = %s", (booking_id,))
    log(f"[refund row] {rf}  offers_after_cancel={[o[0] for o in offers_after]}")

    with open("customer_e2e_result.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(OUT))
    log("DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
