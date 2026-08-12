"""P-SWEEP-CONFIRMED — backward-compatible alias for stuck confirmed scan."""
from __future__ import annotations

import psycopg

from app.monitoring.scanner import run_stuck_state_monitor


def flag_stuck_confirmed_bookings(
    conn: psycopg.Connection, *, grace_minutes: int = 90
) -> list[str]:
    """Deprecated: use ``run_stuck_state_monitor``. Returns newly alerted booking ids."""
    _ = grace_minutes  # configured via MONITOR_CONFIRMED_NO_SHOW_GRACE_MINUTES
    return run_stuck_state_monitor(conn).get("stuck_confirmed_no_show", [])
