"""
Production-style E2E verification for P-SWEEP-RELIABILITY.
Run: python scripts/verify_sweep_e2e.py
"""
from __future__ import annotations

import json
import sys
import time
import uuid
from pathlib import Path

import httpx
import psycopg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

sys.path.insert(0, str(ROOT))

from app.core.config import get_settings
from app.services.booking_gate import BookingGateSettings, assert_booking_gate
from app.workers.sweep import exhaust_past_dispatch_deadline, get_connection, run_sweep
from app.workers.sweep_heartbeat import SWEEP_STALE_SECONDS, sweep_age_seconds
from app.workers.redis_sync import get_sync_redis

CUSTOMER = "aaaaaaaa-0000-0000-0000-000000000001"
PUJA = "11111111-1111-1111-1111-111111111111"
ADDRESS = "dddddddd-0000-0000-0000-000000000001"

PASS = 0
FAIL = 0


def ok(name: str, detail: str = "") -> None:
    global PASS
    PASS += 1
    print(f"  PASS  {name}" + (f" - {detail}" if detail else ""))


def bad(name: str, detail: str) -> None:
    global FAIL
    FAIL += 1
    print(f"  FAIL  {name} - {detail}")


def check_migration_024(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT 1 FROM information_schema.tables
            WHERE table_schema='public' AND table_name='worker_heartbeats'
            """
        )
        if cur.fetchone():
            ok("migration_024", "worker_heartbeats table exists")
        else:
            bad("migration_024", "table missing — run scripts/apply_migration_024.py")


def check_health_api() -> None:
    try:
        r = httpx.get("http://127.0.0.1:8000/health", timeout=10.0)
        data = r.json()
    except Exception as exc:
        bad("health_api", f"unreachable: {exc}")
        return
    if r.status_code != 200:
        bad("health_api", f"status {r.status_code}")
        return
    if data.get("db") and data.get("redis"):
        ok("health_api", f"db+redis ok, env={data.get('env')}")
    else:
        bad("health_api", json.dumps(data))
    age = data.get("sweep_age_seconds")
    stale = data.get("sweep_stale")
    if age is not None and stale is False:
        ok("sweep_heartbeat_live", f"age={age:.1f}s (threshold {SWEEP_STALE_SECONDS}s)")
    elif age is None:
        bad("sweep_heartbeat_live", "sweep_age_seconds missing — beat never completed a sweep?")
    else:
        bad("sweep_heartbeat_live", f"stale=true age={age}")


def check_redis_and_celery() -> None:
    try:
        r = get_sync_redis()
        r.ping()
        ok("redis_ping")
    except Exception as exc:
        bad("redis_ping", str(exc))
    import subprocess

    proc = subprocess.run(
        [
            str(ROOT / ".venv" / "Scripts" / "celery.exe"),
            "-A",
            "app.workers.celery_app",
            "inspect",
            "ping",
        ],
        capture_output=True,
        text=True,
        cwd=ROOT,
        timeout=30,
    )
    if proc.returncode == 0 and "pong" in proc.stdout.lower():
        ok("celery_worker", proc.stdout.strip().split("\n")[-1])
    else:
        bad("celery_worker", proc.stderr or proc.stdout or "no pong")


def check_past_slot_gate() -> None:
    import datetime as dt

    from fastapi import HTTPException

    settings = BookingGateSettings()
    now = dt.datetime.now(dt.UTC)
    try:
        assert_booking_gate(
            now.astimezone().date(),
            dt.time(0, 1),
            settings,
            now=now - dt.timedelta(hours=1),
        )
        bad("past_slot_gate", "expected SLOT_IN_PAST 422")
    except HTTPException as exc:
        if exc.detail.get("code") == "SLOT_IN_PAST":
            ok("past_slot_gate", "422 SLOT_IN_PAST")
        else:
            bad("past_slot_gate", str(exc.detail))


def check_deadline_exhaust_e2e(conn) -> None:
    """Insert a real past-deadline booking and verify exhaust flips it."""
    bid = str(uuid.uuid4())
    slot_h = 8 + (int(bid.replace("-", "")[:4], 16) % 12)
    slot_m = int(bid.replace("-", "")[4:8], 16) % 60
    slot_time = f"{slot_h:02d}:{slot_m:02d}:00"
    import datetime as dt

    slot_date = (dt.date.today() - dt.timedelta(days=1)).isoformat()
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO bookings (
                id, user_id, puja_id, address_id, status_id, cancellation_policy_id,
                scheduled_date, scheduled_time, duration_minutes, total_amount,
                amount_due_online, amount_due_offline, payment_mode, paid_at,
                dispatch_mode, booking_class, created_at, updated_at
            ) VALUES (
                %s, %s, %s, %s,
                (SELECT id FROM status_types WHERE domain='booking' AND code='requested'),
                (SELECT id FROM cancellation_policies WHERE name='standard'),
                %s, %s::time, 90, 2100, 2100, 0, 'full_online', now(), 'broadcast',
                'instant', now(), now()
            )
            """,
            (bid, CUSTOMER, PUJA, ADDRESS, slot_date, slot_time),
        )
        cur.execute(
            """
            INSERT INTO booking_dispatch_state (
                booking_id, dispatch_starts_at, dispatch_deadline, round, max_rounds
            ) VALUES (%s, now() - interval '3 hours', now() - interval '1 minute', 3, 4)
            """,
            (bid,),
        )
    conn.commit()

    exhausted = exhaust_past_dispatch_deadline(conn)
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT st.code, bds.exhausted_at IS NOT NULL
            FROM bookings b
            JOIN status_types st ON st.id = b.status_id
            LEFT JOIN booking_dispatch_state bds ON bds.booking_id = b.id
            WHERE b.id = %s
            """,
            (bid,),
        )
        row = cur.fetchone()
    if bid in exhausted and row and row[0] == "failed_no_pujari" and row[1]:
        ok("deadline_exhaust_e2e", f"booking {bid[:8]} -> failed_no_pujari")
    else:
        bad("deadline_exhaust_e2e", f"exhausted={exhausted} row={row}")


def check_sweep_updates_heartbeat(conn) -> None:
    from app.workers.sweep_heartbeat import SWEEP_WORKER_NAME, record_worker_heartbeat

    summary = run_sweep(conn, redis_client=get_sync_redis())
    record_worker_heartbeat(conn, SWEEP_WORKER_NAME, summary)
    after = sweep_age_seconds(conn)
    if summary.get("duration_ms", 0) > 0:
        ok("sweep_run", f"duration_ms={summary['duration_ms']}")
    else:
        bad("sweep_run", str(summary))
    if after is not None and after <= 2.0:
        ok("heartbeat_fresh_after_sweep", f"age={after:.2f}s")
    else:
        bad("heartbeat_fresh_after_sweep", f"age={after}")


def check_no_stuck_past_deadline(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT count(*) FROM bookings b
            JOIN booking_dispatch_state bds ON bds.booking_id = b.id
            JOIN status_types st ON st.id = b.status_id
            WHERE st.domain='booking' AND st.code='requested'
              AND b.pujari_id IS NULL AND b.cancelled_at IS NULL
              AND bds.dispatch_deadline IS NOT NULL
              AND bds.dispatch_deadline <= now()
            """
        )
        n = cur.fetchone()[0]
    if n == 0:
        ok("no_stuck_past_deadline", "0 requested bookings past deadline")
    else:
        bad("no_stuck_past_deadline", f"{n} still stuck — is beat running?")


def main() -> None:
    print("=== P-SWEEP-RELIABILITY E2E verification ===\n")
    settings = get_settings()
    url = str(settings.DATABASE_URL).replace("postgresql+psycopg://", "postgresql://")
    conn = psycopg.connect(url)

    print("[1] Infrastructure")
    check_migration_024(conn)
    check_redis_and_celery()
    check_health_api()

    print("\n[2] Business rules")
    check_past_slot_gate()

    print("\n[3] Live deadline exhaust")
    check_deadline_exhaust_e2e(conn)
    check_no_stuck_past_deadline(conn)

    print("\n[4] Sweep + heartbeat")
    check_sweep_updates_heartbeat(conn)

    conn.close()
    print(f"\n=== Result: {PASS} passed, {FAIL} failed ===")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
