-- 001_initial.sql
-- Creates panchangam_cache and geocode_cache tables

CREATE TABLE IF NOT EXISTS panchangam_cache (
  cache_key TEXT PRIMARY KEY,
  data TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  expires_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_panchangam_cache_expires
  ON panchangam_cache(expires_at);

CREATE TABLE IF NOT EXISTS geocode_cache (
  query TEXT PRIMARY KEY,
  data TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  expires_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_geocode_cache_expires
  ON geocode_cache(expires_at);
