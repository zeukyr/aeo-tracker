-- Migration: non-destructive recommendation batches
-- Additive & idempotent. Safe to run on existing Supabase data.
-- Adds `superseded` to the status vocabulary (old `proposed` recs are archived,
-- never deleted, when a new batch is generated) and a `batch_id` to group the
-- rows produced by a single generate_recommendations() call.

BEGIN;

-- batch_id: generated once per generate_recommendations() call (in Python),
-- not per-row now(), so rows from the same batch are unambiguously grouped
-- even if individual INSERTs land in the same millisecond.
ALTER TABLE recommendations
    ADD COLUMN IF NOT EXISTS batch_id uuid;

CREATE INDEX IF NOT EXISTS idx_recommendations_batch_id
    ON recommendations (batch_id);

-- Widen the status vocabulary to include 'superseded'. Postgres has no
-- ALTER CHECK, so drop + recreate.
ALTER TABLE recommendations DROP CONSTRAINT IF EXISTS recommendations_status_chk;

ALTER TABLE recommendations
    ADD CONSTRAINT recommendations_status_chk
    CHECK (status IN (
        'proposed','accepted','in_progress','implemented',
        'measuring','validated','failed','inconclusive','superseded'
    ));

COMMIT;
