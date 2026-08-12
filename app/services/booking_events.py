"""
Server-published booking WebSocket events (P-WS / C-WS).

Publishes JSON to Redis channel `booking:{booking_id}`; WS handler relays to
connected clients. Workers use sync redis; API handlers use async.
"""
from __future__ import annotations

import json
from typing import Any

import structlog

log = structlog.get_logger()


def _channel(booking_id: str) -> str:
    return f"booking:{booking_id}"


def _payload(event: str, **fields: Any) -> str:
    return json.dumps({"type": event, **fields})


def publish_booking_event_sync(booking_id: str, event: str, **fields: Any) -> int:
    import redis as redis_lib

    from app.core.config import get_settings

    r = redis_lib.from_url(str(get_settings().REDIS_URL))
    try:
        n = r.publish(_channel(booking_id), _payload(event, **fields))
        log.info("booking_event_published", booking_id=booking_id, booking_event=event, subscribers=n)
        return int(n)
    finally:
        r.close()


async def publish_booking_event(booking_id: str, event: str, **fields: Any) -> int:
    from app.core.redis_client import get_redis

    r = get_redis()
    n = await r.publish(_channel(booking_id), _payload(event, **fields))
    log.info("booking_event_published", booking_id=booking_id, booking_event=event, subscribers=n)
    return int(n)
