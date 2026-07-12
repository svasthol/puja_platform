-- =============================================================================
-- PUJA BOOKING PLATFORM — PRODUCTION SCHEMA (v FINAL, validated)
-- PostgreSQL 16
-- =============================================================================
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS btree_gist;  -- required for the pujari no-overlap exclusion constraint

-- =============================================================================
-- DOMAIN 1 — IDENTITY & ACCESS
-- =============================================================================
CREATE TABLE users (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    full_name     VARCHAR(150) NOT NULL,
    phone         VARCHAR(15)  NOT NULL UNIQUE,
    email         VARCHAR(150) UNIQUE,
    is_active     BOOLEAN NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE roles (
    id    SMALLSERIAL PRIMARY KEY,
    name  VARCHAR(30) NOT NULL UNIQUE
);

CREATE TABLE user_roles (
    user_id      UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role_id      SMALLINT NOT NULL REFERENCES roles(id),
    assigned_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, role_id)
);

CREATE TABLE addresses (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    line1       VARCHAR(200) NOT NULL,
    line2       VARCHAR(200),
    city        VARCHAR(80) NOT NULL,
    state       VARCHAR(80),
    pincode     VARCHAR(10),
    latitude    DECIMAL(9,6),
    longitude   DECIMAL(9,6),
    is_default  BOOLEAN NOT NULL DEFAULT FALSE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- one default address per user
CREATE UNIQUE INDEX ux_addresses_one_default_per_user
    ON addresses (user_id) WHERE is_default;

CREATE TABLE devices (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id        UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    device_token   VARCHAR(255) NOT NULL UNIQUE,
    platform       VARCHAR(20),
    last_seen_at   TIMESTAMPTZ,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE auth_sessions (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    device_id           UUID REFERENCES devices(id),
    app_context         VARCHAR(10) NOT NULL CHECK (app_context IN ('customer','pujari','admin')),
    refresh_token_hash  VARCHAR(255) NOT NULL UNIQUE,
    issued_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at          TIMESTAMPTZ NOT NULL,
    revoked_at          TIMESTAMPTZ,
    revoked_reason      VARCHAR(100)
);
CREATE INDEX ix_auth_sessions_user ON auth_sessions(user_id);

CREATE TABLE otp_verifications (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      UUID REFERENCES users(id),
    phone        VARCHAR(15) NOT NULL,
    otp_hash     VARCHAR(255) NOT NULL,
    purpose      VARCHAR(30) NOT NULL,
    attempts     SMALLINT NOT NULL DEFAULT 0 CHECK (attempts <= 5),
    expires_at   TIMESTAMPTZ NOT NULL,
    verified_at  TIMESTAMPTZ,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_otp_verifications_phone ON otp_verifications(phone);

-- =============================================================================
-- DOMAIN 2 — PUJARI PROFILE & CATALOG
-- =============================================================================
CREATE TABLE service_areas (
    id          SMALLSERIAL PRIMARY KEY,
    city        VARCHAR(80) NOT NULL,
    zone_name   VARCHAR(100) NOT NULL,
    pincode     VARCHAR(10),
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,
    UNIQUE (city, zone_name)
);

CREATE TABLE languages (
    id    SMALLSERIAL PRIMARY KEY,
    code  VARCHAR(10) NOT NULL UNIQUE,
    name  VARCHAR(50) NOT NULL
);

CREATE TABLE specializations (
    id    SMALLSERIAL PRIMARY KEY,
    name  VARCHAR(100) NOT NULL UNIQUE
);

CREATE TABLE puja_categories (
    id    SMALLSERIAL PRIMARY KEY,
    name  VARCHAR(100) NOT NULL UNIQUE
);

CREATE TABLE pujas (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    category_id       SMALLINT NOT NULL REFERENCES puja_categories(id),
    name              VARCHAR(150) NOT NULL,
    description       TEXT,
    duration_minutes  INT,
    default_price     DECIMAL(10,2) NOT NULL CHECK (default_price >= 0),
    is_active         BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE puja_addons (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    puja_id    UUID NOT NULL REFERENCES pujas(id) ON DELETE CASCADE,
    name       VARCHAR(100) NOT NULL,
    price      DECIMAL(10,2) NOT NULL CHECK (price >= 0),
    is_active  BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE pujaris (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    bio                 TEXT,
    years_experience    SMALLINT,
    verification_status VARCHAR(20) NOT NULL DEFAULT 'pending'
                          CHECK (verification_status IN ('pending','verified','rejected')),
    rating_avg          DECIMAL(3,2) NOT NULL DEFAULT 0,
    rating_count        INT NOT NULL DEFAULT 0,
    is_online           BOOLEAN NOT NULL DEFAULT FALSE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE pujari_documents (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pujari_id    UUID NOT NULL REFERENCES pujaris(id) ON DELETE CASCADE,
    doc_type     VARCHAR(30) NOT NULL,
    file_url     VARCHAR(500) NOT NULL,
    version      SMALLINT NOT NULL DEFAULT 1,
    is_current   BOOLEAN NOT NULL DEFAULT TRUE,
    status       VARCHAR(20) NOT NULL DEFAULT 'pending'
                  CHECK (status IN ('pending','verified','rejected')),
    uploaded_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (pujari_id, doc_type, version)
);

CREATE TABLE pujari_languages (
    pujari_id    UUID NOT NULL REFERENCES pujaris(id) ON DELETE CASCADE,
    language_id  SMALLINT NOT NULL REFERENCES languages(id),
    PRIMARY KEY (pujari_id, language_id)
);

CREATE TABLE pujari_specializations (
    pujari_id          UUID NOT NULL REFERENCES pujaris(id) ON DELETE CASCADE,
    specialization_id  SMALLINT NOT NULL REFERENCES specializations(id),
    PRIMARY KEY (pujari_id, specialization_id)
);

CREATE TABLE pujari_availability (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pujari_id    UUID NOT NULL REFERENCES pujaris(id) ON DELETE CASCADE,
    day_of_week  SMALLINT NOT NULL CHECK (day_of_week BETWEEN 0 AND 6),
    start_time   TIME NOT NULL,
    end_time     TIME NOT NULL CHECK (end_time > start_time),
    UNIQUE (pujari_id, day_of_week, start_time)
);

CREATE TABLE pujari_unavailability (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pujari_id         UUID NOT NULL REFERENCES pujaris(id) ON DELETE CASCADE,
    unavailable_date  DATE NOT NULL,
    reason            VARCHAR(100),
    UNIQUE (pujari_id, unavailable_date)
);

CREATE TABLE pujari_live_location (
    pujari_id   UUID PRIMARY KEY REFERENCES pujaris(id) ON DELETE CASCADE,
    latitude    DECIMAL(9,6) NOT NULL,
    longitude   DECIMAL(9,6) NOT NULL,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE pujari_pricing (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pujari_id   UUID NOT NULL REFERENCES pujaris(id) ON DELETE CASCADE,
    puja_id     UUID NOT NULL REFERENCES pujas(id) ON DELETE CASCADE,
    base_price  DECIMAL(10,2) NOT NULL CHECK (base_price >= 0),
    UNIQUE (pujari_id, puja_id)
);

-- =============================================================================
-- DOMAIN 3 — BOOKING & DISPATCH
-- =============================================================================
CREATE TABLE status_types (
    id      SMALLSERIAL PRIMARY KEY,
    domain  VARCHAR(30) NOT NULL,
    code    VARCHAR(30) NOT NULL,
    label   VARCHAR(60) NOT NULL,
    UNIQUE (domain, code)
);

CREATE TABLE cancellation_policies (
    id                       SMALLSERIAL PRIMARY KEY,
    name                     VARCHAR(80) NOT NULL UNIQUE,
    refund_pct_before_24h    SMALLINT NOT NULL CHECK (refund_pct_before_24h BETWEEN 0 AND 100),
    refund_pct_after_24h     SMALLINT NOT NULL CHECK (refund_pct_after_24h BETWEEN 0 AND 100)
);

CREATE TABLE slot_holds (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id        UUID NOT NULL REFERENCES users(id),
    pujari_id      UUID NOT NULL REFERENCES pujaris(id),
    slot_date      DATE NOT NULL,
    slot_time      TIME NOT NULL,
    held_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at     TIMESTAMPTZ NOT NULL,
    released_at    TIMESTAMPTZ
);
-- CRITICAL: uniqueness applies ONLY to active (unreleased) holds. A flat table-level
-- UNIQUE here would permanently block a slot forever after its first hold resolves.
CREATE UNIQUE INDEX ux_slot_holds_active ON slot_holds (pujari_id, slot_date, slot_time) WHERE released_at IS NULL;
-- sweep index: worker scans for expired-unreleased holds
CREATE INDEX ix_slot_holds_sweep ON slot_holds (expires_at) WHERE released_at IS NULL;

CREATE TABLE bookings (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id                 UUID NOT NULL REFERENCES users(id),
    pujari_id               UUID REFERENCES pujaris(id),  -- NULL until an assignment is accepted (TRG-managed)
    puja_id                 UUID NOT NULL REFERENCES pujas(id),
    address_id              UUID NOT NULL REFERENCES addresses(id),
    status_id               SMALLINT NOT NULL REFERENCES status_types(id),
    cancellation_policy_id  SMALLINT NOT NULL REFERENCES cancellation_policies(id),
    scheduled_date          DATE NOT NULL,
    scheduled_time          TIME NOT NULL,
    duration_minutes        SMALLINT NOT NULL DEFAULT 0,  -- TRG: snapshotted from pujas at insert
    cancelled_at            TIMESTAMPTZ,                  -- set on cancellation; frees the slot below
    total_amount            DECIMAL(10,2) NOT NULL CHECK (total_amount >= 0),
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_bookings_user ON bookings(user_id);
CREATE INDEX ix_bookings_pujari ON bookings(pujari_id);

-- THE REAL double-booking guarantee: a pujari can never hold two ACTIVE bookings whose
-- time windows OVERLAP (not merely start at the same instant). A 10:00 booking lasting
-- 90 minutes blocks 10:30; a cancelled booking frees its window. Checked by the DB on
-- every INSERT and on the UPDATE that assigns pujari_id at accept time.
ALTER TABLE bookings ADD CONSTRAINT ex_bookings_pujari_no_overlap
    EXCLUDE USING gist (
        pujari_id WITH =,
        tsrange(scheduled_date + scheduled_time,
                scheduled_date + scheduled_time + make_interval(mins => duration_minutes)) WITH &&
    ) WHERE (pujari_id IS NOT NULL AND cancelled_at IS NULL);

-- double-submit protection: the same customer cannot create two identical ACTIVE bookings
CREATE UNIQUE INDEX ux_bookings_no_duplicate_submit
    ON bookings (user_id, puja_id, scheduled_date, scheduled_time)
    WHERE cancelled_at IS NULL;

CREATE TABLE booking_addons (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    booking_id        UUID NOT NULL REFERENCES bookings(id) ON DELETE CASCADE,
    addon_id          UUID NOT NULL REFERENCES puja_addons(id),
    price_at_booking  DECIMAL(10,2) NOT NULL,
    UNIQUE (booking_id, addon_id)
);

CREATE TABLE booking_assignments (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    booking_id    UUID NOT NULL REFERENCES bookings(id) ON DELETE CASCADE,
    pujari_id     UUID NOT NULL REFERENCES pujaris(id),
    status_id     SMALLINT NOT NULL REFERENCES status_types(id),
    offered_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at    TIMESTAMPTZ NOT NULL,
    responded_at  TIMESTAMPTZ
);
CREATE INDEX ix_booking_assignments_sweep ON booking_assignments (expires_at) WHERE responded_at IS NULL;
CREATE INDEX ix_booking_assignments_booking ON booking_assignments(booking_id);
CREATE INDEX ix_booking_assignments_pujari ON booking_assignments(pujari_id);

CREATE TABLE booking_status_history (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    booking_id  UUID NOT NULL REFERENCES bookings(id) ON DELETE CASCADE,
    status_id   SMALLINT NOT NULL REFERENCES status_types(id),
    changed_by  UUID REFERENCES users(id),
    changed_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- =============================================================================
-- DOMAIN 4 — PAYMENTS & PAYOUTS
-- =============================================================================
CREATE TABLE payments (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    booking_id       UUID NOT NULL REFERENCES bookings(id),
    amount           DECIMAL(10,2) NOT NULL CHECK (amount >= 0),
    idempotency_key  VARCHAR(100) NOT NULL UNIQUE,
    gateway_txn_id   VARCHAR(100) UNIQUE,
    status           VARCHAR(20) NOT NULL DEFAULT 'pending'
                       CHECK (status IN ('pending','success','failed','refunded')),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_payments_booking ON payments(booking_id);

CREATE TABLE payment_splits (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    payment_id         UUID NOT NULL UNIQUE REFERENCES payments(id) ON DELETE CASCADE,
    platform_fee       DECIMAL(10,2) NOT NULL CHECK (platform_fee >= 0),
    gst_amount         DECIMAL(10,2) NOT NULL CHECK (gst_amount >= 0),
    net_pujari_amount  DECIMAL(10,2) NOT NULL DEFAULT 0  -- TRG-computed, see triggers.sql
);

CREATE TABLE payouts (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pujari_id         UUID NOT NULL REFERENCES pujaris(id),
    amount            DECIMAL(10,2) NOT NULL CHECK (amount >= 0),
    payout_reference  VARCHAR(100) NOT NULL UNIQUE,
    status            VARCHAR(20) NOT NULL DEFAULT 'initiated'
                        CHECK (status IN ('initiated','success','failed')),
    processed_at      TIMESTAMPTZ,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE wallet_transactions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pujari_id       UUID NOT NULL REFERENCES pujaris(id),
    amount          DECIMAL(10,2) NOT NULL,
    txn_type        VARCHAR(20) NOT NULL CHECK (txn_type IN ('credit','debit')),
    reference_type  VARCHAR(30) NOT NULL
                      CHECK (reference_type IN ('booking','payout','refund','adjustment')),
    reference_id    UUID NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_wallet_transactions_pujari ON wallet_transactions(pujari_id);

-- =============================================================================
-- DOMAIN 5 — ENGAGEMENT & GROWTH
-- =============================================================================
CREATE TABLE reviews (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    booking_id  UUID NOT NULL UNIQUE REFERENCES bookings(id),
    user_id     UUID NOT NULL REFERENCES users(id),
    pujari_id   UUID NOT NULL REFERENCES pujaris(id),
    rating      SMALLINT NOT NULL CHECK (rating BETWEEN 1 AND 5),
    comment     TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- used directly by the rating-sync trigger (aiud_reviews_rating_sync) on every write
CREATE INDEX ix_reviews_pujari ON reviews(pujari_id);

CREATE TABLE chat_conversations (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    booking_id  UUID NOT NULL UNIQUE REFERENCES bookings(id),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE chat_messages (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id  UUID NOT NULL REFERENCES chat_conversations(id) ON DELETE CASCADE,
    sender_id        UUID NOT NULL REFERENCES users(id),
    body             TEXT NOT NULL,
    sent_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_chat_messages_conversation ON chat_messages(conversation_id);

CREATE TABLE notifications (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       UUID NOT NULL REFERENCES users(id),
    app_context   VARCHAR(10) NOT NULL CHECK (app_context IN ('customer','pujari','admin')),
    related_type  VARCHAR(30)
                    CHECK (related_type IN ('booking','payment','assignment','promo','chat','system')),
    related_id    UUID,
    title         VARCHAR(150) NOT NULL,
    body          TEXT,
    read_at       TIMESTAMPTZ,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_notifications_user ON notifications(user_id);

CREATE TABLE promo_codes (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code                VARCHAR(30) NOT NULL UNIQUE,
    discount_pct        SMALLINT NOT NULL CHECK (discount_pct BETWEEN 1 AND 100),
    max_uses_per_user   SMALLINT NOT NULL DEFAULT 1,
    valid_from          TIMESTAMPTZ NOT NULL,
    valid_until         TIMESTAMPTZ NOT NULL,
    is_active           BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE promo_redemptions (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    promo_code_id  UUID NOT NULL REFERENCES promo_codes(id),
    user_id        UUID NOT NULL REFERENCES users(id),
    booking_id     UUID NOT NULL REFERENCES bookings(id),
    redeemed_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (promo_code_id, user_id, booking_id)
);
CREATE INDEX ix_promo_redemptions_user ON promo_redemptions(user_id);

CREATE TABLE promo_usage_counters (
    promo_code_id     UUID NOT NULL REFERENCES promo_codes(id),
    user_id           UUID NOT NULL REFERENCES users(id),
    redemption_count  SMALLINT NOT NULL DEFAULT 0,
    PRIMARY KEY (promo_code_id, user_id)
);

CREATE TABLE ads (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pujari_id   UUID NOT NULL REFERENCES pujaris(id),
    puja_id     UUID NOT NULL REFERENCES pujas(id),
    title       VARCHAR(150) NOT NULL,
    budget      DECIMAL(10,2) NOT NULL CHECK (budget >= 0),
    starts_at   TIMESTAMPTZ NOT NULL,
    ends_at     TIMESTAMPTZ NOT NULL CHECK (ends_at > starts_at),
    is_active   BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE ad_impressions (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ad_id      UUID NOT NULL REFERENCES ads(id) ON DELETE CASCADE,
    user_id    UUID NOT NULL REFERENCES users(id),
    shown_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    clicked    BOOLEAN NOT NULL DEFAULT FALSE
);
