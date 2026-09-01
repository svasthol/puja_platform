"""Synchronous Redis helpers for Celery workers (timeouts + owner-token locks)."""
from __future__ import annotations

import uuid

import redis as redis_lib

from app.core.config import get_settings

_RELEASE_LOCK_LUA = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
else
    return 0
end
"""


def namespaced_key(base: str) -> str:
    """Prefix lock keys with APP_ENV so dev/staging/prod do not collide."""
    settings = get_settings()
    return f"{settings.APP_ENV}:{base}"


def get_sync_redis() -> redis_lib.Redis:
    """Process-local sync client with connect/read timeouts (matches async pool policy)."""
    return redis_lib.from_url(
        str(get_settings().REDIS_URL),
        socket_connect_timeout=5,
        socket_timeout=10,
        socket_keepalive=True,
        health_check_interval=30,
        retry_on_timeout=True,
    )


def new_lock_token() -> str:
    return uuid.uuid4().hex


def acquire_lock(redis_client: redis_lib.Redis, key: str, token: str, *, ttl_seconds: int) -> bool:
    return bool(redis_client.set(key, token, nx=True, ex=ttl_seconds))


def release_lock(redis_client: redis_lib.Redis, key: str, token: str) -> None:
    redis_client.eval(_RELEASE_LOCK_LUA, 1, key, token)
