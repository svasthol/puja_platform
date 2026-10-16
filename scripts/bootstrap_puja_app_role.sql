-- Create application DB role for local / prod-like dev (run once as superuser).
-- Then run scripts/apply_grants.sql on every deploy.
--
-- Usage (superuser, e.g. postgres):
--   psql "postgresql://postgres@localhost:5432/postgres" -f scripts/bootstrap_puja_app_role.sql
--   psql "postgresql://postgres@localhost:5432/Mana_Guruji" -f scripts/apply_grants.sql
--
-- Set DATABASE_URL to use puja_app when testing grants:
--   postgresql+psycopg://puja_app:dev_password@localhost:5432/Mana_Guruji
--
-- If you keep DATABASE_URL as postgres, the API still works; apply_grants + puja_app
-- matter for production-like append-only / tax_statutory_config enforcement (R12).

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'puja_app') THEN
        CREATE ROLE puja_app WITH LOGIN PASSWORD 'dev_password';
        RAISE NOTICE 'Created role puja_app (password dev_password — change in prod)';
    ELSE
        RAISE NOTICE 'Role puja_app already exists';
    END IF;
END $$;

-- CONNECT on the app database (adjust name if yours differs).
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_database WHERE datname = 'Mana_Guruji') THEN
        EXECUTE 'GRANT CONNECT ON DATABASE "Mana_Guruji" TO puja_app';
        RAISE NOTICE 'Granted CONNECT on Mana_Guruji to puja_app';
    ELSE
        RAISE NOTICE 'Database Mana_Guruji not found — create it first (createdb Mana_Guruji)';
    END IF;
END $$;
