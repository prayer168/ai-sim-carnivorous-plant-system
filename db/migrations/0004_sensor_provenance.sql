-- Explicit batch and acquisition source for reproducible sensor ingestion.
ALTER TABLE readings ADD COLUMN source TEXT NOT NULL DEFAULT 'legacy';
ALTER TABLE readings ADD COLUMN ingest_batch_id TEXT NOT NULL DEFAULT 'legacy';
