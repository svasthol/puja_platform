"""Truncate all booking-related dev data (keeps partners/catalog)."""
from __future__ import annotations

import sys
from pathlib import Path

from app.core.config import get_settings
from app.workers.sweep import get_connection


def _run(flush_redis: bool) -> None:
    sql_path = Path(__file__).parent / "clean_dev_bookings.sql"
    sql = sql_path.read_text(encoding="utf-8")
    settings = get_settings()
    if settings.APP_ENV == "production":
        print("REFUSED: APP_ENV=production", file=sys.stderr)
        sys.exit(1)

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM bookings")
            before = cur.fetchone()[0]
            print(f"bookings before: {before}")
            cur.execute(sql)
            cur.execute("SELECT count(*) FROM bookings")
            after = cur.fetchone()[0]
            cur.execute(
                "SELECT count(*) FROM booking_assignments ba "
                "JOIN status_types st ON st.id = ba.status_id AND st.code = 'offered'"
            )
            offers = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM slot_holds")
            holds = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM payments")
            payments = cur.fetchone()[0]
            print(f"bookings after: {after}")
            print(f"live offers after: {offers}")
            print(f"slot_holds after: {holds}")
            print(f"payments after: {payments}")
        conn.commit()
    finally:
        conn.close()
    print("PostgreSQL: clean_dev_bookings.sql applied.")

    if flush_redis:
        import redis

        for label, url in (
            ("cache", settings.redis_cache_url),
            ("celery", settings.redis_celery_url),
            ("presence", settings.redis_presence_url),
        ):
            r = redis.from_url(str(url), socket_connect_timeout=5)
            r.flushdb()
            print(f"Redis {label}: FLUSHDB on {url}")
        print("Restart Celery worker + Beat after Redis flush.")


def main() -> None:
    flush = "--no-redis" not in sys.argv
    _run(flush_redis=flush)


if __name__ == "__main__":
    main()