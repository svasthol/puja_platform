"""Dev/staging: reconcile failed TDS accrual intents when ledger accrual already exists.

Default is dry-run. Use --apply to commit.

Examples:
  python scripts/cleanup_tds_accrual_intents.py
  python scripts/cleanup_tds_accrual_intents.py --apply
  python scripts/cleanup_tds_accrual_intents.py --apply --limit 500
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

if sys.platform == "win32":
    # psycopg async cannot use Windows ProactorEventLoop (Python 3.8+ default).
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


def _ensure_path() -> None:
    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))


async def _run(apply: bool, limit: int) -> int:
    _ensure_path()
    from app.db.engine import AsyncSessionLocal
    from app.services.tds_accrual_service import reconcile_failed_accrual_intents
    from sqlalchemy import text

    async with AsyncSessionLocal() as db:
        preview = (
            await db.execute(
                text(
                    """
                    SELECT i.id::text, i.booking_id::text, left(i.last_error, 120)
                    FROM pujari_tds_accrual_intents i
                    WHERE i.status = 'failed'
                      AND EXISTS (
                          SELECT 1 FROM pujari_tds_facilitation_ledger l
                          WHERE l.booking_id = i.booking_id
                            AND l.entry_type = 'accrual'
                      )
                    ORDER BY i.created_at
                    LIMIT :lim
                    """
                ),
                {"lim": limit},
            )
        ).all()

        failed_no_ledger = (
            await db.execute(
                text(
                    """
                    SELECT count(*)::int
                    FROM pujari_tds_accrual_intents
                    WHERE status = 'failed'
                      AND NOT EXISTS (
                          SELECT 1 FROM pujari_tds_facilitation_ledger l
                          WHERE l.booking_id = pujari_tds_accrual_intents.booking_id
                            AND l.entry_type = 'accrual'
                      )
                    """
                )
            )
        ).scalar_one()

    print(f"=== TDS accrual intent cleanup (dry_run={not apply}) ===")
    print(f"Eligible failed intents (ledger accrual exists): {len(preview)} shown (limit {limit})")
    print(f"Failed intents still missing ledger: {failed_no_ledger}")
    for intent_id, booking_id, err in preview[:20]:
        print(f"  intent={intent_id[:8]}... booking={booking_id[:8]}... err={err!r}")
    if len(preview) > 20:
        print(f"  ... and {len(preview) - 20} more")

    if not apply:
        print("\nNo changes made. Pass --apply to mark these intents completed.")
        return 0

    if not preview:
        print("\nNothing to reconcile.")
        return 0

    async with AsyncSessionLocal() as db:
        async with db.begin():
            stats = await reconcile_failed_accrual_intents(db, limit=limit)
    print(f"\nReconciled (completed): {stats['reconciled']}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Mark failed accrual intents completed when ledger row exists"
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Commit updates (default: dry-run only)",
    )
    parser.add_argument("--limit", type=int, default=500, help="Max intents per run")
    args = parser.parse_args()
    if os.environ.get("APP_ENV") == "production" and args.apply:
        print(
            "Refusing --apply when APP_ENV=production. Use staging/dev or run via controlled ops.",
            file=sys.stderr,
        )
        sys.exit(2)
    raise SystemExit(asyncio.run(_run(args.apply, args.limit)))


if __name__ == "__main__":
    main()
