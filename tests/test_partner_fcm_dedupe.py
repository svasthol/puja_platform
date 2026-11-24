"""B7 — escalated high FCM dedupe per (pujari_id, booking_id)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import text

from app.services.fcm_client import FcmOutcome, FcmResult
from app.workers.notifications import _notify_offers_impl

from tests.test_partner_ux import (  # noqa: F401 — fixtures
    CUSTOMER,
    PUJA,
    ADDRESS,
    _register_device,
    _require_migration_014,
    _seed_live_offer,
)


@pytest.mark.asyncio
async def test_escalated_second_notify_skips_high_when_dedupe_set(session, seed, uniq):
    await _require_migration_014(session)
    bid, _ = await _seed_live_offer(session, uniq, booking_class="advance")
    await session.execute(
        text(
            """
            INSERT INTO booking_dispatch_state (
                booking_id, urgency_escalated_at, dispatch_deadline
            ) VALUES (:bid, now(), now() + interval '4 hours')
            ON CONFLICT (booking_id) DO UPDATE SET
                urgency_escalated_at = now(),
                dispatch_deadline = now() + interval '4 hours'
            """
        ),
        {"bid": bid},
    )
    await _register_device(session, uniq)

    mock_redis = MagicMock()
    mock_redis.set.side_effect = [True, False]

    with (
        patch("app.workers.redis_sync.get_sync_redis", return_value=mock_redis),
        patch("app.services.reconfirmation.is_quiet_hours", return_value=False),
        patch(
            "app.workers.notifications.send_push_sync",
            return_value=FcmResult(outcome=FcmOutcome.SENT, message_id="m1"),
        ) as mock_push,
    ):
        _notify_offers_impl(bid)
        first_priority = mock_push.call_args.kwargs["priority"]
        mock_push.reset_mock()
        _notify_offers_impl(bid)
        second_priority = mock_push.call_args.kwargs["priority"]

    assert first_priority == "high"
    assert second_priority == "normal"
    assert mock_push.call_args.kwargs.get("visible_tray") is True