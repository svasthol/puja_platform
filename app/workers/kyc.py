"""KYC expiry + retention purge worker (migration 020)."""
from __future__ import annotations

import os

import psycopg
import structlog

from app.workers.sweep import _normalize_db_url, get_connection

log = structlog.get_logger("kyc_worker")


def expire_kyc_requests(conn: psycopg.Connection) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE kyc_verification_requests
            SET status = 'expired', updated_at = now()
            WHERE status IN ('created', 'authenticated')
              AND expires_at < now()
            """
        )
        n = cur.rowcount
    conn.commit()
    if n:
        log.info("kyc_requests_expired", count=n)
    return n


def refresh_kyc_pending_gauge(conn: psycopg.Connection) -> int:
    from app.monitoring.metrics import set_kyc_pending_docs

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT COUNT(DISTINCT pujari_id)
            FROM pujari_documents
            WHERE is_current = true AND status = 'pending'
            """
        )
        row = cur.fetchone()
        count = int(row[0]) if row else 0
    set_kyc_pending_docs(count)
    return count


def purge_stale_kyc_artifacts(conn: psycopg.Connection, retention_days: int) -> int:
    """Mark expired requests older than retention — S3 purge deferred to ops runbook."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT COUNT(*) FROM kyc_verification_requests
            WHERE status IN ('expired', 'failed')
              AND updated_at < now() - (%s || ' days')::interval
            """,
            (retention_days,),
        )
        row = cur.fetchone()
        count = int(row[0]) if row else 0
    return count


def run_kyc_maintenance(conn: psycopg.Connection, retention_days: int) -> dict:
    return {
        "expired": expire_kyc_requests(conn),
        "pending_docs_gauge": refresh_kyc_pending_gauge(conn),
        "stale_artifact_rows": purge_stale_kyc_artifacts(conn, retention_days),
    }


try:
    from app.workers.celery_app import celery_app

    @celery_app.task(name="app.workers.kyc.expire_kyc_requests_task")
    def expire_kyc_requests_task():
        import redis as redis_lib

        from app.core.config import get_settings

        settings = get_settings()
        r = redis_lib.from_url(str(settings.REDIS_URL))
        if not r.set("kyc_expire_lock", "1", nx=True, ex=120):
            log.info("kyc_expire_skipped_locked")
            return {"skipped": "locked"}

        conn = get_connection()
        try:
            return run_kyc_maintenance(conn, settings.KYC_RETENTION_DAYS)
        finally:
            conn.close()
            r.delete("kyc_expire_lock")

except ImportError:
    pass
