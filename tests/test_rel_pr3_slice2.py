"""PR3 slice 2 — RedBeat (REL-008) + notification acks + worker guard."""

import re
from pathlib import Path

from app.workers.celery_app import celery_app
from app.workers.celery_ops import (
    NOTIFICATION_TASK_NAMES,
    REDBEAT_LOCK_TIMEOUT_S,
    REDBEAT_MAX_LOOP_INTERVAL_S,
    notification_task_annotations,
    redbeat_conf,
)

ROOT = Path(__file__).resolve().parents[1]
WORKERS = ROOT / "app" / "workers"


def test_redbeat_rel008_config():
    assert celery_app.conf.beat_scheduler == "redbeat.RedBeatScheduler"
    assert celery_app.conf.redbeat_lock_timeout == REDBEAT_LOCK_TIMEOUT_S
    assert celery_app.conf.beat_max_loop_interval == REDBEAT_MAX_LOOP_INTERVAL_S
    assert str(celery_app.conf.redbeat_key_prefix).endswith(":redbeat:")
    sample = redbeat_conf(app_env="staging", redis_url="redis://127.0.0.1:6379/1")
    assert sample["redbeat_key_prefix"] == "staging:redbeat:"


def test_notification_tasks_ack_early():
    ann = notification_task_annotations()
    assert len(ann) == len(NOTIFICATION_TASK_NAMES)
    for name in NOTIFICATION_TASK_NAMES:
        key = f"app.workers.notifications.{name}"
        assert ann[key] == {"acks_late": False}
        merged = celery_app.conf.task_annotations[key]
        assert merged.get("acks_late") is False


def test_workers_do_not_use_countdown_or_eta():
    """visibility_timeout=900 is safe only while no delayed tasks exist under app/workers."""
    pattern = re.compile(r"\b(countdown\s*=|\.apply_async\s*\([^)]*eta\s*=)")
    hits: list[str] = []
    for path in WORKERS.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if pattern.search(text):
            hits.append(str(path.relative_to(ROOT)))
    assert hits == [], f"disallowed delayed task usage: {hits}"