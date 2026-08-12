"""Phase 2 integration tests — device registration (B-DEVICE)."""
from __future__ import annotations

import pytest
from sqlalchemy import text

PUJARI_USER = "bbbbbbbb-0000-0000-0000-000000000001"
CUSTOMER = "aaaaaaaa-0000-0000-0000-000000000001"


@pytest.mark.asyncio
async def test_device_upsert_and_transfer(session, seed, uniq):
    """Same token re-registered by another user moves ownership (globally unique token)."""
    tok = f"fcm-test-{uniq.id()[:12]}"
    await session.execute(
        text(
            "INSERT INTO devices (user_id, device_token, platform, created_at) "
            "VALUES (:uid, :tok, 'android', now())"
        ),
        {"uid": CUSTOMER, "tok": tok},
    )
    await session.commit()

    await session.execute(
        text(
            """
            INSERT INTO devices (id, user_id, device_token, platform, last_seen_at, created_at)
            VALUES (gen_random_uuid(), :uid, :tok, 'ios', now(), now())
            ON CONFLICT (device_token) DO UPDATE
            SET user_id = EXCLUDED.user_id, platform = EXCLUDED.platform, last_seen_at = now()
            """
        ),
        {"uid": PUJARI_USER, "tok": tok},
    )
    await session.commit()

    row = (
        await session.execute(
            text("SELECT user_id::text, platform FROM devices WHERE device_token = :tok"),
            {"tok": tok},
        )
    ).first()
    assert row is not None
    assert row[0] == PUJARI_USER
    assert row[1] == "ios"


@pytest.mark.asyncio
async def test_device_delete_only_owner(session, seed, uniq):
    tok = f"fcm-del-{uniq.id()[:12]}"
    await session.execute(
        text(
            "INSERT INTO devices (user_id, device_token, platform, created_at) "
            "VALUES (:uid, :tok, 'web', now())"
        ),
        {"uid": CUSTOMER, "tok": tok},
    )
    await session.commit()

    result = await session.execute(
        text("DELETE FROM devices WHERE device_token = :tok AND user_id = :uid"),
        {"tok": tok, "uid": PUJARI_USER},
    )
    assert result.rowcount == 0

    still = (
        await session.execute(text("SELECT 1 FROM devices WHERE device_token = :tok"), {"tok": tok})
    ).first()
    assert still is not None
