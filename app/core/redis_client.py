"""
Async Redis client — presence TTL keys, rate limits, WS tickets, dispatch locks,
and pub/sub. One shared connection pool per process, created at FastAPI lifespan
startup and recycled on stale connections.

Uses redis.asyncio (redis-py 5.x). GETDEL (single-use WS tickets) requires 5.x.

Production notes:
  - Pool is warmed with PING at startup (not on first request).
  - Transient connection failures (idle timeout, network blip, dead asyncio
    transport on Windows) trigger one pool reset + retry via redis_execute().
  - Callers that need reliability should use redis_execute() or the thin
    helpers below — not raw get_redis() commands.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TypeVar

import redis.asyncio as aioredis
import structlog
from redis.asyncio.retry import Retry
from redis.backoff import ExponentialBackoff
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError

from app.core.config import get_settings

log = structlog.get_logger()
settings = get_settings()

_pool: aioredis.Redis | None = None

T = TypeVar("T")

# Errors that mean the pooled connection is dead — safe to reset and retry once.
_TRANSIENT_REDIS_ERRORS: tuple[type[BaseException], ...] = (
    RedisConnectionError,
    RedisTimeoutError,
    ConnectionResetError,
    BrokenPipeError,
    OSError,
)


class RedisUnavailable(Exception):
    """Redis could not serve a command after reconnect — map to HTTP 503."""


def _is_transient_redis_error(exc: BaseException) -> bool:
    if isinstance(exc, _TRANSIENT_REDIS_ERRORS):
        return True
    # redis-py on a dead asyncio transport (common after idle / network loss on Windows).
    if isinstance(exc, TypeError) and "not callable" in str(exc).lower():
        return True
    return False


def _create_pool() -> aioredis.Redis:
    return aioredis.from_url(
        str(settings.REDIS_URL),
        encoding="utf-8",
        decode_responses=True,
        health_check_interval=30,
        socket_keepalive=True,
        socket_connect_timeout=5,
        retry_on_timeout=True,
        retry_on_error=list(_TRANSIENT_REDIS_ERRORS),
        retry=Retry(ExponentialBackoff(), retries=3),
    )


def get_redis() -> aioredis.Redis:
    """Return the process-wide pool. Prefer redis_execute() for request-path commands."""
    global _pool
    if _pool is None:
        log.warning("redis_lazy_init", hint="call init_redis() from FastAPI lifespan")
        _pool = _create_pool()
    return _pool


async def init_redis() -> None:
    """Create the pool and verify connectivity — call from FastAPI lifespan startup."""
    global _pool
    if _pool is not None:
        await _pool.aclose()
    _pool = _create_pool()
    await _pool.ping()
    log.info("redis_ready")


async def reset_redis() -> None:
    """Drop the current pool so the next init/get creates fresh connections."""
    global _pool
    if _pool is not None:
        try:
            await _pool.aclose()
        except Exception as exc:  # noqa: BLE001
            log.warning("redis_close_error", error=str(exc))
        _pool = None


async def close_redis() -> None:
    """Shutdown hook — close pool on process exit."""
    await reset_redis()
    log.info("redis_closed")


async def redis_execute(fn: Callable[[aioredis.Redis], Awaitable[T]]) -> T:
    """Run a Redis command with one automatic pool reset + retry on stale connections."""
    last_exc: BaseException | None = None
    for attempt in (1, 2):
        try:
            return await fn(get_redis())
        except Exception as exc:
            last_exc = exc
            if not _is_transient_redis_error(exc) or attempt == 2:
                break
            log.warning("redis_connection_reset", attempt=attempt, error=str(exc))
            await reset_redis()
            await init_redis()
    assert last_exc is not None
    if _is_transient_redis_error(last_exc):
        raise RedisUnavailable(str(last_exc)) from last_exc
    raise last_exc


async def redis_ping() -> bool:
    """Readiness probe — resets pool once on transient failure."""

    async def _op(r: aioredis.Redis) -> bool:
        await r.ping()
        return True

    try:
        await redis_execute(_op)
        return True
    except RedisUnavailable as exc:
        log.error("redis_ping_fail", error=str(exc))
        return False


async def redis_incr(key: str) -> int:
    async def _op(r: aioredis.Redis) -> int:
        return await r.incr(key)

    return await redis_execute(_op)


async def redis_expire(key: str, seconds: int) -> None:
    async def _op(r: aioredis.Redis) -> None:
        await r.expire(key, seconds)

    await redis_execute(_op)


async def redis_set(key: str, value: str, *, ex: int | None = None) -> None:
    async def _op(r: aioredis.Redis) -> None:
        await r.set(key, value, ex=ex)

    await redis_execute(_op)


async def redis_delete(key: str) -> int:
    async def _op(r: aioredis.Redis) -> int:
        return await r.delete(key)

    return await redis_execute(_op)


async def redis_getdel(key: str) -> str | None:
    async def _op(r: aioredis.Redis) -> str | None:
        return await r.getdel(key)

    return await redis_execute(_op)
