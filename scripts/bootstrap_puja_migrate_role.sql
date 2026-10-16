-- Create puja_migrate role (DDL / Alembic owner). Run once as superuser.
-- Extensions (postgis, pgcrypto, btree_gist) require superuser — not this role.
--
-- Usage: python scripts/bootstrap_puja_migrate_role.py
--        (or scripts/bootstrap.sh)

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'puja_migrate') THEN
        CREATE ROLE puja_migrate WITH LOGIN PASSWORD 'dev_password';
        RAISE NOTICE 'Created role puja_migrate (password dev_password — change in prod)';
    ELSE
        RAISE NOTICE 'Role puja_migrate already exists';
    END IF;
END $$;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_database WHERE datname = 'Mana_Guruji') THEN
        EXECUTE 'GRANT CONNECT ON DATABASE "Mana_Guruji" TO puja_migrate';
        RAISE NOTICE 'Granted CONNECT on Mana_Guruji to puja_migrate';
    ELSE
        RAISE NOTICE 'Database Mana_Guruji not found — create it first (createdb Mana_Guruji)';
    END IF;
END $$;
