"""Redis client resilience helpers."""
from __future__ import annotations

from app.core.redis_client import RedisUnavailable, _is_transient_redis_error


def test_transient_typeerror_is_stale_transport() -> None:
    assert _is_transient_redis_error(TypeError("'NoneType' object is not callable"))


def test_non_transient_valueerror() -> None:
    assert not _is_transient_redis_error(ValueError("bad key"))


def test_redis_unavailable_is_exception() -> None:
    assert issubclass(RedisUnavailable, Exception)
