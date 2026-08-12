"""009 — Sprint 4-0 security hotfix (P-AUTH-FIX, P-ADMIN-SEED, A-AUDIT-LOG,
A-REASSIGN revoked status, A-PROMO check, P-ADMIN-AUTH credential storage).

Raw SQL from spec/db/migration_009.sql. DO NOT edit. Changes belong in 010+.

Chain note: 007 (tax, Phase 3) and 008 (PLL-GEOM, P2) are reserved spec labels
implemented later; they will chain AFTER this revision. Numbers are spec scope
identifiers, not Alembic order.
"""
from pathlib import Path

from alembic import op

revision = "009"
down_revision = "006"
branch_labels = None
depends_on = None

DB_DIR = Path(__file__).parent.parent.parent / "spec" / "db"


def upgrade() -> None:
    sql = (DB_DIR / "migration_009.sql").read_text(encoding="utf-8-sig")
    op.execute(sql)  # type: ignore[arg-type]


def downgrade() -> None:
    raise NotImplementedError("Migration 009 is irreversible.")
