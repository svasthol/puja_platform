"""004 — Persist Razorpay order id on bookings (idempotent checkout resume).

Adds bookings.razorpay_order_id + partial unique index. Raw SQL from spec/db/.

DO NOT edit. Changes belong in 005+.
"""
from pathlib import Path

from alembic import op

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None

DB_DIR = Path(__file__).parent.parent.parent / "spec" / "db"


def upgrade() -> None:
    sql = (DB_DIR / "migration_004.sql").read_text()
    op.execute(sql)  # type: ignore[arg-type]


def downgrade() -> None:
    raise NotImplementedError("Migration 004 is irreversible.")
