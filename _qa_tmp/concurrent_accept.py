"""QA Phase 6: concurrency correctness - N concurrent accepts of one offer => exactly one winner."""
from __future__ import annotations

import asyncio
import sys
import time

import httpx
from dotenv import load_dotenv

load_dotenv()
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

BASE = "http://127.0.0.1:8000"


def main():
    import customer_e2e, partner_e2e
    info = asyncio.run(customer_e2e.setup())
    import redis as redis_lib
    from app.core.config import get_settings
    redis_lib.from_url(str(get_settings().REDIS_URL)).set(f"presence:{info['pujari_id']}", "1", ex=600)

    ch = {"Authorization": f"Bearer {partner_e2e.login('+919300000031','customer')}"}
    ph_token = partner_e2e.login("+919300000032", "pujari")
    ph = {"Authorization": f"Bearer {ph_token}"}

    bid, _ = partner_e2e.create_paid_booking(info, ch)
    from app.workers.dispatch import broadcast_booking
    time.sleep(1); broadcast_booking(bid)
    pc = httpx.Client(base_url=BASE, timeout=30, headers=ph)
    offers = pc.get("/v1/offers").json().get("offers", [])
    mine = [o for o in offers if o["booking_id"] == bid]
    if not mine:
        print("NO OFFER - cannot run race test"); return
    aid = mine[0]["assignment_id"]
    print(f"assignment={aid}")

    async def race():
        async with httpx.AsyncClient(base_url=BASE, timeout=30, headers=ph) as ac:
            rs = await asyncio.gather(*[ac.post(f"/v1/offers/{aid}/accept") for _ in range(6)], return_exceptions=True)
            return [r.status_code if hasattr(r, "status_code") else str(type(r).__name__) for r in rs]
    codes = asyncio.run(race())
    wins = sum(1 for c in codes if c == 200)
    print(f"6 concurrent accepts -> codes={codes} wins_200={wins}")

    # DB: exactly one accepted assignment, booking confirmed once
    rows = partner_e2e.dbexec(
        "SELECT st.code, count(*) FROM booking_assignments ba JOIN status_types st ON st.id=ba.status_id "
        "WHERE ba.booking_id=%s GROUP BY st.code", (bid,), fetch=True)
    bstat = partner_e2e.dbexec("SELECT st.code, b.pujari_id FROM bookings b JOIN status_types st ON st.id=b.status_id WHERE b.id=%s", (bid,), fetch=True)
    print(f"assignment_states={rows} booking={bstat[0][0]} pujari_set={bstat[0][1] is not None}")
    print("RESULT:", "PASS exactly-one-winner" if wins == 1 and bstat[0][0] == "confirmed" else "CHECK")


if __name__ == "__main__":
    main()
