"""Admin audit trail writer (A-AUDIT-LOG).

Two paths, deliberately different (SPEC_AMENDMENTS §19):

* record_admin_action(): INSERTs into admin_audit_log **inside the caller's
  transaction**. If the mutation rolls back, its audit row rolls back too — the
  table records OUTCOMES, not attempts. The table is append-only at the DB
  level (REVOKE UPDATE/DELETE from puja_app), so this INSERT is the whole API.

* log_admin_attempt(): structlog only, OUT of transaction — for rejected/failed
  actions that must leave a trace even though their DB work rolled back.

`before`/`after` are JSON-serialisable dicts (money as str, never float).
"""
from __future__ import annotations

import datetime as dt
import uuid

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.admin import AdminAuditLog

log = structlog.get_logger()


async def record_admin_action(
    db: AsyncSession,
    *,
    actor_user_id: uuid.UUID,
    action: str,
    entity_type: str,
    entity_id: str | None = None,
    before: dict | None = None,
    after: dict | None = None,
    change_reason: str | None = None,
    ip: str | None = None,
) -> None:
    """Append one audit row in the CALLER'S transaction (commit is the caller's)."""
    db.add(
        AdminAuditLog(
            id=uuid.uuid4(),
            actor_user_id=actor_user_id,
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id) if entity_id is not None else None,
            before_json=before,
            after_json=after,
            change_reason=change_reason,
            ip=ip,
            created_at=dt.datetime.now(dt.UTC),
        )
    )
    log.info(
        "admin_action",
        actor=str(actor_user_id),
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
    )


def log_admin_attempt(
    *,
    actor_user_id: uuid.UUID | None,
    action: str,
    entity_type: str,
    outcome: str,
    reason: str | None = None,
) -> None:
    """Structlog-only trace for rejected/failed admin actions (no DB row)."""
    log.warning(
        "admin_action_rejected",
        actor=str(actor_user_id) if actor_user_id else None,
        action=action,
        entity_type=entity_type,
        outcome=outcome,
        reason=reason,
    )
