"""DV2-PARTNER-UX — class-aware broadcast FCM + accept_ack (§21.6.H)."""
from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from sqlalchemy import text

from app.services import offer_service
from app.services.fcm_client import FcmOutcome, FcmResult
from app.workers.notifications import _notify_accept_ack_impl, _notify_offers_impl

CUSTOMER = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001")
PUJARI_USER = uuid.UUID("bbbbbbbb-0000-0000-0000-000000000001")
PUJA = "11111111-1111-1111-1111-111111111111"
ADDRESS = "dddddddd-0000-0000-0000-000000000001"


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


async def _pujari_id(session) -> str:
    return (
        await session.execute(
            text("SELECT id::text FROM pujaris WHERE user_id = :u"),
            {"u": str(PUJARI_USER)},
        )
    ).scalar_one()


def _unique_slot_time(uniq) -> str:
    h = (int(uniq.id().replace("-", "")[:4], 16) % 12) + 8
    m = int(uniq.id().replace("-", "")[4:8], 16) % 60
    return f"{h:02d}:{m:02d}:00"


async def _seed_live_offer(
    session,
    uniq,
    *,
    booking_class: str,
    dispatch_mode: str = "broadcast",
) -> tuple[str, str]:
    bid, aid = uniq.id(), uniq.id()
    pujari_id = await _pujari_id(session)
    slot_time = _unique_slot_time(uniq)
    await session.execute(
        text(
            """
            INSERT INTO bookings (
                id, user_id, puja_id, address_id, status_id, cancellation_policy_id,
                scheduled_date, scheduled_time, duration_minutes, total_amount,
                amount_due_online, amount_due_offline, payment_mode, paid_at,
                dispatch_mode, booking_class, created_at, updated_at
            ) VALUES (
                :bid, :uid, :puja, :addr,
                (SELECT id FROM status_types WHERE domain='booking' AND code='requested'),
                (SELECT id FROM cancellation_policies WHERE name='standard'),
                :d, CAST(:t AS time), 90, 2100, 2100, 0, 'full_online', now(),
                :dm, :cls, now(), now()
            )
            """
        ),
        {
            "bid": bid,
            "uid": str(CUSTOMER),
            "puja": PUJA,
            "addr": ADDRESS,
            "d": uniq.date,
            "t": slot_time,
            "dm": dispatch_mode,
            "cls": booking_class,
        },
    )
    offered_id = (
        await session.execute(
            text("SELECT id FROM status_types WHERE domain='assignment' AND code='offered'")
        )
    ).scalar_one()
    await session.execute(
        text(
            """
            INSERT INTO booking_assignments (
                id, booking_id, pujari_id, status_id, offered_at, expires_at
            ) VALUES (:aid, :bid, :pid, :sid, now(), now() + interval '10 minutes')
            """
        ),
        {"aid": aid, "bid": bid, "pid": pujari_id, "sid": offered_id},
    )
    await session.commit()
    return bid, aid


async def _register_device(session, uniq) -> None:
    await session.execute(
        text("DELETE FROM devices WHERE user_id = :uid"),
        {"uid": str(PUJARI_USER)},
    )
    await session.execute(
        text(
            """
            INSERT INTO devices (user_id, device_token, platform, created_at)
            VALUES (:uid, :tok, 'android', now())
            """
        ),
        {"uid": str(PUJARI_USER), "tok": f"partner-ux-{uniq.id()[:12]}"},
    )
    await session.commit()


@pytest.mark.asyncio
async def test_notify_offers_advance_uses_offer_advance_type(session, seed, uniq):
    await _require_migration_014(session)
    bid, _ = await _seed_live_offer(session, uniq, booking_class="advance")
    await _register_device(session, uniq)

    with patch(
        "app.workers.notifications.send_push_sync",
        return_value=FcmResult(outcome=FcmOutcome.SENT, message_id="m1"),
    ) as mock_push:
        result = _notify_offers_impl(bid)

    assert result["offer_type"] == "offer_advance"
    assert mock_push.call_args.kwargs["data"]["type"] == "offer_advance"
    assert mock_push.call_args.kwargs["priority"] == "normal"


