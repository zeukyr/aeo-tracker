-- Migration: rich structured detail for recommendations (Phase 4).
-- Additive & idempotent. Holds the Tab 2 scorecard (QC page vs cited pages,
-- feature-by-feature comparison, section-level edits) so the frontend card
-- can render it. NULL for recs that have no structured detail.

BEGIN;

ALTER TABLE recommendations
    ADD COLUMN IF NOT EXISTS detail jsonb;

COMMIT;
