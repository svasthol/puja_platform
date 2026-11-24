"""Migration 040 — urgency escalation settings + morning-wake column."""
from __future__ import annotations

import pytest
from sqlalchemy import text


@pytest.mark.asyncio
async def test_migration_040_columns_and_settings(session):
    col = (
        await session.execute(
            text(
                """
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'booking_dispatch_state'
                  AND column_name = 'escalated_holders_shortened_at'
                """
            )
        )
    ).scalar_one_or_none()
    if col is None:
        pytest.skip("migration_040 not applied — run: python scripts/apply_migration_040.py")

    for key in (
        "urgency_escalation_lead_hours",
        "escalated_offer_ttl_seconds",
        "rebroadcast_on_urgency_flip",
    ):
        row = (
            await session.execute(
                text("SELECT value_json FROM platform_settings WHERE key = :k"),
                {"k": key},
            )
        ).scalar_one_or_none()
        assert row is not None, key