@pytest.mark.asyncio
async def test_notify_offers_instant_uses_offer_instant_type(session, seed, uniq):
    await _require_migration_014(session)
    bid, _ = await _seed_live_offer(session, uniq, booking_class="instant")
    await _register_device(session, uniq)

    with patch(
        "app.workers.notifications.send_push_sync",
        return_value=FcmResult(outcome=FcmOutcome.SENT, message_id="m1"),
    ) as mock_push:
        result = _notify_offers_impl(bid)

    assert result["offer_type"] == "offer_instant"
    assert mock_push.call_args.kwargs["data"]["type"] == "offer_instant"
    assert mock_push.call_args.kwargs["priority"] == "high"


@pytest.mark.asyncio
async def test_accept_ack_sent_for_advance_booking(session, seed, uniq):
    await _require_migration_014(session)
    bid, aid = await _seed_live_offer(session, uniq, booking_class="advance")
    await _register_device(session, uniq)

    with patch(
        "app.workers.notifications.send_push_sync",
        return_value=FcmResult(outcome=FcmOutcome.SENT, message_id="ack1"),
    ) as mock_push:
        result = _notify_accept_ack_impl(bid, str(PUJARI_USER))

    assert result["fcm_sent"] == 1
    assert mock_push.call_args.kwargs["data"]["type"] == "accept_ack"
    assert mock_push.call_args.kwargs["priority"] == "normal"
    notif = (
        await session.execute(
            text(
                "SELECT body FROM notifications "
                "WHERE user_id = :uid AND related_id = :bid AND related_type = 'booking'"
            ),
            {"uid": str(PUJARI_USER), "bid": bid},
        )
    ).scalar_one()
    assert "confirm" in notif.lower()


@pytest.mark.asyncio
async def test_accept_ack_skipped_for_instant_booking(session, seed, uniq):
    await _require_migration_014(session)
    bid, _ = await _seed_live_offer(session, uniq, booking_class="instant")

    result = _notify_accept_ack_impl(bid, str(PUJARI_USER))
    assert result["skipped"] == "not_advance"


@pytest.mark.asyncio
async def test_accept_offer_enqueues_accept_ack_for_advance(session, seed, uniq, monkeypatch):
    await _require_migration_014(session)
    bid, aid = await _seed_live_offer(session, uniq, booking_class="advance")

    sent: list[tuple] = []
    monkeypatch.setattr(
        "app.workers.celery_app.celery_app.send_task",
        lambda name, args=None, **kw: sent.append((name, args)),
    )
    async def _noop_publish(*_a, **_kw):
        return None

    monkeypatch.setattr(
        "app.services.offer_service.booking_events.publish_booking_event",
        _noop_publish,
    )

    await offer_service.accept_offer(
        session, user_id=PUJARI_USER, assignment_id=uuid.UUID(aid)
    )
    await session.commit()

    assert (
        "app.workers.notifications.notify_accept_ack",
        [bid, str(PUJARI_USER)],
    ) in sent


@pytest.mark.asyncio
async def test_accept_offer_skips_accept_ack_for_instant(session, seed, uniq, monkeypatch):
    await _require_migration_014(session)
    bid, aid = await _seed_live_offer(session, uniq, booking_class="instant")

    sent: list[tuple] = []
    monkeypatch.setattr(
        "app.workers.celery_app.celery_app.send_task",
        lambda name, args=None, **kw: sent.append((name, args)),
    )

    async def _noop_publish(*_a, **_kw):
        return None

    monkeypatch.setattr(
        "app.services.offer_service.booking_events.publish_booking_event",
        _noop_publish,
    )

    await offer_service.accept_offer(
        session, user_id=PUJARI_USER, assignment_id=uuid.UUID(aid)
    )
    await session.commit()

    ack_calls = [c for c in sent if c[0] == "app.workers.notifications.notify_accept_ack"]
    assert ack_calls == []
