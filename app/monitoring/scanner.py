"""Sweep-time stuck-state monitor (P-MONITOR)."""
from __future__ import annotations

from collections import defaultdict

import psycopg
import structlog

from app.core.config import Settings, get_settings
from app.monitoring.emit import AlertCandidate, record_ops_alert_sync
from app.monitoring.metrics import OPS_SCAN_CANDIDATES, observe_scan, set_open_gauge
from app.monitoring.registry import AlertType, get_alert_spec
from app.monitoring.stuck_state import (
    detect_refund_stalls,
    detect_stuck_confirmed_no_show,
    detect_stuck_payment_pending,
)

log = structlog.get_logger("monitoring.scanner")


def _sync_booking_no_show_legacy(conn: psycopg.Connection, booking_id: str) -> None:
    """Keep booking_no_show_alerts (mig 015) in sync for admin/reporting queries."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO booking_no_show_alerts (booking_id, ops_alert_sent_at)
            VALUES (%s, now())
            ON CONFLICT (booking_id) DO NOTHING
            """,
            (booking_id,),
        )
    conn.commit()


def _resolve_cleared(
    conn: psycopg.Connection,
    *,
    alert_type: AlertType,
    active_subject_ids: set[str],
) -> int:
    spec = get_alert_spec(alert_type)
    with conn.cursor() as cur:
        if active_subject_ids:
            cur.execute(
                """
                UPDATE ops_monitor_alerts
                SET resolved_at = now()
                WHERE alert_type = %s
                  AND subject_type = %s
                  AND resolved_at IS NULL
                  AND subject_id::text <> ALL(%s)
                RETURNING subject_id
                """,
                (spec.alert_type.value, spec.subject_type, list(active_subject_ids)),
            )
        else:
            cur.execute(
                """
                UPDATE ops_monitor_alerts
                SET resolved_at = now()
                WHERE alert_type = %s
                  AND subject_type = %s
                  AND resolved_at IS NULL
                RETURNING subject_id
                """,
                (spec.alert_type.value, spec.subject_type),
            )
        resolved = cur.rowcount
    conn.commit()
    return resolved


def _count_open(conn: psycopg.Connection, alert_type: AlertType) -> int:
    spec = get_alert_spec(alert_type)
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT count(*) FROM ops_monitor_alerts
            WHERE alert_type = %s AND subject_type = %s AND resolved_at IS NULL
            """,
            (spec.alert_type.value, spec.subject_type),
        )
        row = cur.fetchone()
    return int(row[0]) if row else 0


def _refresh_open_gauges(conn: psycopg.Connection) -> None:
    for alert_type in (
        AlertType.STUCK_PAYMENT_PENDING,
        AlertType.STUCK_CONFIRMED_NO_SHOW,
        AlertType.REFUND_STALL,
    ):
        spec = get_alert_spec(alert_type)
        set_open_gauge(
            spec.alert_type.value,
            spec.layer,
            spec.component,
            float(_count_open(conn, alert_type)),
        )


def run_stuck_state_monitor(
    conn: psycopg.Connection,
    settings: Settings | None = None,
) -> dict:
    """
    Scan DB for stuck conditions; upsert ops_monitor_alerts; emit on first_seen.

    Called from sweep every 30s. Idempotent and self-healing (auto-resolve).
    """
    cfg = settings or get_settings()
    payment_ttl = cfg.BOOKING_PAYMENT_TTL_MINUTES
    payment_grace = cfg.MONITOR_PAYMENT_PENDING_GRACE_MINUTES
    no_show_grace = cfg.MONITOR_CONFIRMED_NO_SHOW_GRACE_MINUTES
    refund_stall_attempts = cfg.MONITOR_REFUND_STALL_ATTEMPTS

    summary: dict = {
        "stuck_payment_pending": [],
        "stuck_confirmed_no_show": [],
        "refund_stall": [],
        "resolved": 0,
    }
    active_by_type: dict[AlertType, set[str]] = defaultdict(set)

    with observe_scan("stuck_state"):
        with conn.cursor() as cur:
            payment_hits = detect_stuck_payment_pending(
                cur, payment_ttl_minutes=payment_ttl, grace_minutes=payment_grace
            )
            confirmed_hits = detect_stuck_confirmed_no_show(cur, grace_minutes=no_show_grace)
            refund_hits = detect_refund_stalls(cur, min_attempts=refund_stall_attempts)
        conn.commit()

        OPS_SCAN_CANDIDATES.labels(
            alert_type=AlertType.STUCK_PAYMENT_PENDING.value
        ).set(len(payment_hits))
        OPS_SCAN_CANDIDATES.labels(
            alert_type=AlertType.STUCK_CONFIRMED_NO_SHOW.value
        ).set(len(confirmed_hits))
        OPS_SCAN_CANDIDATES.labels(alert_type=AlertType.REFUND_STALL.value).set(len(refund_hits))

        for hit in payment_hits:
            active_by_type[hit.alert_type].add(hit.subject_id)
            if record_ops_alert_sync(
                conn,
                AlertCandidate(
                    alert_type=hit.alert_type,
                    subject_id=hit.subject_id,
                    payload=hit.payload,
                ),
            ):
                summary["stuck_payment_pending"].append(hit.subject_id)

        for hit in confirmed_hits:
            active_by_type[hit.alert_type].add(hit.subject_id)
            first = record_ops_alert_sync(
                conn,
                AlertCandidate(
                    alert_type=hit.alert_type,
                    subject_id=hit.subject_id,
                    payload=hit.payload,
                ),
            )
            if first:
                summary["stuck_confirmed_no_show"].append(hit.subject_id)
            _sync_booking_no_show_legacy(conn, hit.subject_id)

        for hit in refund_hits:
            active_by_type[hit.alert_type].add(hit.subject_id)
            if record_ops_alert_sync(
                conn,
                AlertCandidate(
                    alert_type=hit.alert_type,
                    subject_id=hit.subject_id,
                    payload=hit.payload,
                ),
            ):
                summary["refund_stall"].append(hit.subject_id)

        for alert_type in (
            AlertType.STUCK_PAYMENT_PENDING,
            AlertType.STUCK_CONFIRMED_NO_SHOW,
            AlertType.REFUND_STALL,
        ):
            summary["resolved"] += _resolve_cleared(
                conn,
                alert_type=alert_type,
                active_subject_ids=active_by_type.get(alert_type, set()),
            )

        _refresh_open_gauges(conn)

    log.info(
        "stuck_state_scan_complete",
        **{k: v for k, v in summary.items() if k != "resolved"},
        resolved_count=summary["resolved"],
    )
    return summary
