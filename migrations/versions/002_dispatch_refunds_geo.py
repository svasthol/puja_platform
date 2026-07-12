"""002 — Dispatch state, refunds, geo, cancel-guard trigger (raw SQL from spec/db/)

Requires PostGIS. On macOS: brew install postgis.
On Windows: PostgreSQL Stack Builder → Spatial Extensions → PostGIS.
On Linux: apt install postgresql-16-postgis-3

DO NOT edit. Changes belong in 004+.
"""
from pathlib import Path
from alembic import op

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None

DB_DIR = Path(__file__).parent.parent.parent / "spec" / "db"


def upgrade() -> None:
    sql = (DB_DIR / "migration_002.sql").read_text()
    op.execute(sql)  # type: ignore[arg-type]


def downgrade() -> None:
    raise NotImplementedError("Migration 002 is irreversible.")
