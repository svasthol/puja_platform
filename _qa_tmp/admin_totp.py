"""Generate an ephemeral admin TOTP login code for QA (uses app config; prints no secrets)."""
from __future__ import annotations

import asyncio
import sys

from dotenv import load_dotenv
load_dotenv()
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


async def run():
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine
    from app.core.config import get_settings

    eng = create_async_engine(str(get_settings().DATABASE_URL))
    async with eng.connect() as conn:
        row = (await conn.execute(text(
            "SELECT u.phone, ac.totp_secret_enc, ac.key_version, ac.activated_at "
            "FROM admin_credentials ac JOIN users u ON u.id = ac.user_id "
            "JOIN user_roles ur ON ur.user_id = u.id "
            "ORDER BY ac.activated_at NULLS LAST LIMIT 1"
        ))).first()
    await eng.dispose()
    if row is None:
        print("NO_ADMIN")
        return
    phone, enc, keyv, activated = row
    from app.core.crypto import decrypt_secret
    from app.core.totp import totp_at
    secret = decrypt_secret(enc)
    code = totp_at(secret)
    print(f"ADMIN_PHONE={phone}")
    print(f"ACTIVATED={activated is not None}")
    print(f"TOTP_CODE={code}")


if __name__ == "__main__":
    asyncio.run(run())
