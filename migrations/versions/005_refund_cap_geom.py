"""005 — Refund sum cap + address geom sync.

Raw SQL from spec/db/migration_005.sql. DO NOT edit. Changes belong in 006+.
"""
from pathlib import Path

from alembic import op

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None

DB_DIR = Path(__file__).parent.parent.parent / "spec" / "db"


def upgrade() -> None:
    sql = (DB_DIR / "migration_005.sql").read_text(encoding="utf-8-sig")
    op.execute(sql)  # type: ignore[arg-type]


def downgrade() -> None:
    raise NotImplementedError("Migration 005 is irreversible.")
