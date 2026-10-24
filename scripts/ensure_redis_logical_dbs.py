"""Verify and bootstrap Redis logical DB indices (no CREATE DATABASE — Redis uses /0, /1, /2).

Usage (staging / CI):
  set -a && source /etc/mana-guruji/api.env && set +a
  python scripts/ensure_redis_logical_dbs.py --strict

Reads REDIS_URL host + REDIS_DB_CACHE, REDIS_DB_CELERY, REDIS_DB_PRESENCE from env.
"""
from __future__ import annotations

import argparse
import os
import sys

MARKER_KEY = "mana_guruji:logical_db_bootstrap"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true", help="Exit 1 on failure")
    args = parser.parse_args()

    try:
        import redis
    except ImportError:
        print("redis package required (pip install redis)", file=sys.stderr)
        return 2

    # Import after env is loaded
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from app.core.config import get_settings

    settings = get_settings()
    dbs = {
        "cache": settings.REDIS_DB_CACHE,
        "celery": settings.REDIS_DB_CELERY,
        "presence": settings.REDIS_DB_PRESENCE,
    }
    host = urlparse_host(str(settings.REDIS_URL))
    print(f"ensure_redis_logical_dbs: host={host} indices={dbs}")

    failed = False
    for label, db_index in dbs.items():
        url = settings.redis_url_for_db(db_index)
        try:
            client = redis.from_url(url, decode_responses=True, socket_connect_timeout=5)
            pong = client.ping()
            client.set(MARKER_KEY, label, nx=True)
            print(f"  OK db={db_index} ({label}) ping={pong} url={url}")
        except Exception as exc:
            failed = True
            print(f"  FAIL db={db_index} ({label}): {exc}", file=sys.stderr)

    if failed:
        if args.strict:
            return 1
        return 0
    print("ensure_redis_logical_dbs: OK")
    return 0


def urlparse_host(redis_url: str) -> str:
    from urllib.parse import urlparse

    p = urlparse(redis_url)
    return p.hostname or redis_url


if __name__ == "__main__":
    raise SystemExit(main())
