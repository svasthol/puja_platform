"""
Prometheus metrics (OpenMetrics-compatible).

Uses the default registry so any scraper (Prometheus, Grafana Agent, Datadog
OpenMetrics check, VictoriaMetrics) can scrape ``GET /metrics``.
"""
from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Iterator

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

# ---- Ops alerts (stuck-state + worker events) --------------------------------
OPS_ALERT_EVENTS = Counter(
    "puja_ops_alert_events_total",
    "Ops alert first-occurrence events (log + notify once per open incident)",
    ["alert_type", "layer", "component", "severity"],
)

OPS_ALERT_OPEN = Gauge(
    "puja_ops_alert_open",
    "Currently open ops alerts by type (resolved when condition clears)",
    ["alert_type", "layer", "component"],
)

OPS_SCAN_DURATION = Histogram(
    "puja_ops_scan_duration_seconds",
    "Duration of stuck-state monitor scans",
    ["scanner"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

OPS_SCAN_CANDIDATES = Gauge(
    "puja_ops_scan_candidates",
    "Candidates detected in the latest stuck-state scan (pre-dedupe)",
    ["alert_type"],
)

KYC_PENDING_DOCS = Gauge(
    "puja_kyc_pending_documents",
    "Distinct pujaris with at least one pending current KYC document (M-HEALTH-KYC)",
)


def set_kyc_pending_docs(count: int) -> None:
    KYC_PENDING_DOCS.set(count)

# ---- Instant (non-persisted) counters ----------------------------------------
WEBHOOK_SIGNATURE_FAILURES = Counter(
    "puja_webhook_signature_failures_total",
    "Invalid payment webhook signatures",
    ["provider"],
)

DISPATCH_EXHAUSTED_EVENTS = Counter(
    "puja_dispatch_exhausted_total",
    "Bookings moved to failed_no_pujari",
    ["layer"],
)

REFUND_FAILED_PERMANENT_EVENTS = Counter(
    "puja_refund_failed_permanent_total",
    "Refunds moved to failed_permanent",
    ["layer"],
)

# ---- HTTP layer (API performance) --------------------------------------------
HTTP_REQUESTS = Counter(
    "puja_http_requests_total",
    "HTTP requests served",
    ["method", "route", "status_class"],
)

HTTP_REQUEST_DURATION = Histogram(
    "puja_http_request_duration_seconds",
    "HTTP request latency",
    ["method", "route"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
)


def render_metrics() -> bytes:
    return generate_latest()


def get_metrics_content_type() -> str:
    return CONTENT_TYPE_LATEST


@contextmanager
def observe_scan(scanner: str) -> Iterator[None]:
    start = time.perf_counter()
    try:
        yield
    finally:
        OPS_SCAN_DURATION.labels(scanner=scanner).observe(time.perf_counter() - start)


def set_open_gauge(alert_type: str, layer: str, component: str, value: float) -> None:
    OPS_ALERT_OPEN.labels(alert_type=alert_type, layer=layer, component=component).set(value)


def inc_alert_event(alert_type: str, layer: str, component: str, severity: str) -> None:
    OPS_ALERT_EVENTS.labels(
        alert_type=alert_type,
        layer=layer,
        component=component,
        severity=severity,
    ).inc()
