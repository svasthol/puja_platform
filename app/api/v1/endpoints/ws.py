"""WebSocket ticket issue + booking socket (Redis pub/sub fan-out)."""
from __future__ import annotations

import json
import uuid

import redis.asyncio as aioredis
import structlog
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy import text

from app.core.config import get_settings
from app.core.dependencies import Principal, get_principal, resolve_ws_ticket
from app.core.redis_client import get_redis, redis_execute, redis_set
from app.db.engine import AsyncSessionLocal

router = APIRouter(tags=["ws"])
log = structlog.get_logger()
settings = get_settings()


@router.post("/ws-tickets")
async def issue_ticket(p: Principal = Depends(get_principal)):
    ticket = uuid.uuid4().hex
    await redis_set(
        f"ws_ticket:{ticket}",
        json.dumps({"user_id": str(p.user_id), "app_context": p.app_context}),
        ex=settings.WS_TICKET_TTL_SECONDS,
    )
    log.info(
        "ws_ticket_issued",
        user_id=str(p.user_id),
        app_context=p.app_context,
        expires_in=settings.WS_TICKET_TTL_SECONDS,
    )
    return {"ticket": ticket, "expires_in": settings.WS_TICKET_TTL_SECONDS}


async def _authorized_for_booking(user_id: uuid.UUID, booking_id: uuid.UUID) -> bool:
    async with AsyncSessionLocal() as db:
        row = (
            await db.execute(
                text(
                    "SELECT b.user_id, pj.user_id AS pujari_user "
                    "FROM bookings b LEFT JOIN pujaris pj ON pj.id = b.pujari_id "
                    "WHERE b.id = :bid"
                ),
                {"bid": str(booking_id)},
            )
        ).mappings().first()
    if row is None:
        return False
    return str(user_id) in (str(row["user_id"]), str(row["pujari_user"]))


@router.websocket("/ws/bookings/{booking_id}")
async def booking_socket(websocket: WebSocket, booking_id: uuid.UUID, ticket: str = ""):
    try:
        principal = await resolve_ws_ticket(ticket)
    except Exception:
        log.warning("ws_auth_failed", booking_id=str(booking_id), reason="invalid_or_used_ticket")
        await websocket.close(code=4401)
        return
    if not await _authorized_for_booking(principal.user_id, booking_id):
        log.warning(
            "ws_forbidden",
            booking_id=str(booking_id),
            user_id=str(principal.user_id),
            app_context=principal.app_context,
        )
        await websocket.close(code=4403)
        return

    await websocket.accept()
    log.info(
        "ws_connected",
        booking_id=str(booking_id),
        user_id=str(principal.user_id),
        app_context=principal.app_context,
    )
    r = get_redis()
    pubsub = r.pubsub()
    await pubsub.subscribe(f"booking:{booking_id}")
    try:
        async def relay():
            async for msg in pubsub.listen():
                if msg.get("type") == "message":
                    await websocket.send_text(msg["data"])

        import asyncio

        relay_task = asyncio.create_task(relay())
        channel = f"booking:{booking_id}"

        async def _publish(r: aioredis.Redis, payload: str) -> int:
            return await r.publish(channel, payload)

        while True:
            data = await websocket.receive_text()
            await redis_execute(lambda r, msg=data: _publish(r, msg))
    except WebSocketDisconnect:
        log.info(
            "ws_disconnected",
            booking_id=str(booking_id),
            user_id=str(principal.user_id),
        )
    finally:
        await pubsub.unsubscribe(f"booking:{booking_id}")
        await pubsub.aclose()
