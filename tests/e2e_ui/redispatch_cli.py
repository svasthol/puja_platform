#!/usr/bin/env python3
"""TEST ONLY — re-dispatch one booking from the CLI."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT.parents[1] / ".env")
sys.path.insert(0, str(ROOT))

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


async def _partner_pujari_id() -> str:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    from app.core.config import get_settings

    engine = create_async_engine(str(get_settings().DATABASE_URL))
    async with engine.connect() as conn:
        pid = (
            await conn.execute(
                text(
                    "SELECT p.id FROM pujaris p JOIN users u ON u.id = p.user_id "
                    "WHERE u.phone = '+910000000011'"
                )
            )
        ).scalar_one()
    await engine.dispose()
    return str(pid)


def main() -> None:
    booking_id = sys.argv[1] if len(sys.argv) > 1 else ""
    if not booking_id:
        print("Usage: python tests/e2e_ui/redispatch_cli.py <booking_id>")
        sys.exit(1)

    import redis as redis_lib

    from app.core.config import get_settings
    from test_db import redispatch_booking

    pid = asyncio.run(_partner_pujari_id())
    r = redis_lib.from_url(str(get_settings().REDIS_URL))
    r.set(f"presence:{pid}", "1", ex=120)
    print(f"presence:{pid} set (120s)")

    result = redispatch_booking(booking_id)
    print("dispatch result:", result)


if __name__ == "__main__":
    main()
