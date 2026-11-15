"""PR2 — REL-002 post-commit Celery enqueue."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from sqlalchemy import text

from app.db import post_commit


class _FakeSession:
    def __init__(self) -> None:
        self.info: dict = {}


@pytest.mark.asyncio
async def test_flush_post_commit_sends_tasks(monkeypatch):
    sent: list[tuple] = []
    mock_app = MagicMock()

    def _send_task(name, args=None, **kwargs):
        sent.append((name, args, kwargs))

    mock_app.send_task = _send_task
    monkeypatch.setattr("app.workers.celery_app.celery_app", mock_app)

    session = _FakeSession()
    post_commit.enqueue_celery_task(
        session,  # type: ignore[arg-type]
        task_name="app.workers.dispatch.broadcast_booking",
        args=["bid-1"],
    )
    await post_commit.flush_post_commit(session)  # type: ignore[arg-type]

    assert sent == [("app.workers.dispatch.broadcast_booking", ["bid-1"], {})]


@pytest.mark.asyncio
async def test_post_commit_discarded_on_rollback(session, monkeypatch):
    sent: list[str] = []
    mock_app = MagicMock()

    def _send_task(name, args=None, **kwargs):
        sent.append(name)

    mock_app.send_task = _send_task
    monkeypatch.setattr("app.workers.celery_app.celery_app", mock_app)

    try:
        async with session.begin():
            post_commit.enqueue_celery_task(
                session,
                task_name="app.workers.dispatch.broadcast_booking",
                args=["should-not-send"],
            )
            await session.execute(text("SELECT 1"))
            raise RuntimeError("force rollback")
    except RuntimeError:
        pass

    post_commit.discard_post_commit(session)
    await post_commit.flush_post_commit(session)
    assert sent == []