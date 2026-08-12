"""
Central Celery application — the single entry point for all workers and beat.

Start workers:
    celery -A app.workers.celery_app worker --loglevel=info -Q sweep,dispatch,refund,notifications
Start scheduler:
    celery -A app.workers.celery_app beat --loglevel=info

Task modules are registered via `include` below. Every task lives under
app.workers.* so the task name always matches the import path.
"""
from celery import Celery
from celery.signals import setup_logging, worker_process_init

from app.core.config import get_settings
from app.core.logging import configure_logging

settings = get_settings()


@setup_logging.connect
def _configure_celery_logging(**_kwargs) -> None:
    """Same structlog config as the API — JSON in prod, console in dev."""
    configure_logging(debug=settings.DEBUG)


@worker_process_init.connect
def _configure_worker_process_logging(**_kwargs) -> None:
    """Re-apply after prefork pool fork so child workers emit structured logs."""
    configure_logging(debug=settings.DEBUG)


# Celery Beat runs in this process (no fork) — ensure logging is ready at import.
configure_logging(debug=settings.DEBUG)

celery_app = Celery(
    "mana_guruji",
    broker=str(settings.REDIS_URL),
    backend=str(settings.REDIS_URL),
    include=[
        "app.workers.sweep",
        "app.workers.dispatch",
        "app.workers.refund",
        "app.workers.notifications",
        "app.workers.advance_offers",
        "app.workers.urgency_flip",
        "app.workers.rm_escalation",
        "app.workers.panchangam",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone=settings.PLATFORM_TIMEZONE,
    enable_utc=True,
    task_acks_late=True,               # redeliver on worker crash (tasks are idempotent)
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,      # fair dispatch for long-ish tasks
    task_default_queue="sweep",
    task_routes={
        "app.workers.sweep.*": {"queue": "sweep"},
        "app.workers.advance_offers.*": {"queue": "sweep"},
        "app.workers.urgency_flip.*": {"queue": "sweep"},
        "app.workers.rm_escalation.*": {"queue": "sweep"},
        "app.workers.dispatch.*": {"queue": "dispatch"},
        "app.workers.refund.*": {"queue": "refund"},
        "app.workers.notifications.*": {"queue": "notifications"},
        "app.workers.panchangam.*": {"queue": "sweep"},
    },
    beat_schedule={
        "sweep-every-30s": {
            "task": "app.workers.sweep.sweep_task",
            "schedule": 30.0,
        },
        "refresh-advance-offers-every-5m": {
            "task": "app.workers.advance_offers.refresh_advance_offers_task",
            "schedule": 300.0,
            "options": {"queue": "sweep"},
        },
        "escalate-urgency-every-2m": {
            "task": "app.workers.urgency_flip.escalate_urgency_on_threshold_task",
            "schedule": 120.0,
            "options": {"queue": "sweep"},
        },
        "rm-escalation-scan-every-15m": {
            "task": "app.workers.rm_escalation.rm_escalation_scan_task",
            "schedule": 900.0,
            "options": {"queue": "sweep"},
        },
        "process-refunds-every-60s": {
            "task": "app.workers.refund.process_refunds",
            "schedule": 60.0,
            "options": {"queue": "refund"},
        },
        "refresh-panchangam-daily": {
            "task": "app.workers.panchangam.refresh_panchangam_cache_task",
            "schedule": 3600.0,
            "options": {"queue": "sweep"},
        },
    },
)
