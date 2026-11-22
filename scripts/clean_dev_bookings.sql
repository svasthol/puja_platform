-- Dev-only: remove all bookings and dependent rows; keep users, pujaris, catalog.
-- Usage: psql -d Mana_Guruji -f scripts/clean_dev_bookings.sql

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