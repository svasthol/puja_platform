"""Queue Celery tasks until the request transaction commits (REL-002)."""
from __future__ import annotations

from typing import Any

import anyio
from sqlalchemy.ext.asyncio import AsyncSession

_QUEUE_KEY = "post_commit"


def enqueue_celery_task(
    session: AsyncSession,
    *,
    task_name: str,
    args: list[Any] | None = None,
    kwargs: dict[str, Any] | None = None,
) -> None:
    """Append a Celery send_task call to run only after a successful get_db_txn commit."""
    queue: list[tuple[str, list[Any], dict[str, Any]]] = session.info.setdefault(_QUEUE_KEY, [])
    queue.append((task_name, list(args or []), dict(kwargs or {})))


def discard_post_commit(session: AsyncSession) -> None:
    session.info.pop(_QUEUE_KEY, None)


async def flush_post_commit(session: AsyncSession) -> None:
    """Run queued send_task calls on a worker thread (non-blocking for the event loop)."""
    queued = session.info.pop(_QUEUE_KEY, [])
    if not queued:
        return
    from app.workers.celery_app import celery_app

    def _send(task_name: str, args: list[Any], kwargs: dict[str, Any]) -> None:
        celery_app.send_task(task_name, args=args, **kwargs)

    for task_name, args, kwargs in queued:
        await anyio.to_thread.run_sync(_send, task_name, args, kwargs)


def flush_post_commit_sync(session: AsyncSession) -> None:
    """Sync flush for workers that already committed outside get_db_txn."""
    queued = session.info.pop(_QUEUE_KEY, [])
    if not queued:
        return
    from app.workers.celery_app import celery_app

    for task_name, args, kwargs in queued:
        celery_app.send_task(task_name, args=args, **kwargs)