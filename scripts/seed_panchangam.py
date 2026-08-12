"""One-shot panchangam cache seed for dev (vendor :3001 → panchangam_daily).

Usage (venv active; engine on :3001):
    python scripts/seed_panchangam.py
    python scripts/seed_panchangam.py --date 2026-07-15 --locale te
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT))

from app.services.panchangam import today_ist  # noqa: E402
from app.workers.panchangam import fetch_and_cache_panchangam  # noqa: E402
from app.workers.sweep import get_connection  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed panchangam_daily from vendor")
    parser.add_argument("--city", default="Hyderabad")
    parser.add_argument(
        "--date",
        default=None,
        help="YYYY-MM-DD (default: today IST)",
    )
    parser.add_argument("--locale", default="te", choices=["te", "en"])
    parser.add_argument(
        "--both-locales",
        action="store_true",
        help="Seed te and en for the date",
    )
    args = parser.parse_args()
    pdate = dt.date.fromisoformat(args.date) if args.date else today_ist()
    locales = ("te", "en") if args.both_locales else (args.locale,)

    conn = get_connection()
    ok_any = False
    try:
        for locale in locales:
            ok = fetch_and_cache_panchangam(
                conn,
                city=args.city,
                panchang_date=pdate,
                locale=locale,
            )
            if ok:
                ok_any = True
                print(f"cached {args.city} {pdate.isoformat()} locale={locale}")
    finally:
        conn.close()

    if not ok_any:
        print(
            "fetch failed — check PANCHANGAM_VENDOR_URL in .env and "
            "telugu-panchangam-app on :3001",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
