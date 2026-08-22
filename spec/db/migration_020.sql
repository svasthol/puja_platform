-- Migration 020 — Partner KYC vendor onboarding (Setu DigiLocker, vendor-agnostic schema)
-- Chains after 019. Idempotent.

CREATE TABLE IF NOT EXISTS kyc_verification_requests (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pujari_id       UUID NOT NULL REFERENCES pujaris(id) ON DELETE CASCADE,
    vendor          VARCHAR(32) NOT NULL,
    kind            VARCHAR(16) NOT NULL CHECK (kind IN ('digilocker', 'pan')),
    vendor_request_id VARCHAR(64) NOT NULL,
    status          VARCHAR(20) NOT NULL CHECK (
        status IN ('created', 'authenticated', 'success', 'failed', 'expired')
    ),
    scope           VARCHAR(64),
    error_code      VARCHAR(64),
    error_message   TEXT,
    nonce_hash      VARCHAR(128) NOT NULL,
    review_flags    JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at      TIMESTAMPTZ NOT NULL,
    UNIQUE (vendor, vendor_request_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_kyc_one_live_request
    ON kyc_verification_requests (pujari_id, kind)
    WHERE status IN ('created', 'authenticated');

CREATE INDEX IF NOT EXISTS ix_kyc_verification_requests_pujari
    ON kyc_verification_requests (pujari_id);

CREATE INDEX IF NOT EXISTS ix_kyc_verification_requests_status_expires
    ON kyc_verification_requests (status, expires_at)
    WHERE status IN ('created', 'authenticated');

CREATE TABLE IF NOT EXISTS kyc_identity_registry (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    digilocker_id_hash  VARCHAR(128) NOT NULL UNIQUE,
    pujari_id           UUID REFERENCES pujaris(id) ON DELETE SET NULL,
    state               VARCHAR(16) NOT NULL CHECK (state IN ('active', 'denied')),
    denied_reason       TEXT,
    denied_by           UUID REFERENCES users(id),
    denied_at           TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_kyc_identity_registry_pujari
    ON kyc_identity_registry (pujari_id)
    WHERE pujari_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS kyc_consents (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pujari_id           UUID NOT NULL REFERENCES pujaris(id) ON DELETE CASCADE,
    request_id          UUID NOT NULL REFERENCES kyc_verification_requests(id) ON DELETE CASCADE,
    purpose             VARCHAR(64) NOT NULL,
    text_version        VARCHAR(32) NOT NULL,
    consent_text_hash   VARCHAR(128) NOT NULL,
    granted_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    ip                  VARCHAR(45),
    user_agent          VARCHAR(255)
);

CREATE INDEX IF NOT EXISTS ix_kyc_consents_pujari
    ON kyc_consents (pujari_id);

CREATE INDEX IF NOT EXISTS ix_kyc_consents_request
    ON kyc_consents (request_id);

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'puja_app') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON kyc_verification_requests TO puja_app;
        GRANT SELECT, INSERT, UPDATE, DELETE ON kyc_identity_registry TO puja_app;
        GRANT SELECT, INSERT ON kyc_consents TO puja_app;
    ELSE
        RAISE NOTICE 'role puja_app not found - grants skipped (dev).';
    END IF;
END $$;
