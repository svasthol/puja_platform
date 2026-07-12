"""006 — Duration guard (P-DUR-GUARD).

Raw SQL from spec/db/migration_006.sql. DO NOT edit. Changes belong in 007+.
"""
from pathlib import Path

from alembic import op

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None

DB_DIR = Path(__file__).parent.parent.parent / "spec" / "db"


def upgrade() -> None:
    sql = (DB_DIR / "migration_006.sql").read_text(encoding="utf-8-sig")
    op.execute(sql)  # type: ignore[arg-type]


def downgrade() -> None:
    raise NotImplementedError("Migration 006 is irreversible.")
