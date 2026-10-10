"""Ensure Celery task names enqueued via send_task are registered on the app.

Direct Python calls in other tests bypass the broker; this catches missing
@celery_app.task decorators (e.g. broadcast_booking regression in commit 19ca99a).
"""

# Register task modules the same way Celery worker `include=` does at import time.
import app.workers.dispatch  # noqa: F401
import app.workers.notifications  # noqa: F401

from app.workers.celery_app import celery_app

_ENQUEUED_DISPATCH_TASKS = (
    "app.workers.dispatch.broadcast_booking",
    "app.workers.dispatch.rebroadcast_booking",
    "app.workers.dispatch.direct_dispatch",
)

_ENQUEUED_NOTIFY_TASKS = (
    "app.workers.notifications.notify_offers",
)


def test_dispatch_tasks_registered_on_celery_app():
    for name in _ENQUEUED_DISPATCH_TASKS:
        assert name in celery_app.tasks, f"missing Celery task registration: {name}"


def test_notification_tasks_registered_on_celery_app():
    for name in _ENQUEUED_NOTIFY_TASKS:
        assert name in celery_app.tasks, f"missing Celery task registration: {name}"
