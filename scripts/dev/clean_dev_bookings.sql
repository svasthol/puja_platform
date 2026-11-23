-- =============================================================================
-- DEV-ONLY — NEVER run on staging or production.
-- Wipes all bookings and dependent rows; keeps users, pujaris, catalog.
-- Prefer: python scripts/dev/run_clean_dev_bookings.py --confirm-wipe-bookings
-- Manual:  psql -d <local_dev_db> -f scripts/dev/clean_dev_bookings.sql
-- =============================================================================

TRUNCATE TABLE
  chat_messages,
  chat_conversations,
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
  refunds,
  payment_splits,
  payments,
  bookings,
  slot_holds,
  notifications
RESTART IDENTITY CASCADE;

DELETE FROM wallet_transactions WHERE reference_type = 'booking';