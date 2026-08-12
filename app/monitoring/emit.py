"""Persisted + instant ops-alert emission."""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Any

import psycopg
import structlog

from app.monitoring.metrics import (
    DISPATCH_EXHAUSTED_EVENTS,
    REFUND_FAILED_PERMANENT_EVENTS,
    WEBHOOK_SIGNATURE_FAILURES,
    inc_alert_event,
)
from app.monitoring.registry import AlertSpec, AlertType, get_alert_spec
from app.monitoring.sentry_bridge import capture_ops_alert

log = structlog.get_logger("monitoring")


@dataclass(frozen=True, slots=True)
class AlertCandidate:
    alert_type: AlertType
    subject_id: str
    payload: dict[str, Any] | None = None


def _emit_log(
    *,
    spec: AlertSpec,
    subject_id: str,
    first_seen: bool,
    occurrence_count: int,
    payload: dict[str, Any] | None,
) -> None:
    fields: dict[str, Any] = {
        "event": "ops_alert",
        "alert_type": spec.alert_type.value,
        "severity": spec.severity,
        "layer": spec.layer,
        "component": spec.component,
        "subject_type": spec.subject_type,
        "subject_id": subject_id,
        "first_seen": first_seen,
        "occurrence_count": occurrence_count,
        "description": spec.description,
    }
    if payload:
        fields["payload"] = payload
    log_method = log.warning if spec.severity in ("warning", "error", "critical") else log.info
    log_method(**fields)
    if first_seen:
        inc_alert_event(
            spec.alert_type.value,
            spec.layer,
            spec.component,
            spec.severity,
        )
        capture_ops_alert(spec, subject_id, payload)


def _upsert_open_alert(
    cur: psycopg.Cursor,
    *,
    spec: AlertSpec,
    subject_id: str,
    payload: dict[str, Any] | None,
) -> tuple[bool, int]:
    """Returns (first_seen, occurrence_count)."""
    payload_json = json.dumps(payload) if payload else None
    cur.execute(
        """
        INSERT INTO ops_monitor_alerts (
            alert_type, subject_type, subject_id, severity, layer, component, payload
        ) VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)
        ON CONFLICT (alert_type, subject_type, subject_id) WHERE resolved_at IS NULL
        DO UPDATE SET
            last_seen_at = now(),
            occurrence_count = ops_monitor_alerts.occurrence_count + 1,
            payload = COALESCE(EXCLUDED.payload, ops_monitor_alerts.payload)
        RETURNING occurrence_count, (occurrence_count = 1) AS first_seen
        """,
        (
            spec.alert_type.value,
            spec.subject_type,
            subject_id,
            spec.severity,
            spec.layer,
            spec.component,
            payload_json,
        ),
    )
    row = cur.fetchone()
    if row is None:
        return False, 0
    return bool(row[1]), int(row[0])


def record_ops_alert_sync(
    conn: psycopg.Connection,
    candidate: AlertCandidate,
) -> bool:
    """Persist alert; emit structured log on first_seen. Returns first_seen."""
    spec = get_alert_spec(candidate.alert_type)
    with conn.cursor() as cur:
        first_seen, occurrence_count = _upsert_open_alert(
            cur,
            spec=spec,
            subject_id=candidate.subject_id,
            payload=candidate.payload,
        )
    conn.commit()
    if first_seen:
        _emit_log(
            spec=spec,
            subject_id=candidate.subject_id,
            first_seen=True,
            occurrence_count=occurrence_count,
            payload=candidate.payload,
        )
    return first_seen


async def record_ops_alert(
    conn: psycopg.Connection,
    candidate: AlertCandidate,
) -> bool:
    return record_ops_alert_sync(conn, candidate)


def emit_instant_alert(
    alert_type: AlertType,
    *,
    subject_id: str | None = None,
    payload: dict[str, Any] | None = None,
    provider: str | None = None,
) -> None:
    """
  Instant alert — no DB row (e.g. webhook signature failure before parse).

  Still emits structured log + Prometheus counter for all monitoring backends.
  """
    spec = get_alert_spec(alert_type)
    sid = subject_id or str(uuid.uuid4())
    if alert_type is AlertType.WEBHOOK_SIGNATURE_INVALID:
        WEBHOOK_SIGNATURE_FAILURES.labels(provider=provider or "razorpay").inc()
    elif alert_type is AlertType.DISPATCH_EXHAUSTED:
        DISPATCH_EXHAUSTED_EVENTS.labels(layer=spec.layer).inc()
    elif alert_type is AlertType.REFUND_FAILED_PERMANENT:
        REFUND_FAILED_PERMANENT_EVENTS.labels(layer=spec.layer).inc()
    inc_alert_event(spec.alert_type.value, spec.layer, spec.component, spec.severity)
    _emit_log(
        spec=spec,
        subject_id=sid,
        first_seen=True,
        occurrence_count=1,
        payload=payload,
    )
