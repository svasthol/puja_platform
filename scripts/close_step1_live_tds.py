"""
Close Sprint 2 Step 1 — live partner balance collection + TDS ledger proof.

Runs the same path as the partner app:
  align slot (if needed) → start → confirm-balance-collected → verify ledger.

Usage:
  python scripts/close_step1_live_tds.py --phone +919603059878
  python scripts/close_step1_live_tds.py --booking-id f95a920e-dbe4-413f-a6fd-2c44ff9de0ea
  python scripts/close_step1_live_tds.py --phone +919603059878 --dry-run
"""
from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import os
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
import uuid
import zoneinfo
from decimal import Decimal
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.schemas.booking import BalanceCollected
from app.api.v1.endpoints import service_lifecycle as lifecycle_ep
from app.core.dependencies import Principal


def _db_url() -> str:
    url = os.environ.get(
        "DATABASE_URL", "postgresql+psycopg://postgres@127.0.0.1:5432/Mana_Guruji"
    )
    return url.replace("postgresql://", "postgresql+psycopg://").replace(
        "postgresql+asyncpg://", "postgresql+psycopg://"
    )


async def _find_pujari(session, phone: str) -> dict:
    row = (
        await session.execute(
            text(
                """
                SELECT p.id::text AS pujari_id, u.id::text AS user_id, u.phone,
                       p.entity_type, p.pan_hash IS NOT NULL AS pan_on_file
                FROM pujaris p
                JOIN users u ON u.id = p.user_id
                WHERE u.phone = :ph OR u.phone LIKE :suffix
                LIMIT 1
                """
            ),
            {"ph": phone, "suffix": f"%{phone.lstrip('+')[-10:]}"},
        )
    ).mappings().first()
    if row is None:
        raise SystemExit(f"Pujari not found for phone {phone}")
    return dict(row)


async def _pick_booking(session, pujari_id: str, booking_id: str | None) -> dict:
    if booking_id:
        row = (
            await session.execute(
                text(
                    """
                    SELECT b.id::text AS booking_id, st.code AS status,
                           b.payment_mode, b.amount_due_offline, b.balance_collected_at,
                           b.scheduled_date, b.scheduled_time::text AS scheduled_time
                    FROM bookings b
                    JOIN status_types st ON st.id = b.status_id
                    WHERE b.id = :bid AND b.pujari_id = :pid
                    """
                ),
                {"bid": booking_id, "pid": pujari_id},
            )
        ).mappings().first()
        if row is None:
            raise SystemExit(f"Booking {booking_id} not found for pujari.")
        return dict(row)

    row = (
        await session.execute(
            text(
                """
                SELECT b.id::text AS booking_id, st.code AS status,
                       b.payment_mode, b.amount_due_offline, b.balance_collected_at,
                       b.scheduled_date, b.scheduled_time::text AS scheduled_time
                FROM bookings b
                JOIN status_types st ON st.id = b.status_id
                WHERE b.pujari_id = :pid
                  AND st.code IN ('confirmed', 'in_progress')
                  AND b.payment_mode IN ('booking_fee', 'advance_balance')
                  AND b.amount_due_offline > 0
                  AND b.balance_collected_at IS NULL
                ORDER BY b.created_at DESC
                LIMIT 1
                """
            ),
            {"pid": pujari_id},
        )
    ).mappings().first()
    if row is None:
        raise SystemExit("No eligible booking (confirmed/in_progress, offline due, not collected).")
    return dict(row)


async def _align_slot_for_start(session, booking_id: str) -> None:
    """Move scheduled slot to now (IST) so partner can tap Start (±60 min gate)."""
    tz = zoneinfo.ZoneInfo(get_settings().PLATFORM_TIMEZONE)
    now = dt.datetime.now(dt.UTC).astimezone(tz)
    slot_time = now.time().replace(second=0, microsecond=0)
    await session.execute(
        text(
            """
            UPDATE bookings
            SET scheduled_date = :d, scheduled_time = CAST(:t AS time), updated_at = now()
            WHERE id = :bid
            """
        ),
        {"bid": booking_id, "d": now.date(), "t": slot_time.isoformat()},
    )


async def _ledger_count(session, pujari_id: str, booking_id: str) -> int:
    return int(
        (
            await session.execute(
                text(
                    """
                    SELECT count(*) FROM pujari_tds_facilitation_ledger
                    WHERE pujari_id = :pid AND booking_id = :bid AND entry_type = 'accrual'
                    """
                ),
                {"pid": pujari_id, "bid": booking_id},
            )
        ).scalar_one()
    )


