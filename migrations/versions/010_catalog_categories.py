"""010 — Sprint 4B: puja_categories.is_active for admin soft-disable.

Raw SQL from spec/db/migration_010.sql.
"""
from pathlib import Path

from alembic import op

revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None

DB_DIR = Path(__file__).parent.parent.parent / "spec" / "db"


def upgrade() -> None:
    sql = (DB_DIR / "migration_010.sql").read_text(encoding="utf-8-sig")
    op.execute(sql)  # type: ignore[arg-type]


def downgrade() -> None:
    op.execute("ALTER TABLE puja_categories DROP COLUMN IF EXISTS is_active")
