"""QA/dev: reset KYC state for a partner by phone suffix so onboarding can be repeated.

Does NOT delete the pujari row or user account.

Usage:
  python scripts/reset_partner_kyc_by_phone.py 7675834207
  python scripts/reset_partner_kyc_by_phone.py 7675834207 --apply
"""
from __future__ import annotations

import argparse
import os
import sys

import psycopg

def _normalize_dsn(url: str) -> str:
    return url.replace("postgresql+psycopg://", "postgresql://")


def _require_dsn(explicit: str | None) -> str:
    raw = (explicit or os.environ.get("DATABASE_URL") or "").strip()
    if not raw:
        print(
            "Set DATABASE_URL in the environment or pass --dsn "
            "(no default DSN — avoids committing credentials).",
            file=sys.stderr,
        )
        sys.exit(2)
    return _normalize_dsn(raw)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("phone_suffix", help="Last 10 digits or unique phone fragment")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Execute reset (default is dry-run preview only)",
    )
    parser.add_argument(
        "--dsn",
        default=None,
        help="PostgreSQL DSN (default: DATABASE_URL from environment)",
    )
    args = parser.parse_args()
    dsn = _require_dsn(args.dsn)

    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT pj.id, u.phone, pj.verification_status
                FROM pujaris pj
                JOIN users u ON u.id = pj.user_id
                WHERE u.phone LIKE %s
                """,
                (f"%{args.phone_suffix}%",),
            )
            row = cur.fetchone()
            if row is None:
                print("No pujari found for phone fragment:", args.phone_suffix)
                return 1
            pujari_id, phone, v_status = row
            print(f"pujari_id={pujari_id} phone={phone} verification_status={v_status}")

            cur.execute(
                "SELECT id, kind, status FROM kyc_verification_requests WHERE pujari_id = %s",
                (str(pujari_id),),
            )
            print("kyc_verification_requests:", cur.fetchall())
            cur.execute(
                """
                SELECT id, doc_type, status
                FROM pujari_documents
                WHERE pujari_id = %s AND is_current IS TRUE
                """,
                (str(pujari_id),),
            )
            print("pujari_documents (current):", cur.fetchall())

            if not args.apply:
                print("\nDry-run only. Re-run with --apply to reset KYC for this partner.")
                return 0

            cur.execute(
                """
                DELETE FROM kyc_consents
                WHERE request_id IN (
                    SELECT id FROM kyc_verification_requests WHERE pujari_id = %s
                )
                """,
                (str(pujari_id),),
            )
            cur.execute(
                "DELETE FROM kyc_verification_requests WHERE pujari_id = %s",
                (str(pujari_id),),
            )
            cur.execute(
                "DELETE FROM pujari_documents WHERE pujari_id = %s",
                (str(pujari_id),),
            )
            cur.execute(
                "DELETE FROM kyc_identity_registry WHERE pujari_id = %s::uuid",
                (str(pujari_id),),
            )
            cur.execute(
                """
                UPDATE pujaris
                SET verification_status = 'pending',
                    pan_hash = NULL,
                    pan_status = 'unverified',
                    entity_type = NULL,
                    customer_profile_photo_doc_id = NULL,
                    updated_at = now()
                WHERE id = %s
                """,
                (str(pujari_id),),
            )
        conn.commit()
    print("KYC reset complete. Partner can sign in and run onboarding again.")
    print("Tip: clear app data or sign out/in; Redis consent URLs expire on their own.")
    return 0


if __name__ == "__main__":
    sys.exit(main())