"""B8 — expand_for_pujari only on offline→online (presence absent before SET)."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import text

from app.api.v1.endpoints.pujaris import Heartbeat, heartbeat
from app.core.dependencies import Principal

PUJARI_USER = uuid.UUID("bbbbbbbb-0000-0000-0000-000000000001")


def _principal() -> Principal:
    return Principal(user_id=PUJARI_USER, app_context="pujari", roles=())


@pytest.mark.asyncio
async def test_heartbeat_enqueues_expand_only_when_presence_was_absent(session, seed):
    pid = (
        await session.execute(
            text("SELECT id FROM pujaris WHERE user_id = :u"),
            {"u": str(PUJARI_USER)},
        )
    ).scalar_one()

    with (
        patch("app.api.v1.endpoints.pujaris.redis_get", new_callable=AsyncMock) as mock_get,
        patch("app.api.v1.endpoints.pujaris.redis_set", new_callable=AsyncMock) as mock_set,
        patch("app.api.v1.endpoints.pujaris.post_commit.enqueue_celery_task") as mock_enqueue,
        patch(
            "app.api.v1.endpoints.pujaris.assert_fy_pan_gate_allowed",
            new_callable=AsyncMock,
        ),
    ):
        mock_get.return_value = None
        await heartbeat(body=Heartbeat(), p=_principal(), db=session)
        mock_enqueue.assert_called_once()
        assert mock_enqueue.call_args.kwargs["task_name"] == (
            "app.workers.dispatch.expand_for_pujari"
        )
        assert mock_enqueue.call_args.kwargs["args"] == [str(pid)]

        mock_enqueue.reset_mock()
        mock_get.return_value = "1"
        await heartbeat(body=Heartbeat(), p=_principal(), db=session)
        mock_enqueue.assert_not_called()
        assert mock_set.await_count == 2