"""Phase 2 tests — booking WebSocket event publishing (P-WS)."""
from __future__ import annotations

import json
import uuid

import pytest

from app.services.booking_events import publish_booking_event_sync


@pytest.fixture
def redis_available():
    try:
        import redis as redis_lib
        from app.core.config import get_settings

        r = redis_lib.from_url(str(get_settings().REDIS_URL))
        r.ping()
        r.close()
        return True
    except Exception:
        pytest.skip("Redis not available for booking_events test")


def test_publish_booking_event_sync_delivers_payload(redis_available):
    bid = str(uuid.uuid4())
    import redis as redis_lib
    from app.core.config import get_settings

    r = redis_lib.from_url(str(get_settings().REDIS_URL))
    pubsub = r.pubsub()
    pubsub.subscribe(f"booking:{bid}")
    # drain subscribe ack
    pubsub.get_message(timeout=2)
    pubsub.get_message(timeout=2)

    publish_booking_event_sync(bid, "status_changed", status="requested")

    msg = pubsub.get_message(timeout=3, ignore_subscribe_messages=True)
    assert msg is not None
    payload = json.loads(msg["data"])
    assert payload["type"] == "status_changed"
    assert payload["status"] == "requested"
    pubsub.unsubscribe(f"booking:{bid}")
    pubsub.close()
    r.close()
