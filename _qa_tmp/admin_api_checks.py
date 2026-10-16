"""QA Phase 5a: admin API checks via TOTP login (resolves Phase 1 admin_bookings 422 question)."""
from __future__ import annotations

import asyncio
import sys

import httpx
from dotenv import load_dotenv

load_dotenv()
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

BASE = "http://127.0.0.1:8000"
OUT: list[str] = []


def log(m):
    OUT.append(str(m)); print(m)


async def _admin_login():
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine
    from app.core.config import get_settings
    from app.core.crypto import decrypt_secret
    from app.core.totp import totp_at
    import redis as redis_lib

    eng = create_async_engine(str(get_settings().DATABASE_URL))
    async with eng.connect() as conn:
        row = (await conn.execute(text(
            "SELECT u.phone, ac.totp_secret_enc FROM admin_credentials ac "
            "JOIN users u ON u.id=ac.user_id WHERE ac.activated_at IS NOT NULL LIMIT 1"))).first()
    await eng.dispose()
    phone, enc = row
    # clear admin login rate limit
    try:
        redis_lib.from_url(str(get_settings().REDIS_URL)).delete(f"admin_login:{phone}")
    except Exception:
        pass
    code = totp_at(decrypt_secret(enc))
    r = httpx.Client(base_url=BASE, timeout=30).post("/v1/admin/auth/login", json={"phone": phone, "code": code})
    r.raise_for_status()
    return r.json()["access_token"]


def main():
    token = asyncio.run(_admin_login())
    log(f"[admin login] OK token_len={len(token)}")
    c = httpx.Client(base_url=BASE, timeout=30, headers={"Authorization": f"Bearer {token}"})

    # a known booking id for detail (most recent)
    import psycopg
    from app.core.config import get_settings
    url = str(get_settings().DATABASE_URL).replace("postgresql+psycopg://", "postgresql://")
    with psycopg.connect(url) as pc:
        bid = pc.execute("SELECT id FROM bookings ORDER BY created_at DESC LIMIT 1").fetchone()[0]
        pujari_id = pc.execute("SELECT id FROM pujaris LIMIT 1").fetchone()[0]

    checks = [
        ("GET", "/v1/admin/bookings", None),
        ("GET", "/v1/admin/bookings?status=confirmed&limit=5", None),
        ("GET", "/v1/admin/bookings?booking_class=advance&limit=3", None),
        ("GET", f"/v1/admin/bookings/{bid}", None),
        ("GET", "/v1/admin/refunds", None),
        ("GET", "/v1/admin/refunds?status=pending&limit=5", None),
        ("GET", "/v1/admin/pujaris?limit=5", None),
        ("GET", f"/v1/admin/pujaris/{pujari_id}", None),
        ("GET", "/v1/admin/kyc?limit=5", None),
        ("GET", "/v1/admin/catalog", None),
        ("GET", "/v1/admin/relationship-managers?limit=5", None),
        ("GET", "/v1/admin/service-areas", None),
        ("GET", "/v1/admin/promos", None),
        ("GET", "/v1/admin/tds/fy-reconcile", None),
        ("GET", "/v1/admin/tds/compliance-backlog", None),
    ]
    for method, path, body in checks:
        try:
            r = c.request(method, path)
            snippet = ""
            if r.status_code >= 400:
                snippet = r.text[:120]
            else:
                j = r.json()
                if isinstance(j, dict):
                    keys = list(j.keys())[:6]
                    n = len(j.get("bookings") or j.get("refunds") or j.get("pujaris") or j.get("items") or j.get("results") or [])
                    snippet = f"keys={keys} list_len={n}"
                elif isinstance(j, list):
                    snippet = f"list_len={len(j)}"
            log(f"[{method} {path}] {r.status_code} {snippet}")
        except Exception as e:
            log(f"[{method} {path}] EXC {type(e).__name__}: {str(e)[:100]}")

    with open("admin_api_result.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(OUT))
    log("DONE")


if __name__ == "__main__":
    main()
