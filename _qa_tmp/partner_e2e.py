"""QA Phase 4: Partner app E2E - go online, offers, accept, service lifecycle, collect money."""
from __future__ import annotations

import asyncio
import datetime as dt
import hashlib
import hmac
import json
import random
import sys
import time
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
OUT: list[str] = []


def log(m: str) -> None:
    OUT.append(m)
    print(m)


def _clear_otp_rl(phone: str) -> None:
    import redis as redis_lib
    from app.core.config import get_settings
    try:
        redis_lib.from_url(str(get_settings().REDIS_URL)).delete(f"otp_req:{phone}")
    except Exception:
        pass


def login(phone: str, ctx: str) -> str:
    _clear_otp_rl(phone)
    with httpx.Client(base_url=BASE, timeout=30) as c:
        body = c.post("/v1/auth/otp/request", json={"phone": phone}).json()
        otp = body.get("otp_dev_only")
        if not otp:
            raise RuntimeError(f"no otp_dev_only (rate-limited?): {body}")
        return c.post("/v1/auth/otp/verify", json={"phone": phone, "otp": otp, "app_context": ctx}).json()["access_token"]


def sign(body: bytes) -> str:
    from app.core.config import get_settings
    return hmac.new(str(get_settings().RAZORPAY_WEBHOOK_SECRET).encode(), body, hashlib.sha256).hexdigest()


def dbexec(sql, params=None, fetch=False):
    import psycopg
    from app.core.config import get_settings
    url = str(get_settings().DATABASE_URL).replace("postgresql+psycopg://", "postgresql://")
    with psycopg.connect(url) as pc:
        with pc.cursor() as cur:
            cur.execute(sql, params or ())
            if fetch:
                return cur.fetchall()
            pc.commit()


def create_paid_booking(info: dict, ch: dict) -> tuple[str, Decimal]:
    c = httpx.Client(base_url=BASE, timeout=30, headers=ch)
    slot_date = (dt.date.today() + dt.timedelta(days=random.randint(15, 180))).isoformat()
    slot_time = f"{random.randint(9,17):02d}:{random.choice(['00','15','30','45'])}:00"
    hold = c.post("/v1/slot-holds", json={"date": slot_date, "time": slot_time}).json()["hold_id"]
    b = c.post("/v1/bookings", json={"hold_id": hold, "puja_id": info["puja_id"], "address_id": info["address_id"], "payment_mode": "booking_fee"}).json()
    booking_id = b["booking_id"]
    amt = Decimal(str(b["razorpay_amount"]))
    body = {"event": "payment.captured", "payload": {"payment": {"entity": {"id": f"pay_qa_{uuid.uuid4().hex[:10]}", "amount": int(amt*100), "currency": "INR", "notes": {"booking_id": booking_id}}}}}
    raw = json.dumps(body, separators=(",", ":")).encode()
    httpx.Client(base_url=BASE, timeout=30).post("/v1/webhooks/razorpay", content=raw, headers={"Content-Type": "application/json", "X-Razorpay-Signature": sign(raw)})
    return booking_id, amt


