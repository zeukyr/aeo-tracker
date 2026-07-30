-- Migration 008: cross-cutting "Pinned" collection for recommendations —
-- orthogonal to the status lifecycle (proposed/accepted/.../superseded), so a
-- rec can be pinned regardless of where it sits in that state machine. Not to
-- be confused with get_saved_recommendations()'s "saved" (= not superseded) -
-- this is a distinct, user-driven "revisit later" flag, hence the different
-- name (is_pinned) throughout.

BEGIN;

ALTER TABLE recommendations
    ADD COLUMN IF NOT EXISTS is_pinned boolean NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS pinned_at timestamptz;

-- Partial index: only pinned rows are ever queried by this flag (Pinned tab),
-- and pins are expected to stay a small minority of all rows.
CREATE INDEX IF NOT EXISTS idx_recommendations_is_pinned
    ON recommendations (is_pinned) WHERE is_pinned;

COMMIT;
