"""
Vendor-neutral observability (P-MONITOR).

Exports a single ops-alert API consumed by API handlers, Celery workers, and
the sweep scanner. Emits:

* Structured JSON logs (`event=ops_alert`) — Datadog, Loki, CloudWatch, ELK
* Prometheus counters/gauges/histograms — Grafana, Datadog agent, VictoriaMetrics
* Optional Sentry events when ``SENTRY_DSN`` is set

Layer taxonomy: ``api`` | ``worker`` | ``sweep`` | ``data``
Component taxonomy: ``booking`` | ``payment`` | ``refund`` | ``dispatch`` | ``webhook``
"""
from app.monitoring.emit import emit_instant_alert, record_ops_alert, record_ops_alert_sync
from app.monitoring.metrics import get_metrics_content_type, render_metrics
from app.monitoring.registry import AlertType, get_alert_spec
from app.monitoring.scanner import run_stuck_state_monitor

__all__ = [
    "AlertType",
    "emit_instant_alert",
    "get_alert_spec",
    "get_metrics_content_type",
    "record_ops_alert",
    "record_ops_alert_sync",
    "render_metrics",
    "run_stuck_state_monitor",
]