async def run(
    *,
    phone: str,
    booking_id: str | None,
    method: str,
    dry_run: bool,
    skip_align: bool,
) -> int:
    settings = get_settings()
    if not settings.TDS_ACCRUAL_ENABLED:
        print("WARN: TDS_ACCRUAL_ENABLED=false — accrual will be skipped until enabled.")

    engine = create_async_engine(_db_url(), echo=False)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async with maker() as read_session:
        pujari = await _find_pujari(read_session, phone)
        booking = await _pick_booking(read_session, pujari["pujari_id"], booking_id)
        bid = booking["booking_id"]

        print("=== Step 1 close — partner TDS accrual ===")
        print(f"  pujari: {pujari['phone']} ({pujari['pujari_id'][:8]}…)")
        print(f"  entity_type: {pujari['entity_type']}  pan_on_file: {pujari['pan_on_file']}")
        print(f"  booking: {bid}")
        print(f"  status: {booking['status']}  mode: {booking['payment_mode']}")
        print(f"  offline_due: {booking['amount_due_offline']}")
        print(f"  slot: {booking['scheduled_date']} {booking['scheduled_time']}")

        if not pujari["entity_type"]:
            raise SystemExit("Pujari entity_type missing — set via PATCH /admin/pujaris/{id}/tax-compliance")
        if not pujari["pan_on_file"]:
            print("WARN: PAN not on file — TDS will accrue at 5% if enabled.")

        before = await _ledger_count(read_session, pujari["pujari_id"], bid)
        print(f"  ledger accrual rows (before): {before}")

    if dry_run:
        print("\nDRY RUN — no changes.")
        return 0

    principal = Principal(
        user_id=uuid.UUID(pujari["user_id"]),
        app_context="pujari",
        roles=("pujari",),
    )

    async with maker() as session, session.begin():
        if booking["status"] == "confirmed" and not skip_align:
            await _align_slot_for_start(session, bid)
            print("  aligned slot to now (IST) for start window")

        status_row = (
            await session.execute(
                text(
                    """
                    SELECT st.code AS status
                    FROM bookings b
                    JOIN status_types st ON st.id = b.status_id
                    WHERE b.id = :bid
                    """
                ),
                {"bid": bid},
            )
        ).mappings().first()

        if status_row and status_row["status"] == "confirmed":
            await lifecycle_ep.start(uuid.UUID(bid), principal, session)
            print("  started service -> in_progress")

        collected = (
            await session.execute(
                text("SELECT balance_collected_at FROM bookings WHERE id = :bid"),
                {"bid": bid},
            )
        ).scalar_one_or_none()

        if collected is None:
            resp = await lifecycle_ep.confirm_balance(
                uuid.UUID(bid),
                BalanceCollected(method=method),
                principal,
                session,
            )
            print(f"  balance recorded: status={resp.status} amount={resp.amount}")
            if resp.tds:
                print(
                    f"  TDS: skipped={resp.tds.skipped} rate={resp.tds.tds_rate} "
                    f"amount={resp.tds.tds_amount} fy_after={resp.tds.fy_gross_after}"
                )
        else:
            print("  balance already recorded — skipped collection")

    async with maker() as verify:
        after = await _ledger_count(verify, pujari["pujari_id"], bid)
        fy = (
            await verify.execute(
                text(
                    """
                    SELECT gross_facilitation, tds_accrued
                    FROM pujari_tax_year
                    WHERE pujari_id = :pid
                    ORDER BY fy_start DESC LIMIT 1
                    """
                ),
                {"pid": pujari["pujari_id"]},
            )
        ).mappings().first()

    print(f"\n  ledger accrual rows (after): {after}")
    if fy:
        print(f"  FY gross_facilitation: {fy['gross_facilitation']}  tds_accrued: {fy['tds_accrued']}")

    if after > before:
        print("\nOK Step 1 CLOSED — TDS accrual ledger row created.")
        return 0
    if after > 0 and before > 0:
        print("\nOK Step 1 already closed — idempotent accrual exists.")
        return 0
    print("\nFAIL No new ledger row — check TDS_ACCRUAL_ENABLED and pujari compliance.")
    return 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Close Sprint 2 Step 1 (live TDS accrual).")
    parser.add_argument("--phone", default="+919603059878", help="Partner phone (E.164)")
    parser.add_argument("--booking-id", default=None, help="Specific booking UUID")
    parser.add_argument("--method", choices=("cash", "upi_direct"), default="cash")
    parser.add_argument("--dry-run", action="store_true", help="Inspect only")
    parser.add_argument(
        "--skip-align",
        action="store_true",
        help="Do not move scheduled slot (booking must already be in start window)",
    )
    args = parser.parse_args()
    raise SystemExit(
        asyncio.run(
            run(
                phone=args.phone,
                booking_id=args.booking_id,
                method=args.method,
                dry_run=args.dry_run,
                skip_align=args.skip_align,
            )
        )
    )


if __name__ == "__main__":
    main()
