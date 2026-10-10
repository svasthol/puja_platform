"""QA Phase 0 - verify migration-gated tables/columns + admin auth tables."""
import psycopg

DSN = "postgresql://postgres:Mahadeva123@localhost:5432/Mana_Guruji"


def main() -> None:
    c = psycopg.connect(DSN)
    cur = c.cursor()

    # migration-gated tables
    tables = [
        "panchangam_daily",        # 017
        "worker_heartbeats",       # 024
        "tax_statutory_config",    # 027/028
        "tds_accrual_intents",     # 027
        "booking_dispatch_state",  # dispatch v2
        "admin_audit_log",         # 009
        "user_roles", "roles",     # admin rbac
        "admin_credentials",       # admin totp (guess)
        "pujari_documents",        # kyc
        "refunds", "payments", "payment_splits",
    ]
    for t in tables:
        cur.execute(
            "select exists(select 1 from information_schema.tables "
            "where table_schema='public' and table_name=%s)", (t,))
        print(f"table {t}:", cur.fetchone()[0])

    # booking_class column (014)
    cur.execute(
        "select column_name from information_schema.columns "
        "where table_name='bookings' and column_name in "
        "('booking_class','intended_pujari_id','cancelled_at','paid_at','relationship_manager_id')")
    print("bookings cols:", sorted(r[0] for r in cur.fetchall()))

    # find any table with 'admin' or 'credential' or 'totp' in name
    cur.execute(
        "select table_name from information_schema.tables where table_schema='public' "
        "and (table_name ilike '%admin%' or table_name ilike '%credential%' or table_name ilike '%totp%' or table_name ilike '%role%') order by 1")
    print("admin/role tables:", [r[0] for r in cur.fetchall()])

    c.close()


if __name__ == "__main__":
    main()
