"""Celery resilience helpers (REL-007) — task failure hook + conf defaults."""
from __future__ import annotations

import structlog
from celery.signals import task_failure

from app.core.config import get_settings

log = structlog.get_logger(__name__)

# Below app.workers.sweep.SWEEP_LOCK_TTL_SECONDS (90).
SWEEP_SOFT_TIME_LIMIT_S = 60
SWEEP_HARD_TIME_LIMIT_S = 80

DEFAULT_SOFT_TIME_LIMIT_S = 240
DEFAULT_HARD_TIME_LIMIT_S = 300

# Repo has no countdown/eta tasks today (PR3 CI guard in hardening plan).
BROKER_VISIBILITY_TIMEOUT_S = 900


def sweep_task_time_limits() -> dict[str, int]:
    return {
        "soft_time_limit": SWEEP_SOFT_TIME_LIMIT_S,
        "time_limit": SWEEP_HARD_TIME_LIMIT_S,
    }


@task_failure.connect
def _log_task_failure(
    sender=None,
    task_id=None,
    exception=None,
    args=None,
    kwargs=None,
    traceback=None,
    einfo=None,
    **_,
) -> None:
    task_name = getattr(sender, "name", None) or str(sender)
    settings = get_settings()
    log.error(
        "celery_task_failed",
        task=task_name,
        task_id=task_id,
        error=str(exception),
        args=args,
        kwargs=kwargs,
        app_env=settings.APP_ENV,
    )