"""Sync Celery -> async service bridge (payment_reconcile, tds_accrual)."""
from __future__ import annotations

import asyncio

from sqlalchemy import text

from app.workers.async_bridge import run_async


async def _db_and_redis_roundtrip() -> tuple[int, str]:
    from app.core.redis_client import get_redis
    from app.db.engine import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        async with db.begin():
            value = (await db.execute(text("SELECT 1"))).scalar_one()
    await get_redis().ping()
    return int(value), type(asyncio.get_running_loop()).__name__


def test_run_async_uses_selector_loop_and_survives_repeated_calls(engine):
    """Back-to-back tasks in one worker process must not reuse loop-bound pool connections."""
    results = [run_async(_db_and_redis_roundtrip()) for _ in range(3)]
    assert [value for value, _ in results] == [1, 1, 1]
    assert {loop for _, loop in results} <= {"SelectorEventLoop", "_WindowsSelectorEventLoop", "_UnixSelectorEventLoop"}
