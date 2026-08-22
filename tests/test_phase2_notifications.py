"""Phase 2 worker tests — notify_offers / notify_no_pujari with mocked FCM+SMS."""
from __future__ import annotations

from unittest.mock import patch

import pytest
from sqlalchemy import text

from app.services.fcm_client import FcmOutcome, FcmResult
from app.workers.notifications import (
    _notify_no_pujari_impl,
    _notify_offer_withdrawn_impl,
    _notify_offers_impl,
)

CUSTOMER = "aaaaaaaa-0000-0000-0000-000000000001"
PUJARI = "cccccccc-0000-0000-0000-000000000001"
PUJARI_USER = "bbbbbbbb-0000-0000-0000-000000000001"
PUJA = "11111111-1111-1111-1111-111111111111"
ADDRESS = "dddddddd-0000-0000-0000-000000000001"


async def _pujari_id(session) -> str:
    pid = (
        await session.execute(
            text("SELECT id::text FROM pujaris WHERE user_id = :u LIMIT 1"),
            {"u": PUJARI_USER},
        )
    ).scalar_one_or_none()
    if pid is None:
        raise RuntimeError("seed missing pujari for PUJARI_USER")
    return pid


async def _seed_booking_with_live_offer(
    session, uniq, *, dispatch_mode: str = "broadcast", booking_class: str = "advance"
) -> str:
    bid = uniq.id()
    pujari_id = await _pujari_id(session)
    await session.execute(
        text(
            """
            INSERT INTO bookings (
                id, user_id, puja_id, address_id, status_id, cancellation_policy_id,
                scheduled_date, scheduled_time, duration_minutes, total_amount,
                amount_due_online, amount_due_offline, payment_mode, paid_at,
                dispatch_mode, booking_class, pujari_id, created_at, updated_at
            ) VALUES (
                :bid, :uid, :puja, :addr,
                (SELECT id FROM status_types WHERE domain='booking' AND code='requested'),
                (SELECT id FROM cancellation_policies WHERE name='standard'),
                :d, '10:00', 90, 2100, 2100, 0, 'full_online', now(),
                :dm, :cls, NULL, now(), now()
            )
            """
        ),
        {
            "bid": bid,
            "uid": CUSTOMER,
            "puja": PUJA,
            "addr": ADDRESS,
            "d": uniq.date,
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
            ) VALUES (gen_random_uuid(), :bid, :pj, :sid, now(), now() + interval '10 minutes')
            """
        ),
        {"bid": bid, "pj": pujari_id, "sid": offered_id},
    )
    await session.commit()
    return bid


async def _clear_devices(session, user_id: str) -> None:
    await session.execute(text("DELETE FROM devices WHERE user_id = :uid"), {"uid": user_id})
    await session.commit()


@pytest.mark.asyncio
async def test_notify_offers_sends_fcm_and_writes_notification(session, seed, uniq):
    bid = await _seed_booking_with_live_offer(session, uniq)
    await _clear_devices(session, PUJARI_USER)
    tok = f"notify-tok-{uniq.id()[:10]}"
    await session.execute(
        text(
            "INSERT INTO devices (user_id, device_token, platform, created_at) "
            "VALUES (:uid, :tok, 'android', now())"
        ),
        {"uid": PUJARI_USER, "tok": tok},
    )
    await session.commit()

    with patch(
        "app.workers.notifications.send_push_sync",
        return_value=FcmResult(outcome=FcmOutcome.SENT, message_id="m1"),
    ) as mock_push:
        result = _notify_offers_impl(bid)

    assert result["targets"] == 1
    assert result["fcm_sent"] == 1
    mock_push.assert_called_once()

    notif = (
        await session.execute(
            text(
                "SELECT title FROM notifications WHERE user_id = :uid AND related_id = :bid"
            ),
            {"uid": PUJARI_USER, "bid": bid},
        )
    ).scalar_one_or_none()
    assert notif is not None


@pytest.mark.asyncio
async def test_notify_offers_deletes_unregistered_device(session, seed, uniq):
    bid = await _seed_booking_with_live_offer(session, uniq)
    await _clear_devices(session, PUJARI_USER)
    tok = f"dead-tok-{uniq.id()[:10]}"
    await session.execute(
        text(
            "INSERT INTO devices (user_id, device_token, platform, created_at) "
            "VALUES (:uid, :tok, 'android', now())"
        ),
        {"uid": PUJARI_USER, "tok": tok},
    )
    await session.commit()

    with patch(
        "app.workers.notifications.send_push_sync",
        return_value=FcmResult(outcome=FcmOutcome.UNREGISTERED, error="NotRegistered"),
    ):
        result = _notify_offers_impl(bid)

    assert result["devices_deleted"] == 1
    gone = (
        await session.execute(text("SELECT 1 FROM devices WHERE device_token = :tok"), {"tok": tok})
    ).first()
    assert gone is None


@pytest.mark.asyncio
async def test_notify_offers_direct_mode_sms_fallback(session, seed, uniq):
    bid = await _seed_booking_with_live_offer(session, uniq, dispatch_mode="direct")
    # No device row — FCM skipped/failed → SMS fallback for direct mode
    with (
        patch(
            "app.workers.notifications.send_push_sync",
            return_value=FcmResult(outcome=FcmOutcome.SKIPPED),
        ),
        patch("app.workers.notifications.send_transactional_sms_sync", return_value=True) as mock_sms,
    ):
        result = _notify_offers_impl(bid)

    assert result["sms_fallback"] == 1
    mock_sms.assert_called_once()


@pytest.mark.asyncio
async def test_notify_no_pujari_customer_push_and_notification(session, seed, uniq):
    bid = uniq.id()
    await _clear_devices(session, CUSTOMER)
    await session.execute(
        text(
            """
            INSERT INTO bookings (
                id, user_id, puja_id, address_id, status_id, cancellation_policy_id,
                scheduled_date, scheduled_time, duration_minutes, total_amount,
                amount_due_online, amount_due_offline, payment_mode, paid_at,
                dispatch_mode, booking_class, cancelled_at, created_at, updated_at
            ) VALUES (
                :bid, :uid, :puja, :addr,
                (SELECT id FROM status_types WHERE domain='booking' AND code='failed_no_pujari'),
                (SELECT id FROM cancellation_policies WHERE name='standard'),
                :d, '11:00', 90, 2100, 2100, 0, 'full_online', now(),
                'broadcast', 'advance', now(), now(), now()
            )
            """
        ),
        {"bid": bid, "uid": CUSTOMER, "puja": PUJA, "addr": ADDRESS, "d": uniq.date},
    )
    tok = f"cust-tok-{uniq.id()[:10]}"
    await session.execute(
        text(
            "INSERT INTO devices (user_id, device_token, platform, created_at) "
            "VALUES (:uid, :tok, 'ios', now())"
        ),
        {"uid": CUSTOMER, "tok": tok},
    )
    await session.commit()

    with patch(
        "app.workers.notifications.send_push_sync",
        return_value=FcmResult(outcome=FcmOutcome.SENT, message_id="c1"),
    ):
        result = _notify_no_pujari_impl(bid)

    assert result["fcm_sent"] == 1
    notif = (
        await session.execute(
            text("SELECT title FROM notifications WHERE user_id = :uid AND related_id = :bid"),
            {"uid": CUSTOMER, "bid": bid},
        )
    ).scalar_one_or_none()
    assert notif == "No pujari available"


@pytest.mark.asyncio
async def test_notify_offer_withdrawn_after_customer_cancel(session, seed, uniq):
    bid = await _seed_booking_with_live_offer(session, uniq)
    await _clear_devices(session, PUJARI_USER)
    tok = f"withdraw-tok-{uniq.id()[:10]}"
    await session.execute(
        text(
            "INSERT INTO devices (user_id, device_token, platform, created_at) "
            "VALUES (:uid, :tok, 'android', now())"
        ),
        {"uid": PUJARI_USER, "tok": tok},
    )
    cancelled_id = (
        await session.execute(
            text("SELECT id FROM status_types WHERE domain='booking' AND code='cancelled'")
        )
    ).scalar_one()
    expired_id = (
        await session.execute(
            text("SELECT id FROM status_types WHERE domain='assignment' AND code='expired'")
        )
    ).scalar_one()
    await session.execute(
        text(
            "UPDATE bookings SET cancelled_at = now(), status_id = :sid WHERE id = :bid"
        ),
        {"sid": cancelled_id, "bid": bid},
    )
    await session.execute(
        text(
            """
            UPDATE booking_assignments
            SET status_id = :expired_id, responded_at = now()
            WHERE booking_id = :bid AND responded_at IS NULL
            """
        ),
        {"expired_id": expired_id, "bid": bid},
    )
    await session.commit()

    with patch(
        "app.workers.notifications.send_push_sync",
        return_value=FcmResult(outcome=FcmOutcome.SENT, message_id="w1"),
    ) as mock_push:
        result = _notify_offer_withdrawn_impl(bid)

    assert result["targets"] == 1
    assert result["fcm_sent"] == 1
    mock_push.assert_called_once()
    _args, kwargs = mock_push.call_args
    assert kwargs["data"]["type"] == "offer_withdrawn"
    assert kwargs["data"]["booking_id"] == bid
    assert kwargs["priority"] == "normal"

    notif = (
        await session.execute(
            text(
                "SELECT title FROM notifications WHERE user_id = :uid AND related_id = :bid"
            ),
            {"uid": PUJARI_USER, "bid": bid},
        )
    ).scalar_one_or_none()
    assert notif == "Offer withdrawn"
