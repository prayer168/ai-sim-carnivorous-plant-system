-- Device freshness metadata used by the MVP offline indicator.
ALTER TABLE devices ADD COLUMN expected_interval_seconds INTEGER NOT NULL DEFAULT 900;
ALTER TABLE devices ADD COLUMN last_seen_at TEXT;
