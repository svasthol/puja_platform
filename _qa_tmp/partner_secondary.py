"""QA Phase 4b: partner secondary actions - reject, pujari-cancel, reconfirm, KYC register/status."""
from __future__ import annotations

import asyncio
import datetime as dt
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


def log(m):
    OUT.append(str(m)); print(m)


def _clear_rl(phone):
    import redis as redis_lib
    from app.core.config import get_settings
    try:
        redis_lib.from_url(str(get_settings().REDIS_URL)).delete(f"otp_req:{phone}")
    except Exception:
        pass


def login(phone, ctx):
    _clear_rl(phone)
    with httpx.Client(base_url=BASE, timeout=30) as c:
        otp = c.post("/v1/auth/otp/request", json={"phone": phone}).json().get("otp_dev_only")
        return c.post("/v1/auth/otp/verify", json={"phone": phone, "otp": otp, "app_context": ctx}).json()["access_token"]


def main():
    import customer_e2e, partner_e2e
    info = asyncio.run(customer_e2e.setup())
    import redis as redis_lib
    from app.core.config import get_settings
    redis_lib.from_url(str(get_settings().REDIS_URL)).set(f"presence:{info['pujari_id']}", "1", ex=600)

    ch = {"Authorization": f"Bearer {login(CUSTOMER_PHONE,'customer')}"}
    ph = {"Authorization": f"Bearer {login(PUJARI_PHONE,'pujari')}"}
    pc = httpx.Client(base_url=BASE, timeout=30, headers=ph)
    pc.put("/v1/me/heartbeat", json={})

    # ---- 1. REJECT an offer ----
    bid, _ = partner_e2e.create_paid_booking(info, ch)
    from app.workers.dispatch import broadcast_booking
    time.sleep(1); broadcast_booking(bid)
    offers = pc.get("/v1/offers").json().get("offers", [])
    mine = [o for o in offers if o["booking_id"] == bid]
    if mine:
        aid = mine[0]["assignment_id"]
        r = pc.post(f"/v1/offers/{aid}/reject")
        log(f"[reject offer] {r.status_code} {r.text[:120]}")
        st = partner_e2e.dbexec("SELECT st.code FROM booking_assignments ba JOIN status_types st ON st.id=ba.status_id WHERE ba.id=%s", (aid,), fetch=True)
        log(f"[reject] assignment_status={st[0][0]}")
    else:
        log("[reject] no offer to reject")

    # ---- 2. PUJARI-CANCEL after accept ----
    bid2, _ = partner_e2e.create_paid_booking(info, ch)
    time.sleep(1); broadcast_booking(bid2)
    offers = pc.get("/v1/offers").json().get("offers", [])
    mine = [o for o in offers if o["booking_id"] == bid2]
    if mine:
        aid2 = mine[0]["assignment_id"]
        pc.post(f"/v1/offers/{aid2}/accept")
        r = pc.post(f"/v1/bookings/{bid2}/pujari-cancel")
        log(f"[pujari-cancel] {r.status_code} {r.text[:150]}")
        st = partner_e2e.dbexec("SELECT st.code, b.pujari_id FROM bookings b JOIN status_types st ON st.id=b.status_id WHERE b.id=%s", (bid2,), fetch=True)
        log(f"[pujari-cancel] booking_status={st[0][0]} pujari_cleared={st[0][1] is None}")

    # ---- 3. RECONFIRM (advance confirmed booking) ----
    bid3, _ = partner_e2e.create_paid_booking(info, ch)
    time.sleep(1); broadcast_booking(bid3)
    offers = pc.get("/v1/offers").json().get("offers", [])
    mine = [o for o in offers if o["booking_id"] == bid3]
    if mine:
        pc.post(f"/v1/offers/{mine[0]['assignment_id']}/accept")
        r = pc.post(f"/v1/pujari/bookings/{bid3}/reconfirm")
        log(f"[reconfirm] {r.status_code} {r.text[:150]}")

    # ---- 4. KYC register (new pujari) + status ----
    newphone = "+9193111" + str(uuid.uuid4().int)[:5]
    nt = login(newphone, "pujari")
    nh = {"Authorization": f"Bearer {nt}"}
    nc = httpx.Client(base_url=BASE, timeout=30, headers=nh)
    r = nc.post("/v1/pujari/register", json={"full_name": "QA New Pujari", "years_experience": 5})
    log(f"[POST /v1/pujari/register] {r.status_code} {r.text[:160]}")
    r = nc.get("/v1/pujari/kyc/status")
    log(f"[GET /v1/pujari/kyc/status] {r.status_code} {r.text[:200]}")

    with open("partner_secondary_result.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(OUT))
    log("DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
