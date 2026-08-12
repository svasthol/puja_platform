"""Bootstrap the FIRST admin — closes the P-ADMIN-SEED cold-start lockout.

Migrations seed the `roles` catalogue but MUST NOT seed a specific admin (that
would bake a deployment secret into version-controlled SQL). This script is the
env-keyed bootstrap: it promotes one real user to `admin` and provisions their
TOTP credential, printing the provisioning URI/secret exactly once.

After this, every other admin is onboarded through the API by an existing admin
(POST /v1/admin/users/{id}/roles + /credential) — no SMS, no self-enrolment race.

Prerequisites:
  - DATABASE_URL, TOTP_ENC_KEYS set in the environment / .env
  - migration 009 applied (roles catalogue + admin_credentials table)

Usage:
  python scripts/bootstrap_admin.py --phone +919111111100 --name "Ops Admin"
  ADMIN_PHONE=+919111111100 python scripts/bootstrap_admin.py
  python scripts/bootstrap_admin.py --phone +91... --reset   # rotate a lost secret
"""
from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


async def _run(phone: str, name: str, reset: bool) -> int:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    from app.core import totp
    from app.core.config import get_settings
    from app.core.crypto import TotpKeyUnavailable, current_key_version, encrypt_secret

    settings = get_settings()

    try:
        current_key_version()  # fail fast if TOTP_ENC_KEYS is unset/invalid
    except TotpKeyUnavailable as exc:
        print(f"ERROR: {exc}")
        return 2

    engine = create_async_engine(str(settings.DATABASE_URL))
    now = dt.datetime.now(dt.UTC)
    secret = totp.generate_secret()

    try:
        async with engine.begin() as conn:
            # roles catalogue must exist (migration 009).
            role_id = (
                await conn.execute(text("SELECT id FROM roles WHERE name = 'admin'"))
            ).scalar_one_or_none()
            if role_id is None:
                print("ERROR: role 'admin' not found. Apply migration 009 first.")
                return 2

            # Upsert the user by phone (create if new, keep existing name/id).
            await conn.execute(
                text(
                    "INSERT INTO users (id, full_name, phone, is_active, created_at, updated_at) "
                    "VALUES (:id, :name, :ph, true, :now, :now) "
                    "ON CONFLICT (phone) DO UPDATE SET is_active = true, updated_at = :now"
                ),
                {"id": str(uuid.uuid4()), "name": name, "ph": phone, "now": now},
            )
            user_id = (
                await conn.execute(text("SELECT id FROM users WHERE phone = :ph"), {"ph": phone})
            ).scalar_one()

            await conn.execute(
                text(
                    "INSERT INTO user_roles (user_id, role_id, assigned_at) "
                    "VALUES (:uid, :rid, :now) ON CONFLICT DO NOTHING"
                ),
                {"uid": str(user_id), "rid": role_id, "now": now},
            )

            existing_cred = (
                await conn.execute(
                    text("SELECT 1 FROM admin_credentials WHERE user_id = :uid"),
                    {"uid": str(user_id)},
                )
            ).scalar_one_or_none()
            if existing_cred and not reset:
                print(
                    f"User {phone} already has an admin credential. "
                    "Re-run with --reset to rotate it (invalidates the old authenticator)."
                )
                return 1

            await conn.execute(
                text(
                    "INSERT INTO admin_credentials "
                    "(user_id, totp_secret_enc, key_version, enrolled_at, activated_at, "
                    " last_used_step, updated_at) "
                    "VALUES (:uid, :enc, :kv, :now, NULL, 0, :now) "
                    "ON CONFLICT (user_id) DO UPDATE SET "
                    "  totp_secret_enc = EXCLUDED.totp_secret_enc, "
                    "  key_version = EXCLUDED.key_version, "
                    "  activated_at = NULL, last_used_step = 0, updated_at = :now"
                ),
                {
                    "uid": str(user_id),
                    "enc": encrypt_secret(secret),
                    "kv": current_key_version(),
                    "now": now,
                },
            )
    finally:
        await engine.dispose()

    uri = totp.provisioning_uri(
        secret,
        account_name=phone,
        issuer=settings.TOTP_ISSUER,
        step=settings.TOTP_STEP_SECONDS,
    )
    print("\n" + "=" * 68)
    print("  FIRST ADMIN PROVISIONED — save the secret NOW (shown once)")
    print("=" * 68)
    print(f"  Phone     : {phone}")
    print(f"  Role      : admin")
    print(f"  Secret    : {secret}")
    print(f"  otpauth   : {uri}")
    print("=" * 68)
    print("  1. Add the secret/URI to an authenticator app (Google Authenticator / Authy).")
    print("  2. Log in: POST /v1/admin/auth/login  {phone, code}. First login activates it.")
    print("=" * 68 + "\n")
    return 0


def main() -> None:
    p = argparse.ArgumentParser(description="Provision the first admin (TOTP).")
    p.add_argument("--phone", default=os.getenv("ADMIN_PHONE"), help="E.164 phone, or ADMIN_PHONE env")
    p.add_argument("--name", default=os.getenv("ADMIN_NAME", "Platform Admin"))
    p.add_argument("--reset", action="store_true", help="Rotate an existing credential")
    args = p.parse_args()
    if not args.phone:
        p.error("--phone (or ADMIN_PHONE env) is required")
    raise SystemExit(asyncio.run(_run(args.phone, args.name, args.reset)))


if __name__ == "__main__":
    main()
