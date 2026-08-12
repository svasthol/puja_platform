"""011 — Sprint 4B Wave-0: catalogue content model (SPEC_AMENDMENTS §20).

Raw SQL from spec/db/migration_011.sql.
"""
from pathlib import Path

from alembic import op

revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None

DB_DIR = Path(__file__).parent.parent.parent / "spec" / "db"


def upgrade() -> None:
    sql = (DB_DIR / "migration_011.sql").read_text(encoding="utf-8-sig")
    op.execute(sql)  # type: ignore[arg-type]


def downgrade() -> None:
    raise NotImplementedError("Migration 011 is irreversible.")
