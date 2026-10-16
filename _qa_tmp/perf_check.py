"""QA Phase 6: perf + concurrency measurements."""
from __future__ import annotations

import asyncio
import statistics
import sys
import time

import httpx
from dotenv import load_dotenv

load_dotenv()
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

BASE = "http://127.0.0.1:8000"
OUT = []


def log(m):
    OUT.append(str(m)); print(m)


def _clear_rl(phone):
    import redis as redis_lib
    from app.core.config import get_settings
    redis_lib.from_url(str(get_settings().REDIS_URL)).delete(f"otp_req:{phone}")


def login(phone, ctx):
    _clear_rl(phone)
    with httpx.Client(base_url=BASE, timeout=30) as c:
        otp = c.post("/v1/auth/otp/request", json={"phone": phone}).json()["otp_dev_only"]
        return c.post("/v1/auth/otp/verify", json={"phone": phone, "otp": otp, "app_context": ctx}).json()["access_token"]


def latency(c, path, n=25):
    xs = []
    for _ in range(n):
        t = time.perf_counter()
        r = c.get(path)
        xs.append((time.perf_counter() - t) * 1000)
        if r.status_code != 200:
            return f"{path}: status={r.status_code}"
    xs.sort()
    p50 = statistics.median(xs)
    p95 = xs[int(len(xs) * 0.95) - 1]
    return f"{path}: n={n} p50={p50:.0f}ms p95={p95:.0f}ms max={max(xs):.0f}ms"


def main():
    import customer_e2e
    info = asyncio.run(customer_e2e.setup())
    token = login("+919300000031", "customer")
    c = httpx.Client(base_url=BASE, timeout=30, headers={"Authorization": f"Bearer {token}"})

    log("== HOT ENDPOINT LATENCY (sequential, warm) ==")
    log(latency(c, "/v1/pujas?limit=20"))
    log(latency(c, f"/v1/pujas/{info['puja_id']}"))
    log(latency(c, f"/v1/checkout/quote?puja_id={info['puja_id']}"))

    # EXPLAIN ANALYZE equivalent: count queries for catalog via server timing is hard here;
    # measure concurrent catalog load for pool behaviour
    log("\n== CONCURRENT CATALOG LOAD (20 parallel GET /v1/pujas) ==")

    async def hammer():
        async with httpx.AsyncClient(base_url=BASE, timeout=30, headers={"Authorization": f"Bearer {token}"}) as ac:
            t = time.perf_counter()
            rs = await asyncio.gather(*[ac.get("/v1/pujas?limit=20") for _ in range(20)], return_exceptions=True)
            dur = (time.perf_counter() - t) * 1000
            codes = [r.status_code if hasattr(r, "status_code") else str(type(r).__name__) for r in rs]
            ok = sum(1 for x in codes if x == 200)
            return dur, ok, codes
    dur, ok, codes = asyncio.run(hammer())
    log(f"20 parallel: total={dur:.0f}ms ok={ok}/20 nonzero_codes={set(c2 for c2 in codes if c2!=200)}")

    # idle-in-transaction + pool snapshot
    log("\n== DB ACTIVITY SNAPSHOT ==")
    import psycopg
    from app.core.config import get_settings
    url = str(get_settings().DATABASE_URL).replace("postgresql+psycopg://", "postgresql://")
    with psycopg.connect(url) as pc:
        rows = pc.execute("SELECT state, count(*) FROM pg_stat_activity WHERE datname='Mana_Guruji' GROUP BY state").fetchall()
        log(f"pg_stat_activity by state: {rows}")
        idle_tx = pc.execute("SELECT count(*) FROM pg_stat_activity WHERE datname='Mana_Guruji' AND state='idle in transaction'").fetchone()[0]
        log(f"idle_in_transaction: {idle_tx}")
        waits = pc.execute("SELECT count(*) FROM pg_locks WHERE NOT granted").fetchone()[0]
        log(f"ungranted_locks(waiters): {waits}")
        longtx = pc.execute("SELECT count(*) FROM pg_stat_activity WHERE datname='Mana_Guruji' AND xact_start < now() - interval '5 seconds'").fetchone()[0]
        log(f"transactions_open_gt_5s: {longtx}")

    with open("perf_result.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(OUT))
    log("DONE")


if __name__ == "__main__":
    main()
