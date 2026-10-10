"""QA Phase 0 DB state check."""
import psycopg

DSN = "postgresql://postgres:Mahadeva123@localhost:5432/Mana_Guruji"


def main() -> None:
    c = psycopg.connect(DSN)
    cur = c.cursor()

    cur.execute(
        "select count(*) from information_schema.tables where table_schema='public'"
    )
    print("public_tables:", cur.fetchone()[0])

    try:
        cur.execute("select version_num from alembic_version")
        print("alembic_version:", [r[0] for r in cur.fetchall()])
    except Exception as e:  # noqa: BLE001
        print("alembic_version: ERROR", e)
        c.rollback()

    cur.execute(
        "select extname from pg_extension where extname in ('postgis','btree_gist')"
    )
    print("extensions:", [r[0] for r in cur.fetchall()])

    for tbl in ("pujas", "status_types", "service_areas", "relationship_managers",
                "users", "pujaris", "bookings", "admin_users"):
        try:
            cur.execute(f"select count(*) from {tbl}")
            print(f"{tbl}:", cur.fetchone()[0])
        except Exception as e:  # noqa: BLE001
            print(f"{tbl}: MISSING/ERROR", str(e).splitlines()[0])
            c.rollback()

    c.close()


if __name__ == "__main__":
    main()
