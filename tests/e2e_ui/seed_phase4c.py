#!/usr/bin/env python3
"""
TEST ONLY — Phase 4C manual QA fixtures.

Creates:
  - One in_progress booking (advance_balance) + success payment → dispute + money read
  - One confirmed booking → dispute should fail (409)

Run after ensure_seed.py:
  python tests/e2e_ui/ensure_seed.py
  python tests/e2e_ui/seed_phase4c.py
"""
from __future__ import annotations

import asyncio
import sys
import uuid
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

CUSTOMER = "aaaaaaaa-0000-0000-0000-000000000001"
PUJARI_USER = "bbbbbbbb-0000-0000-0000-000000000001"
ADDRESS = "dddddddd-0000-0000-0000-000000000001"
PUJA = "11111111-1111-1111-1111-111111111111"

IN_PROGRESS_ID = "cccccccc-0000-0000-0000-000000000004"
CONFIRMED_ID = "cccccccc-0000-0000-0000-000000000005"


async def main() -> None:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.core.config import get_settings

    engine = create_async_engine(str(get_settings().DATABASE_URL))
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async with maker() as s:
        async with s.begin():
            pujari_id = (
                await s.execute(
                    text("SELECT id FROM pujaris WHERE user_id = :uid"),
                    {"uid": PUJARI_USER},
                )
            ).scalar_one()

            # in_progress — for A-DISPUTE + A-MONEY-READ
            await s.execute(
                text(
                    """
                    INSERT INTO bookings (
                        id, user_id, pujari_id, intended_pujari_id, puja_id, address_id, status_id,
                        cancellation_policy_id, scheduled_date, scheduled_time, duration_minutes,
                        total_amount, amount_due_online, amount_due_offline, payment_mode, paid_at,
                        dispatch_mode, created_at, updated_at
                    )
                    SELECT
                        :bid, :uid, :pid, :pid, :puja, :addr, st.id,
                        (SELECT id FROM cancellation_policies WHERE name='standard'),
                        CURRENT_DATE + 1, '10:00:00'::time, 90,
                        2100, 250, 1850, 'advance_balance', now(),
                        'broadcast', now(), now()
                    FROM status_types st
                    WHERE st.domain = 'booking' AND st.code = 'in_progress'
                    ON CONFLICT (id) DO UPDATE SET
                        status_id = EXCLUDED.status_id,
                        payment_mode = EXCLUDED.payment_mode,
                        amount_due_online = EXCLUDED.amount_due_online,
                        amount_due_offline = EXCLUDED.amount_due_offline,
                        updated_at = now()
                    """
                ),
                {
                    "bid": IN_PROGRESS_ID,
                    "uid": CUSTOMER,
                    "pid": str(pujari_id),
                    "puja": PUJA,
                    "addr": ADDRESS,
                },
            )

            pay_id = "eeeeeeee-0000-0000-0000-000000000004"
            await s.execute(
                text(
                    """
                    INSERT INTO payments (
                        id, booking_id, amount, idempotency_key, gateway_txn_id, status, created_at
                    ) VALUES (
                        :pid, :bid, 250, :key, :gw, 'success', now()
                    )
                    ON CONFLICT (id) DO UPDATE SET status = 'success', amount = 250
                    """
                ),
                {
                    "pid": pay_id,
                    "bid": IN_PROGRESS_ID,
                    "key": f"phase4c-{IN_PROGRESS_ID}",
                    "gw": f"pay_phase4c_{IN_PROGRESS_ID[:8]}",
                },
            )

            # confirmed — dispute must be blocked
            await s.execute(
                text(
                    """
                    INSERT INTO bookings (
                        id, user_id, pujari_id, intended_pujari_id, puja_id, address_id, status_id,
                        cancellation_policy_id, scheduled_date, scheduled_time, duration_minutes,
                        total_amount, amount_due_online, amount_due_offline, payment_mode, paid_at,
                        dispatch_mode, created_at, updated_at
                    )
                    SELECT
                        :bid, :uid, :pid, :pid, :puja, :addr, st.id,
                        (SELECT id FROM cancellation_policies WHERE name='standard'),
                        CURRENT_DATE + 2, '11:00:00'::time, 90,
                        2100, 2100, 0, 'full_online', now(),
                        'broadcast', now(), now()
                    FROM status_types st
                    WHERE st.domain = 'booking' AND st.code = 'confirmed'
                    ON CONFLICT (id) DO UPDATE SET
                        status_id = EXCLUDED.status_id,
                        updated_at = now()
                    """
                ),
                {
                    "bid": CONFIRMED_ID,
                    "uid": CUSTOMER,
                    "pid": str(pujari_id),
                    "puja": PUJA,
                    "addr": ADDRESS,
                },
            )

    await engine.dispose()

    print("Phase 4C seed OK.")
    print()
    print("Use these in Admin UI -> Bookings:")
    print(f"  IN_PROGRESS (dispute + money): {IN_PROGRESS_ID}")
    print(f"  CONFIRMED (dispute blocked):   {CONFIRMED_ID}")
    print()
    print("Customer phone for search: +910000000001")
    print("Direct URLs (after login):")
    print(f"  http://localhost:3000/console/bookings/{IN_PROGRESS_ID}")
    print(f"  http://localhost:3000/console/bookings/{CONFIRMED_ID}")
    print(f"  http://localhost:3000/console/promos")


if __name__ == "__main__":
    asyncio.run(main())
