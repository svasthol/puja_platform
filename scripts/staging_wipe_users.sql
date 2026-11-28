-- =============================================================================
-- STAGING-ONLY companion SQL (invoked by scripts/staging_wipe_users.py).
-- NEVER run on production. Wipes booking + identity data, then target users.
-- Keeps: catalog (pujas), platform_settings, relationship_managers, admin users
--        (Python DELETE skips admin/support roles unless --include-admin).
-- =============================================================================

-- 1) Transactional / booking graph (same core as scripts/dev/clean_dev_bookings.sql)
TRUNCATE TABLE
  chat_messages,
  chat_conversations,
  promo_usage_counters,
  promo_redemptions,
  reviews,
  booking_no_show_alerts,
  booking_reconfirmations,
  booking_status_history,
  booking_assignments,
  booking_dispatch_state,
  booking_addons,
  pujari_tds_recovery,
  pujari_tds_accrual_intents,
  pujari_tds_facilitation_ledger,
  pujari_tax_year,
  refunds,
  payment_splits,
  payments,
  bookings,
  slot_holds,
  notifications,
  ops_monitor_alerts,
  payouts,
  wallet_transactions,
  ad_impressions,
  ads
RESTART IDENTITY CASCADE;

-- 2) Staging audit rows (block DELETE users while actor FK exists)
TRUNCATE TABLE admin_audit_log, public_name_audit RESTART IDENTITY CASCADE;

-- 3) OTP / auth scratch
TRUNCATE TABLE otp_verifications, auth_sessions RESTART IDENTITY CASCADE;

-- User deletes happen in Python (scoped + keep-admin).