-- Idempotent role grants — run on EVERY deploy (after migrations), not once.
--
-- WHY THIS FILE EXISTS (SPEC_AMENDMENTS §19 "Audit log integrity"):
-- migrations run once per database. Migration 009's REVOKE block is guarded by
-- a pg_roles check so dev machines (connecting as postgres, no puja_app role)
-- don't abort — but that means a prod database where puja_app was created
-- AFTER 009 ran would silently keep UPDATE on the "append-only" audit tables,
-- with 009 marked applied and nothing alarming. This script is the mechanism
-- prod relies on; the migration guard is only a dev convenience.
--
-- Usage (as a superuser / role owner):
--   psql "$DATABASE_URL" -f scripts/apply_grants.sql
--
-- Fails loudly if puja_app does not exist — that is intentional in prod.

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'puja_app') THEN
        RAISE EXCEPTION
            'role puja_app does not exist. Create it first (see CURSOR_SETUP.md / prod runbook).';
    END IF;
END $$;

-- ---- Baseline: app role reads/writes app tables ----------------------------
GRANT USAGE ON SCHEMA public TO puja_app;
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA public TO puja_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO puja_app;

-- ---- Append-only tables: audit trails must not be rewritable by the app ----
REVOKE UPDATE, DELETE ON admin_audit_log        FROM puja_app;
REVOKE UPDATE, DELETE ON booking_status_history FROM puja_app;

DO $$
BEGIN
    IF to_regclass('pujari_tds_facilitation_ledger') IS NOT NULL THEN
        REVOKE UPDATE, DELETE ON pujari_tds_facilitation_ledger FROM puja_app;
    END IF;
END $$;

-- ---- Statutory tax config: seeded by puja_migrate only (once 007 ships) ----
DO $$
BEGIN
    IF to_regclass('tax_statutory_config') IS NOT NULL THEN
        REVOKE INSERT, UPDATE, DELETE ON tax_statutory_config FROM puja_app;
    END IF;
END $$;

-- ---- Role management: app may assign/remove roles (admin endpoints), -------
-- ---- but the role catalogue itself is migration-owned ----------------------
REVOKE INSERT, UPDATE, DELETE ON roles FROM puja_app;
GRANT  SELECT, INSERT, DELETE ON user_roles TO puja_app;

-- ---- Credential storage: app owns the full lifecycle -----------------------
GRANT SELECT, INSERT, UPDATE, DELETE ON admin_credentials TO puja_app;
