-- 002_reminders.sql
-- Creates reminders table for ancestor remembrance notifications

CREATE TABLE IF NOT EXISTS reminders (
  id TEXT PRIMARY KEY,
  email TEXT NOT NULL,
  name TEXT NOT NULL,
  city_name TEXT NOT NULL,
  lat REAL NOT NULL,
  lng REAL NOT NULL,
  tz TEXT NOT NULL,
  tithi_types TEXT NOT NULL,
  custom_tithi TEXT,
  personal_note TEXT,
  remind_days_before INTEGER NOT NULL DEFAULT 1,
  remind_time TEXT NOT NULL DEFAULT '06:00',
  reminder_type TEXT NOT NULL DEFAULT 'amavasya',
  tithi_masa_number INTEGER,
  tithi_paksha TEXT,
  tithi_number INTEGER,
  tithi_description TEXT,
  origin_lat REAL,
  origin_lng REAL,
  origin_tz TEXT,
  original_date TEXT,
  unsubscribe_token TEXT NOT NULL,
  active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_reminders_email
  ON reminders(email);

CREATE INDEX IF NOT EXISTS idx_reminders_active
  ON reminders(active);

CREATE INDEX IF NOT EXISTS idx_reminders_unsubscribe
  ON reminders(unsubscribe_token);
