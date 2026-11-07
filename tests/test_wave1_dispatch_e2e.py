"""Wave 1 #3 — pay → requested → broadcast → accept → confirmed (§21.2)."""
from __future__ import annotations

import datetime as dt
import uuid

import pytest
from sqlalchemy import text

from app.services import booking_events, offer_service, webhook_service
from app.services.dispatch_launch import launch_eligibility_sql, load_dispatch_settings
from app.workers.dispatch import broadcast_booking
from app.workers.sweep import get_connection
from tests.test_inbox_cap import (
    ADDRESS,
    CUSTOMER,
    PUJA,
    _ensure_pujari_dispatch_ready,
    _pujari_ids,
    _reset_dispatch_presence_state,
    _set_presence,
    _unique_slot_time,
)


def _eligible_pujari_ids_sync(booking_id: str) -> list[str]:
    """Same candidate pool as ``dispatch._dispatch_round`` (launch SQL)."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            settings = load_dispatch_settings(cur)
            cur.execute(launch_eligibility_sql(settings), (booking_id,))
            return [str(r[0]) for r in cur.fetchall()]
    finally:
        conn.close()


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


async def _ensure_default_rm(session) -> None:
    rm_id = uuid.uuid4()
    await session.execute(
        text(
            """
            INSERT INTO relationship_managers (id, name, phone, city, is_active, created_at, updated_at)
            VALUES (:id, 'E2E RM', '+910000009999', 'Hyd', true, now(), now())
            ON CONFLICT DO NOTHING
            """
        ),
        {"id": str(rm_id)},
    )
    await session.execute(
        text(
            """
            INSERT INTO platform_settings (key, value_json, updated_at)
            VALUES (
                'default_relationship_manager_id',
                CAST(:val AS jsonb),
                now()
            )
            ON CONFLICT (key) DO UPDATE
            SET value_json = EXCLUDED.value_json, updated_at = now()
            """
        ),
        {"val": f'{{"relationship_manager_id": "{rm_id}"}}'},
    )


async def _insert_payment_pending_booking(
    session,
    uniq,
    *,
    booking_class: str = "advance",
) -> uuid.UUID:
    booking_id = uuid.uuid4()
    slot_time = _unique_slot_time(uniq)
    pending_id = (
        await session.execute(
            text(
                "SELECT id FROM status_types WHERE domain='booking' AND code='payment_pending'"
            )
        )
    ).scalar_one()
    policy_id = (
        await session.execute(
            text("SELECT id FROM cancellation_policies WHERE name='standard'")
        )
    ).scalar_one()
    await session.execute(
        text(
            """
            INSERT INTO bookings (
                id, user_id, puja_id, address_id, status_id, cancellation_policy_id,
                scheduled_date, scheduled_time, duration_minutes, total_amount,
                amount_due_online, amount_due_offline, payment_mode, dispatch_mode,
                booking_class, created_at, updated_at
            ) VALUES (
                :bid, :uid, :puja, :addr, :sid, :cpid,
                :sd, CAST(:st AS time), 90, 2100, 2100, 0, 'full_online', 'broadcast',
                :cls, :now, :now
            )
            """
        ),
        {
            "bid": str(booking_id),
            "uid": CUSTOMER,
            "puja": PUJA,
            "addr": ADDRESS,
            "sid": pending_id,
            "cpid": policy_id,
            "sd": uniq.date,
            "st": slot_time,
            "cls": booking_class,
            "now": dt.datetime.now(dt.UTC),
        },
    )
    return booking_id


@pytest.mark.asyncio
async def test_wave1_pay_requested_broadcast_accept_confirmed(session, seed, uniq, monkeypatch):
    """Full dispatch loop after Razorpay webhook."""
    await _require_migration_014(session)
    await _reset_dispatch_presence_state(session)
    await _ensure_pujari_dispatch_ready(session)
    await _ensure_default_rm(session)
    await _pujari_ids(session)

    # Use instant class so G1 inbox-cap does not drop every candidate on a shared dev DB
    # full of stale advance offers (filter only runs for ``booking_class='advance'``).
    booking_id = await _insert_payment_pending_booking(session, uniq, booking_class="instant")
    await session.commit()

    async def _noop_publish(*_args: object, **_kwargs: object) -> None:
        return None

    monkeypatch.setattr(booking_events, "publish_booking_event", _noop_publish)

    result = await webhook_service.handle_payment_captured(
        session,
        booking_id=booking_id,
        gateway_txn_id=f"pay_{uniq.id()}",
        idempotency_key=f"idem_{uniq.id()}",
        amount_paise=210000,
    )
    await session.commit()
    assert result.get("enqueue_broadcast") == str(booking_id)

    status = (
        await session.execute(
            text(
                """
                SELECT st.code FROM bookings b
                JOIN status_types st ON st.id = b.status_id
                WHERE b.id = :bid
                """
            ),
            {"bid": str(booking_id)},
        )
    ).scalar_one()
    assert status == "requested"

    eligible = _eligible_pujari_ids_sync(str(booking_id))
    assert eligible, "expected ≥1 launch-eligible pujari after _ensure_pujari_dispatch_ready"
    # Heartbeat keys for every SQL candidate — ordering is undefined without ORDER BY; a single id can miss the round-trip list.
    _set_presence(*eligible)

    broadcast_result = broadcast_booking(str(booking_id))
    assert broadcast_result.get("offers", 0) >= 1

    row_offer = (
        await session.execute(
            text(
                """
                SELECT ba.id::text, pj.user_id::text
                FROM booking_assignments ba
                JOIN status_types st ON st.id = ba.status_id
                JOIN pujaris pj ON pj.id = ba.pujari_id
                WHERE ba.booking_id = :bid AND st.domain = 'assignment' AND st.code = 'offered'
                  AND ba.responded_at IS NULL AND ba.expires_at > now()
                ORDER BY ba.offered_at ASC
                LIMIT 1
                """
            ),
            {"bid": str(booking_id)},
        )
    ).one()
    assignment_id, accept_user_id = row_offer[0], row_offer[1]

    await offer_service.accept_offer(
        session,
        user_id=uuid.UUID(accept_user_id),
        assignment_id=uuid.UUID(assignment_id),
    )
    await session.commit()

    row = (
        await session.execute(
            text(
                """
                SELECT st.code AS status, b.pujari_id::text, b.relationship_manager_id::text
                FROM bookings b
                JOIN status_types st ON st.id = b.status_id
                WHERE b.id = :bid
                """
            ),
            {"bid": str(booking_id)},
        )
    ).mappings().one()

    assert row["status"] == "confirmed"
    assert row["pujari_id"] is not None
    assert row["relationship_manager_id"] is not None
