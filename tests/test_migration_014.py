"""Migration 014 — Dispatch v2 schema + trigger 3 sibling supersede (§21.6)."""
from __future__ import annotations

import pytest
from sqlalchemy import text

PUJARI_USER1 = "bbbbbbbb-0000-0000-0000-000000000001"
PUJARI_USER2 = "bbbbbbbb-0000-0000-0000-000000000002"


async def _pujari_ids(session) -> tuple[str, str]:
    p1 = (
        await session.execute(
            text("SELECT id FROM pujaris WHERE user_id = :uid"),
            {"uid": PUJARI_USER1},
        )
    ).scalar_one()
    p2 = (
        await session.execute(
            text("SELECT id FROM pujaris WHERE user_id = :uid"),
            {"uid": PUJARI_USER2},
        )
    ).scalar_one()
    return str(p1), str(p2)


async def _require_migration_014(session) -> None:
    row = (
        await session.execute(
            text(
                """
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'bookings'
                  AND column_name = 'booking_class'
                """
            )
        )
    ).scalar_one_or_none()
    if row is None:
        pytest.skip("migration_014 not applied — run: python scripts/apply_migration_014.py")


@pytest.mark.asyncio
async def test_migration_014_schema(session):
    """DDL present: booking_class, dispatch markers, superseded seed, settings."""
    await _require_migration_014(session)

    nullable = (
        await session.execute(
            text(
                """
                SELECT is_nullable FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'bookings'
                  AND column_name = 'booking_class'
                """
            )
        )
    ).scalar_one()
    assert nullable == "NO"

    cols = (
        await session.execute(
            text(
                """
                SELECT column_name FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'booking_dispatch_state'
                  AND column_name IN (
                      'urgency_escalated_at',
                      'rm_escalated_no_accept_at',
                      'rm_escalated_t24_at'
                  )
                """
            )
        )
    ).scalars().all()
    assert set(cols) == {
        "urgency_escalated_at",
        "rm_escalated_no_accept_at",
        "rm_escalated_t24_at",
    }

    superseded_id = (
        await session.execute(
            text(
                "SELECT id FROM status_types "
                "WHERE domain = 'assignment' AND code = 'superseded'"
            )
        )
    ).scalar_one_or_none()
    assert superseded_id is not None

    settings = (
        await session.execute(
            text(
                """
                SELECT key FROM platform_settings
                WHERE key IN (
                    'night_bookings_enabled',
                    'immediate_dispatch_on_payment',
                    'advance_offer_ttl_hours',
                    'instant_offer_ttl_seconds',
                    'max_live_advance_offers_per_pujari',
                    'reconfirm_quiet_hours_start',
                    'reconfirm_quiet_hours_end'
                )
                """
            )
        )
    ).scalars().all()
    assert len(settings) == 7


@pytest.mark.asyncio
async def test_sibling_supersede_on_first_accept(session, seed, uniq):
    """LG-sibling-supersede: first accept supersedes other live offers (§21.6.B)."""
    await _require_migration_014(session)

    pujari1, pujari2 = await _pujari_ids(session)
    bid, winner_aid, loser_aid = uniq.id(), uniq.id(), uniq.id()
    await session.execute(
        text(
            """
            INSERT INTO bookings (
                id, user_id, puja_id, address_id, status_id, cancellation_policy_id,
                scheduled_date, scheduled_time, duration_minutes, total_amount,
                amount_due_online, amount_due_offline, payment_mode, paid_at,
                dispatch_mode, booking_class, created_at, updated_at
            ) VALUES (
                :bid, 'aaaaaaaa-0000-0000-0000-000000000001',
                '11111111-1111-1111-1111-111111111111',
                'dddddddd-0000-0000-0000-000000000001',
                (SELECT id FROM status_types WHERE domain='booking' AND code='requested'),
                (SELECT id FROM cancellation_policies WHERE name='standard'),
                :d, '10:00', 90, 2100, 2100, 0, 'full_online', now(), 'broadcast',
                'advance', now(), now()
            )
            """
        ),
        {"bid": bid, "d": uniq.date},
    )
    for aid, pid in ((winner_aid, pujari1), (loser_aid, pujari2)):
        await session.execute(
            text(
                """
                INSERT INTO booking_assignments (
                    id, booking_id, pujari_id, status_id, offered_at, expires_at
                ) VALUES (
                    :aid, :bid, :pid,
                    (SELECT id FROM status_types WHERE domain='assignment' AND code='offered'),
                    now(), now() + interval '24 hours'
                )
                """
            ),
            {"aid": aid, "bid": bid, "pid": pid},
        )
    await session.commit()

    await session.execute(
        text(
            """
            UPDATE booking_assignments
            SET status_id = (
                    SELECT id FROM status_types
                    WHERE domain = 'assignment' AND code = 'accepted'
                ),
                responded_at = now()
            WHERE id = :aid
            """
        ),
        {"aid": winner_aid},
    )
    await session.commit()

    rows = (
        await session.execute(
            text(
                """
                SELECT ba.id, st.code AS status, ba.responded_at IS NOT NULL AS resolved
                FROM booking_assignments ba
                JOIN status_types st ON st.id = ba.status_id
                WHERE ba.booking_id = :bid
                ORDER BY ba.offered_at ASC
                """
            ),
            {"bid": bid},
        )
    ).mappings().all()

    by_id = {str(r["id"]): r for r in rows}
    assert by_id[winner_aid]["status"] == "accepted"
    assert by_id[loser_aid]["status"] == "superseded"
    assert by_id[loser_aid]["resolved"] is True

    accepted_count = sum(1 for r in rows if r["status"] == "accepted")
    assert accepted_count == 1
