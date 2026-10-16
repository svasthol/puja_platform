"""Create puja_migrate role, DDL grants, and default privileges for puja_app."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from urllib.parse import urlparse, urlunparse

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

try:
    import psycopg
except ImportError:
    print("psycopg not installed — activate .venv first", file=sys.stderr)
    sys.exit(1)

APP_DB = "Mana_Guruji"


def _sync_url(database: str | None = None) -> str:
    url = os.environ.get(
        "DATABASE_URL", "postgresql://postgres@127.0.0.1:5433/Mana_Guruji"
    )
    url = url.replace("postgresql+psycopg://", "postgresql://").replace(
        "postgresql+asyncpg://", "postgresql://"
    )
    if database is None:
        return url
    parsed = urlparse(url)
    return urlunparse(parsed._replace(path=f"/{database}"))


def main() -> None:
    sql_path = Path(__file__).resolve().parent / "bootstrap_puja_migrate_role.sql"
    with psycopg.connect(_sync_url(), autocommit=True) as conn:
        conn.execute(sql_path.read_text(encoding="utf-8"))

    grants_and_defaults = """
    GRANT CREATE, USAGE ON SCHEMA public TO puja_migrate;
    GRANT ALL ON ALL TABLES IN SCHEMA public TO puja_migrate;
    GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO puja_migrate;

    ALTER DEFAULT PRIVILEGES FOR ROLE puja_migrate IN SCHEMA public
        GRANT SELECT, INSERT, UPDATE ON TABLES TO puja_app;
    ALTER DEFAULT PRIVILEGES FOR ROLE puja_migrate IN SCHEMA public
        GRANT USAGE, SELECT ON SEQUENCES TO puja_app;
    """
    try:
        with psycopg.connect(_sync_url(APP_DB), autocommit=True) as conn:
            conn.execute(grants_and_defaults)
    except psycopg.OperationalError as exc:
        print(f"bootstrap_puja_migrate_role: role OK; app-DB grants skipped ({exc})")
        print(f"Next: create {APP_DB}, re-run scripts/bootstrap.sh")
        return

    print(
        "bootstrap_puja_migrate_role: OK "
        "(puja_migrate + DDL grants + default privileges for puja_app)"
    )
    print("Next: extensions as superuser; alembic/migrations as puja_migrate; API as puja_app")


if __name__ == "__main__":
    main()
