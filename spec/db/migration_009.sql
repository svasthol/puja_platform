-- Migration 009 — Sprint 4-0 security hotfix + Phase 4 control-plane DDL.
-- Apply after 006. See spec/plans/SPEC_AMENDMENTS.md §19, spec/plans/ADMIN.md Sprint 4-0.
--
-- NOTE ON NUMBERING: 007 (tax) and 008 (PLL-GEOM) are reserved scope labels that
-- ship later (Phase 3 / P2). The Alembic chain is 006 -> 009; 007/008 will chain
-- after 009 when implemented. Numbers are spec identifiers, not execution order.
--
-- Idempotent throughout: safe to re-apply on a database where parts already exist
-- (conftest applies spec/db/*.sql directly; Alembic applies this same file once).

-- ============================================================================
-- 1. P-AUTH-FIX — refresh session lookup key
-- ----------------------------------------------------------------------------
-- refresh/logout previously matched refresh_token_hash == hash_secret(token),
-- which NEVER matches (bcrypt salts differ per call). Sessions are now looked
-- up by the JWT jti and the presented token is verified against the stored
-- bcrypt hash. Legacy rows keep refresh_jti NULL: they were never refreshable
-- (the lookup bug predates this column), so no backfill is possible or needed —
-- those users simply re-login once.
ALTER TABLE auth_sessions ADD COLUMN IF NOT EXISTS refresh_jti VARCHAR(64);

-- UNIQUE via index (allows many NULLs for legacy rows, blocks jti collisions).
CREATE UNIQUE INDEX IF NOT EXISTS ux_auth_sessions_refresh_jti
    ON auth_sessions (refresh_jti)
    WHERE refresh_jti IS NOT NULL;

-- Partial index for the hot lookup: live sessions by jti.
CREATE INDEX IF NOT EXISTS ix_auth_sessions_live
    ON auth_sessions (refresh_jti)
    WHERE revoked_at IS NULL;

-- ============================================================================
-- 2. P-ADMIN-SEED — role rows (admin / support)
-- ----------------------------------------------------------------------------
-- seed.sql only seeds status_types; user_roles lookups could never match.
-- First-admin bootstrap is scripts/bootstrap_admin.py (env-keyed), NOT here —
-- migrations must not depend on deployment-specific env values.
INSERT INTO roles (name) VALUES ('admin'), ('support')
ON CONFLICT (name) DO NOTHING;

-- ============================================================================
-- 3. A-REASSIGN — 'revoked' assignment status
-- ----------------------------------------------------------------------------
-- Manual reassign flips the old accepted row to revoked (never 'rejected' —
-- that poisons reliability scoring). See DISPATCH_FLOW.md §Manual reassign.
INSERT INTO status_types (domain, code, label)
VALUES ('assignment', 'revoked', 'Revoked by admin')
ON CONFLICT (domain, code) DO NOTHING;

-- ============================================================================
-- 4. A-AUDIT-LOG — append-only admin audit trail
-- ----------------------------------------------------------------------------
-- entity_id is VARCHAR: audited entities have UUID *and* SMALLSERIAL PKs.
-- Successful admin mutations write a row in the same transaction; failed
-- attempts go to structlog only (an in-txn audit row would roll back with the
-- failed mutation). PII reads (search by phone) log action='read' (DPDP).
CREATE TABLE IF NOT EXISTS admin_audit_log (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    actor_user_id  UUID NOT NULL REFERENCES users(id),
    action         VARCHAR(30)  NOT NULL,   -- create | update | read | approve | reject | revoke | refund_override | ...
    entity_type    VARCHAR(60)  NOT NULL,   -- table or domain name, e.g. 'pujas', 'bookings', 'platform_settings'
    entity_id      VARCHAR(64),
    before_json    JSONB,
    after_json     JSONB,
    change_reason  VARCHAR(300),
    ip             INET,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_admin_audit_actor_time
    ON admin_audit_log (actor_user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_admin_audit_entity
    ON admin_audit_log (entity_type, entity_id);

-- ============================================================================
-- 5. P-ADMIN-AUTH — TOTP credential storage
-- ----------------------------------------------------------------------------
-- TOTP secrets CANNOT be hashed (verification needs the plaintext) — the value
-- stored here is Fernet/AES-GCM ciphertext produced with TOTP_ENC_KEY from the
-- secrets manager (never SECRET_KEY, never plaintext). key_version supports
-- key rotation without re-enrolling every admin.
--
-- Enrolment lifecycle (closes the first-admin lockout — ADMIN.md P-ADMIN-SEED):
--   * role-holder with NO row here may self-enrol ONCE on first admin login
--   * activated_at stays NULL until the user proves possession with a valid code
--   * reset = an existing admin DELETEs the row; the user re-enrols
-- last_used_step blocks TOTP replay: a code (30s time-step) is accepted at most
-- once — the guarded UPDATE "last_used_step < presented_step" is the enforcement.
-- (No colon-prefixed placeholders in this file: Alembic op.execute() treats
-- them as bind parameters, even inside comments.)
CREATE TABLE IF NOT EXISTS admin_credentials (
    user_id          UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    totp_secret_enc  TEXT        NOT NULL,
    key_version      SMALLINT    NOT NULL DEFAULT 1,
    enrolled_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    activated_at     TIMESTAMPTZ,
    last_used_step   BIGINT      NOT NULL DEFAULT 0,
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ============================================================================
-- 6. A-PROMO — promo date-range CHECK (matches the ads-table pattern)
-- ----------------------------------------------------------------------------
-- NOT VALID first so a legacy bad row cannot brick the migration; VALIDATE
-- immediately after (fails loudly if bad data exists — fix data, re-run).
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'ck_promo_codes_valid_range'
          AND conrelid = 'promo_codes'::regclass
    ) THEN
        ALTER TABLE promo_codes
            ADD CONSTRAINT ck_promo_codes_valid_range
            CHECK (valid_until > valid_from) NOT VALID;
    END IF;
END $$;

ALTER TABLE promo_codes VALIDATE CONSTRAINT ck_promo_codes_valid_range;

-- ============================================================================
-- 7. Append-only grants — guarded REVOKE (dev-only guard!)
-- ----------------------------------------------------------------------------
-- puja_app's default grant includes UPDATE, so "no DELETE" alone is NOT
-- append-only. The pg_roles guard exists ONLY so dev machines (connecting as
-- postgres, no puja_app role) don't abort. PROD CORRECTNESS DOES NOT RELY ON
-- THIS BLOCK: puja_app creation is a documented prerequisite of 009 in the
-- runbook, and scripts/apply_grants.sql re-applies all grants idempotently on
-- every deploy. See SPEC_AMENDMENTS.md §19 "Audit log integrity".
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'puja_app') THEN
        GRANT  SELECT, INSERT          ON admin_audit_log        TO   puja_app;
        REVOKE UPDATE, DELETE          ON admin_audit_log        FROM puja_app;
        REVOKE UPDATE, DELETE          ON booking_status_history FROM puja_app;
        GRANT  SELECT, INSERT, UPDATE, DELETE ON admin_credentials TO puja_app;
        GRANT  SELECT                  ON roles                  TO   puja_app;
        GRANT  SELECT, INSERT, DELETE  ON user_roles             TO   puja_app;
    ELSE
        RAISE NOTICE 'role puja_app not found - grants skipped (dev). '
                     'Prod MUST create puja_app before 009 and run scripts/apply_grants.sql.';
    END IF;
END $$;
