"""Run async service code from a sync Celery task — same behaviour on Windows dev and Linux.

Each call gets a fresh `SelectorEventLoop` (psycopg async rejects Windows' default
ProactorEventLoop; Selector is already the Linux default). The process-wide async DB engine
and Redis pool hold connections bound to the loop that opened them, so both are released
before the loop closes — otherwise the next task in the same worker process fails with
"Event loop is closed".
"""
from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any, TypeVar

T = TypeVar("T")


def run_async(coro: Coroutine[Any, Any, T]) -> T:
    async def _main() -> T:
        from app.core.redis_client import reset_redis
        from app.db.engine import engine

        try:
            return await coro
        finally:
            await engine.dispose()
            await reset_redis()

    return asyncio.run(_main(), loop_factory=asyncio.SelectorEventLoop)
