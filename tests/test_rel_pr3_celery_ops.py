"""PR3 slice: Celery ops defaults (REL-007 / reconcile queue)."""

from app.workers.celery_app import celery_app
from app.workers.celery_ops import (
    BROKER_VISIBILITY_TIMEOUT_S,
    SWEEP_HARD_TIME_LIMIT_S,
    SWEEP_SOFT_TIME_LIMIT_S,
)


def test_celery_rel007_defaults():
    conf = celery_app.conf
    assert conf.task_ignore_result is True
    assert conf.broker_transport_options["visibility_timeout"] == BROKER_VISIBILITY_TIMEOUT_S
    assert conf.task_soft_time_limit == 240
    assert conf.task_time_limit == 300

    sweep_ann = conf.task_annotations["app.workers.sweep.sweep_task"]
    assert sweep_ann["soft_time_limit"] == SWEEP_SOFT_TIME_LIMIT_S
    assert sweep_ann["time_limit"] == SWEEP_HARD_TIME_LIMIT_S


def test_payment_reconcile_routed_to_dedicated_queue():
    route = celery_app.conf.task_routes["app.workers.payment_reconcile.*"]
    assert route["queue"] == "reconcile"