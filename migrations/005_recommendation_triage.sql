-- Migration 005: persist the router's triage list (question-router plan §5.9).
-- Additive & idempotent. Safe to run on existing Supabase data.
--
-- One row per losing question the router could NOT auto-action, per batch -
-- the visible "needs a human" queue that replaces silent drops. Rows are
-- written with the same batch_id as the recommendations they were generated
-- with; the dashboard shows the latest batch, ranked by rank_score (citation
-- volume x how badly QC is losing), so the strongest own-the-field candidates
-- surface first instead of an unranked pile.

BEGIN;

CREATE TABLE IF NOT EXISTS recommendation_triage (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    batch_id        uuid NOT NULL,
    generated_at    timestamptz NOT NULL DEFAULT now(),

    question_id     uuid,
    question        text NOT NULL,
    topic           text,
    school          text,

    -- fragmented_field | insufficient_voters | no_cited_winners |
    -- feasibility_unknown | reputation_no_channel
    reason          text NOT NULL,
    -- buildable topic where QC could plausibly own the fragmented field -
    -- flagged for a human green-light, never auto-built
    build_candidate boolean NOT NULL DEFAULT false,

    qc_share        numeric,
    n_citations     integer,
    -- n_citations x (1 - qc_share): the queue order
    rank_score      numeric,

    -- vote tally, winner summary, qc_url, genre_mismatch - the router's
    -- full working for the row
    detail          jsonb
);

CREATE INDEX IF NOT EXISTS idx_rec_triage_batch ON recommendation_triage (batch_id);

COMMIT;
