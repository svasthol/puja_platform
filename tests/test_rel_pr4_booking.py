"""PR4 — REL-020 DB retry mapping (REL-013 covered by booking unit tests)."""

from __future__ import annotations

from psycopg.errors import DeadlockDetected, LockNotAvailable

from app.core.exceptions import map_db_error


def test_rel020_lock_errors_map_503():
    for exc in (LockNotAvailable("lock"), DeadlockDetected("deadlock")):
        resp = map_db_error(exc, "/v1/bookings")
        assert resp.status_code == 503
        assert b"DB_RETRY" in resp.body