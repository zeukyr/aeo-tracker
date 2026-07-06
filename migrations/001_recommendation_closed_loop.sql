-- Migration: closed-loop recommendation system
-- Additive & idempotent. Safe to run on existing Supabase data.
-- Extends `recommendations` with quality + lifecycle + measurement fields,
-- and adds `recommendation_outcomes` for the diff-in-diff measurement history.

BEGIN;

-- ─────────────────────────────────────────────────────────────────────────────
-- 1. Quality / structured-action fields (Phase 1 & 2)
-- ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE recommendations
    -- what kind of action this is (content | technical | citation | outreach)
    ADD COLUMN IF NOT EXISTS action_type        text,
    -- concrete target: a URL, page, topic, or competitor the action addresses
    ADD COLUMN IF NOT EXISTS target             text,
    -- the segment this rec is scoped to, e.g. {"dimension":"topic","value":"Brand Credibility"}
    -- dimension ∈ engine | topic | category | school | global
    ADD COLUMN IF NOT EXISTS segment            jsonb,
    -- which KPI the rec is expected to move (mention_rate | citation_rate |
    -- positive_sentiment_rate | avg_rank | sov | visibility_score)
    ADD COLUMN IF NOT EXISTS metric_impact      text,
    -- expected direction of the metric: +1 = increase, -1 = decrease (e.g. avg_rank)
    ADD COLUMN IF NOT EXISTS expected_direction smallint,
    -- optional expected magnitude in the metric's units (percentage points, rank, etc.)
    ADD COLUMN IF NOT EXISTS expected_magnitude numeric,
    -- estimated effort: S | M | L
    ADD COLUMN IF NOT EXISTS effort             text,
    -- model/judge confidence 0..1
    ADD COLUMN IF NOT EXISTS confidence         numeric;

-- ─────────────────────────────────────────────────────────────────────────────
-- 2. Lifecycle + baseline fields (Phase 3)
--    status flow: proposed → accepted → in_progress → implemented
--                 → measuring → validated | failed | inconclusive
--    (`status` column already exists as free text; we constrain the vocabulary below)
-- ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE recommendations
    -- when the action was actually shipped; starts the measurement clock
    ADD COLUMN IF NOT EXISTS implemented_at         timestamptz,
    -- how many days the post-implementation window spans (default 30)
    ADD COLUMN IF NOT EXISTS measurement_window_days integer DEFAULT 30,
    -- metric value in the target segment over the window BEFORE implemented_at
    ADD COLUMN IF NOT EXISTS baseline_value          numeric,
    -- number of responses backing the baseline (min-sample gate for measurement)
    ADD COLUMN IF NOT EXISTS baseline_sample_n       integer,
    -- when the closed-loop measurement was last computed
    ADD COLUMN IF NOT EXISTS measured_at             timestamptz,
    -- full measurement detail: {post_value, post_sample_n, target_delta,
    --   control_delta, diff_in_diff_lift, p_value, verdict}
    ADD COLUMN IF NOT EXISTS outcome                 jsonb;

-- Default new rows to 'proposed'; backfill existing NULL statuses.
ALTER TABLE recommendations ALTER COLUMN status SET DEFAULT 'proposed';
UPDATE recommendations SET status = 'proposed' WHERE status IS NULL;

-- Constrain the status vocabulary (added NOT VALID-free since we just backfilled).
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'recommendations_status_chk'
    ) THEN
        ALTER TABLE recommendations
            ADD CONSTRAINT recommendations_status_chk
            CHECK (status IN (
                'proposed','accepted','in_progress','implemented',
                'measuring','validated','failed','inconclusive'
            ));
    END IF;
END$$;

-- ─────────────────────────────────────────────────────────────────────────────
-- 3. Measurement history — one row per measurement pass of a recommendation.
--    Keeps the audit trail even if `recommendations.outcome` is overwritten,
--    and lets the learning loop query "what tactics worked" over time.
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS recommendation_outcomes (
    id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    recommendation_id  uuid NOT NULL REFERENCES recommendations(id) ON DELETE CASCADE,
    measured_at        timestamptz NOT NULL DEFAULT now(),

    metric             text    NOT NULL,          -- metric_impact snapshot
    segment            jsonb,                      -- segment snapshot

    baseline_value     numeric,                    -- target segment, pre-window
    post_value         numeric,                    -- target segment, post-window
    target_delta       numeric,                    -- post - baseline (target)
    control_delta      numeric,                    -- post - baseline (untargeted control)
    diff_in_diff_lift  numeric,                    -- target_delta - control_delta
    baseline_sample_n  integer,
    post_sample_n      integer,
    p_value            numeric,                    -- two-proportion test

    verdict            text CHECK (verdict IN ('validated','failed','inconclusive'))
);

CREATE INDEX IF NOT EXISTS idx_rec_outcomes_rec_id
    ON recommendation_outcomes (recommendation_id, measured_at DESC);

-- Helpful for the lifecycle board / sweep that advances `measuring` rows.
CREATE INDEX IF NOT EXISTS idx_recommendations_status
    ON recommendations (status);

COMMIT;