def main() -> int:
    import customer_e2e
    info = asyncio.run(customer_e2e.setup())
    log(f"[setup] pujari={info['pujari_id']} puja={info['puja_name']!r}")

    # presence on
    import redis as redis_lib
    from app.core.config import get_settings
    redis_lib.from_url(str(get_settings().REDIS_URL)).set(f"presence:{info['pujari_id']}", "1", ex=300)

    ctoken = login(CUSTOMER_PHONE, "customer")
    ch = {"Authorization": f"Bearer {ctoken}"}
    booking_id, amt = create_paid_booking(info, ch)
    log(f"[customer] paid booking {booking_id} razorpay_amount={amt}")

    # dispatch
    from app.workers.dispatch import broadcast_booking
    time.sleep(1)
    disp = broadcast_booking(booking_id)
    log(f"[dispatch] {disp}")

    # ---- PARTNER ----
    ptoken = login(PUJARI_PHONE, "pujari")
    ph = {"Authorization": f"Bearer {ptoken}"}
    pc = httpx.Client(base_url=BASE, timeout=30, headers=ph)

    # go online
    r = pc.put("/v1/me/heartbeat", json={})
    log(f"[PUT /v1/me/heartbeat go-online] {r.status_code} {r.text[:120]}")

    # offers
    r = pc.get("/v1/offers")
    offers = r.json().get("offers", [])
    log(f"[GET /v1/offers] {r.status_code} count={len(offers)} sample_keys={list(offers[0].keys()) if offers else None}")
    mine = [o for o in offers if o["booking_id"] == booking_id]
    if not mine:
        log(f"[offers] FAIL - my booking {booking_id} not in offers")
        # dump what offers exist
        log(f"   offer booking_ids: {[o['booking_id'] for o in offers][:5]}")
        return 1
    off = mine[0]
    log(f"[offer detail] puja={off.get('puja_name')} area={off.get('area_label')} class={off.get('booking_class')} offline_due={off.get('amount_due_offline')} has_phone={'phone' in off} has_address={'address' in str(off).lower() and 'area' not in str(off).lower()}")
    assignment_id = off["assignment_id"]

    # accept
    r = pc.post(f"/v1/offers/{assignment_id}/accept")
    log(f"[POST /v1/offers/accept] {r.status_code} {r.text[:200]}")

    # verify booking confirmed + pujari + rm
    rows = dbexec("SELECT st.code, b.pujari_id, b.relationship_manager_id FROM bookings b JOIN status_types st ON st.id=b.status_id WHERE b.id=%s", (booking_id,), fetch=True)
    log(f"[db booking after accept] status={rows[0][0]} pujari_set={rows[0][1] is not None} rm_set={rows[0][2] is not None}")

    # notify_accept_ack fired?
    time.sleep(3)
    nrows = dbexec("SELECT app_context, title FROM notifications WHERE related_id=%s ORDER BY created_at DESC", (booking_id,), fetch=True)
    log(f"[notifications after accept] {nrows[:4]}")

    # pujari bookings list + detail
    r = pc.get("/v1/pujari/bookings")
    jb = r.json()
    log(f"[GET /v1/pujari/bookings] {r.status_code} count={len(jb.get('bookings', []))}")
    r = pc.get(f"/v1/pujari/bookings/{booking_id}")
    jd = r.json() if r.status_code == 200 else {"err": r.text[:150]}
    log(f"[GET /v1/pujari/bookings/id] {r.status_code} status={jd.get('status')} customer_phone_present={'customer_phone' in jd or 'phone' in jd} rm={bool(jd.get('relationship_manager'))}")

    # ---- LIFECYCLE (seed scheduled time to now to pass +/-60min start gate) ----
    dbexec("UPDATE bookings SET scheduled_date=%s, scheduled_time=%s WHERE id=%s", (dt.date.today().isoformat(), dt.datetime.now().strftime("%H:%M:00"), booking_id))
    r = pc.post(f"/v1/bookings/{booking_id}/start")
    log(f"[POST start] {r.status_code} {r.text[:150]}")
    r = pc.post(f"/v1/bookings/{booking_id}/confirm-balance-collected", json={"method": "cash"})
    log(f"[POST confirm-balance-collected] {r.status_code} {r.text[:250]}")
    r = pc.post(f"/v1/bookings/{booking_id}/complete")
    log(f"[POST complete] {r.status_code} {r.text[:150]}")
    rows = dbexec("SELECT st.code, b.balance_collected_amount, b.balance_collection_method FROM bookings b JOIN status_types st ON st.id=b.status_id WHERE b.id=%s", (booking_id,), fetch=True)
    log(f"[db final] status={rows[0][0]} collected_amount={rows[0][1]} method={rows[0][2]}")

    # tax summary
    r = pc.get("/v1/me/tax-summary")
    log(f"[GET /v1/me/tax-summary] {r.status_code} {str(r.json())[:200] if r.status_code==200 else r.text[:150]}")

    # go offline
    r = pc.delete("/v1/me/heartbeat")
    log(f"[DELETE /v1/me/heartbeat go-offline] {r.status_code} {r.text[:80]}")

    with open("partner_e2e_result.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(OUT))
    log("DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
