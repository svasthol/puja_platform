"""Shared Redis key builders — API and Celery workers must stay identical."""


def presence_redis_key(pujari_id: object) -> str:
    """TTL heartbeat key for dispatch eligibility (`MGET` in dispatch worker)."""
    return f"presence:{pujari_id!s}"
