#!/usr/bin/env python3
"""List (and optionally fix) duplicate users that share the same canonical mobile.

Run on staging after deploying canonical phone auth, **before** prod launch.
Does not run automatically — operator must review output.

Usage:
  python scripts/dedupe_users_by_canonical_phone.py           # dry-run (default)
  python scripts/dedupe_users_by_canonical_phone.py --apply   # merge + re-point pujaris

Requires DATABASE_URL (or /etc/mana-guruji/api.env via ENV_FILE).
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
import uuid
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv

load_dotenv()
_env_file = os.environ.get("ENV_FILE", "/etc/mana-guruji/api.env")
if Path(_env_file).is_file():
    load_dotenv(_env_file)

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import get_settings
from app.services.sms_phone import InvalidIndiaPhoneError, canonical_user_phone


def _canonical_safe(raw: str) -> str | None:
    try:
        return canonical_user_phone(raw)
    except InvalidIndiaPhoneError:
        return None


def _score_row(row: dict) -> tuple:
    """Higher = prefer as survivor."""
    verified = 1 if row.get("verification_status") == "verified" else 0
    has_pujari = 1 if row.get("pujari_id") else 0
    return (verified, has_pujari, row["created_at"] or "")


async def _run(*, apply: bool) -> int:
    settings = get_settings()
    engine = create_async_engine(str(settings.DATABASE_URL))
    try:
        async with engine.connect() as conn:
            rows = (
                await conn.execute(
                    text(
                        """
                        SELECT u.id, u.phone, u.full_name, u.created_at,
                               p.id AS pujari_id, p.verification_status
                        FROM users u
                        LEFT JOIN pujaris p ON p.user_id = u.id
                        ORDER BY u.created_at
                        """
                    )
                )
            ).mappings().all()
    finally:
        await engine.dispose()

    buckets: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        canon = _canonical_safe(row["phone"])
        if canon is None:
            print(f"SKIP non-canonicalizable phone user_id={row['id']} phone={row['phone']!r}")
            continue
        entry = dict(row)
        entry["canonical"] = canon
        buckets[canon].append(entry)

    dupes = {k: v for k, v in buckets.items() if len(v) > 1}
    if not dupes:
        print("No duplicate canonical phone groups found.")
        return 0

    print(f"Found {len(dupes)} duplicate phone group(s):\n")
    for canon, group in dupes.items():
        group_sorted = sorted(group, key=_score_row, reverse=True)
        survivor = group_sorted[0]
        orphans = group_sorted[1:]
        print(f"  {canon}:")
        print(f"    KEEP   user={survivor['id']} phone={survivor['phone']} "
              f"pujari={survivor.get('pujari_id')} status={survivor.get('verification_status')}")
        for o in orphans:
            print(f"    MERGE  user={o['id']} phone={o['phone']} "
                  f"pujari={o.get('pujari_id')} status={o.get('verification_status')}")
        print()

    if not apply:
        print("Dry-run only. Re-run with --apply to merge (staging/test data recommended).")
        return 0

    engine = create_async_engine(str(settings.DATABASE_URL))
    try:
        async with engine.begin() as conn:
            for canon, group in dupes.items():
                group_sorted = sorted(group, key=_score_row, reverse=True)
                survivor_id = uuid.UUID(str(group_sorted[0]["id"]))
                for orphan in group_sorted[1:]:
                    orphan_id = uuid.UUID(str(orphan["id"]))
                    orphan_pujari = orphan.get("pujari_id")
                    survivor_pujari = group_sorted[0].get("pujari_id")
                    if orphan_pujari and not survivor_pujari:
                        await conn.execute(
                            text(
                                "UPDATE pujaris SET user_id = :survivor, updated_at = now() "
                                "WHERE id = :pid"
                            ),
                            {"survivor": str(survivor_id), "pid": str(orphan_pujari)},
                        )
                    elif orphan_pujari and survivor_pujari:
                        print(
                            f"WARN both have pujaris for {canon}: "
                            f"survivor_pujari={survivor_pujari} orphan_pujari={orphan_pujari} "
                            "— manual merge required; skipping orphan pujari move"
                        )
                    await conn.execute(
                        text("UPDATE users SET is_active = false, updated_at = now() WHERE id = :id"),
                        {"id": str(orphan_id)},
                    )
                await conn.execute(
                    text("UPDATE users SET phone = :ph, updated_at = now() WHERE id = :id"),
                    {"ph": canon, "id": str(survivor_id)},
                )
    finally:
        await engine.dispose()

    print("Apply complete. Review inactive users and run admin partner list.")
    return 0


def main() -> None:
    p = argparse.ArgumentParser(description="Dedupe users by canonical +91 phone.")
    p.add_argument(
        "--apply",
        action="store_true",
        help="Merge duplicate groups (deactivate orphan users; re-point pujari when safe).",
    )
    args = p.parse_args()
    raise SystemExit(asyncio.run(_run(apply=args.apply)))


if __name__ == "__main__":
    main()
