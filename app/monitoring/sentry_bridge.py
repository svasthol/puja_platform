"""Optional Sentry bridge — no-op when SENTRY_DSN unset or sentry-sdk missing."""
from __future__ import annotations

from typing import Any

import structlog

from app.monitoring.registry import AlertSpec

log = structlog.get_logger("monitoring.sentry")
_initialized = False


def init_sentry(dsn: str, *, environment: str) -> None:
    global _initialized
    dsn = (dsn or "").strip()
    if not dsn or not dsn.startswith("https://"):
        if dsn:
            log.warning("sentry_dsn_invalid", hint="SENTRY_DSN must be https://… or empty")
        return
    try:
        import sentry_sdk
        from sentry_sdk.integrations.celery import CeleryIntegration
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.starlette import StarletteIntegration
    except ImportError:
        log.warning("sentry_sdk_not_installed", hint="pip install sentry-sdk")
        return
    try:
        sentry_sdk.init(
            dsn=dsn,
            environment=environment,
            integrations=[
                StarletteIntegration(),
                FastApiIntegration(),
                CeleryIntegration(),
            ],
            traces_sample_rate=0.0,  # ops alerts only; enable APM separately
            send_default_pii=False,
        )
    except Exception as exc:  # noqa: BLE001 — BadDsn, malformed URL, etc.
        log.warning("sentry_init_skipped", error=str(exc))
        return
    _initialized = True
    log.info("sentry_initialized", environment=environment)


def capture_ops_alert(
    spec: AlertSpec,
    subject_id: str,
    payload: dict[str, Any] | None,
) -> None:
    if not _initialized:
        return
    try:
        import sentry_sdk
    except ImportError:
        return
    level = {"info": "info", "warning": "warning", "error": "error", "critical": "fatal"}.get(
        spec.severity, "warning"
    )
    with sentry_sdk.push_scope() as scope:
        scope.set_tag("alert_type", spec.alert_type.value)
        scope.set_tag("layer", spec.layer)
        scope.set_tag("component", spec.component)
        scope.set_tag("subject_type", spec.subject_type)
        scope.set_tag("subject_id", subject_id)
        if payload:
            scope.set_context("payload", payload)
        sentry_sdk.capture_message(
            f"[{spec.alert_type.value}] {spec.description}",
            level=level,
        )
