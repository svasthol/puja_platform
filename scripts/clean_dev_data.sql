-- Dev-only reset: clears transactional data, keeps lookup/seed rows.
-- Usage: psql -d Mana_Guruji -f scripts/clean_dev_data.sql

TRUNCATE TABLE
  booking_status_history,
  booking_assignments,
  booking_dispatch_state,
  booking_addons,
  refunds,
  payments,
  bookings,
  slot_holds,
  otp_verifications,
  auth_sessions,
  notifications,
  chat_messages,
  wallet_transactions,
  reviews,
  pujaris,
  users
RESTART IDENTITY CASCADE;

-- Optional: remove dev addresses created during tests (keeps seed if any)
-- DELETE FROM addresses WHERE line1 IN ('Home', 'Test home');
