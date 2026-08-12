-- 003_reminder_sent_tracking.sql
-- Adds idempotency tracking to the reminders table so the daily cron
-- worker (POST /api/cron/send-reminders) never sends two emails to
-- the same user on the same date even if it is invoked twice.
--
-- last_sent_date stores the YYYY-MM-DD of the last day on which a
-- reminder email was actually sent for this row. The cron loop skips
-- any row where last_sent_date == today.
--
-- last_sent_kind records WHICH match triggered the send (amavasya,
-- ekadashi, purnima, tithi_anniversary) — useful for logs and for
-- letting a single reminder fire on multiple matches in one day if
-- the user opted into more than one tithi type.

ALTER TABLE reminders ADD COLUMN last_sent_date TEXT;
ALTER TABLE reminders ADD COLUMN last_sent_kind TEXT;

CREATE INDEX IF NOT EXISTS idx_reminders_last_sent
  ON reminders(last_sent_date);
