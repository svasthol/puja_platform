"""TDS accrual intent processor (§0.S decouple — D1/D3/R4)."""
from __future__ import annotations

import asyncio

import structlog

from app.workers.celery_app import celery_app

log = structlog.get_logger("tds_accrual")


async def _process_batch(limit: int) -> dict[str, int]:
    from app.db.engine import AsyncSessionLocal
    from app.services import tds_accrual_service

    async with AsyncSessionLocal() as db:
        async with db.begin():
            return await tds_accrual_service.process_pending_accrual_intents(db, limit=limit)


@celery_app.task(name="app.workers.tds_accrual.process_tds_accrual_intents")
def process_tds_accrual_intents(batch: int = 50) -> dict[str, int]:
    result = asyncio.run(_process_batch(batch))
    if any(result.values()):
        log.info("tds_accrual_batch_done", **result)
    return result


async def _sweep_no_show(limit: int) -> dict[str, int]:
    from app.db.engine import AsyncSessionLocal
    from app.services.tds_v3_reversal_service import sweep_never_collected_facilitation

    async with AsyncSessionLocal() as db:
        async with db.begin():
            return await sweep_never_collected_facilitation(db, limit=limit)


@celery_app.task(name="app.workers.tds_accrual.sweep_never_collected_tds")
def sweep_never_collected_tds(batch: int = 50) -> dict[str, int]:
    result = asyncio.run(_sweep_no_show(batch))
    if any(result.values()):
        log.info("tds_no_show_sweep_done", **result)
    return result
