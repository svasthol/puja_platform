"""003 — Dual payment models: full_online + advance_balance (raw SQL from spec/db/)

Adds platform_settings, payment_mode columns, amount_due_online/offline,
balance-collection acknowledgement fields, and the CHECK constraints.

DO NOT edit. Changes belong in 004+.
"""
from pathlib import Path
from alembic import op

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None

DB_DIR = Path(__file__).parent.parent.parent / "spec" / "db"


def upgrade() -> None:
    sql = (DB_DIR / "migration_003.sql").read_text()
    op.execute(sql)  # type: ignore[arg-type]


def downgrade() -> None:
    raise NotImplementedError("Migration 003 is irreversible.")
