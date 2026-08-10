-- Migration 010: blog content ideation
-- Additive & idempotent. Safe to run on existing Supabase data.
--
-- Blog ideas are NOT falsifiable hypotheses like `recommendations` rows (no
-- metric/segment/expected_direction) - they're an ongoing backlog of content
-- to write, not a targeted fix tied to one measurable outcome. That's why
-- this is its own table instead of a new recommendations.action_type: see
-- docs/ai/recommendation-system-phases-bc.md and the recommendation-system
-- plan's "every recommendation is a falsifiable hypothesis" principle, which
-- blog ideas deliberately don't have to satisfy.
--
-- One generation batch produces a small pillar/cluster tree per topic: one
-- pillar row (cluster_role='pillar', parent_id NULL) plus several cluster
-- rows (cluster_role='cluster', parent_id -> the pillar). Mirrors the
-- pillar-page/cluster-page structure in the multi-blog strategy doc.

BEGIN;

CREATE TABLE IF NOT EXISTS blog_ideas (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    -- groups every row produced by one generate_blog_ideas() call, same
    -- pattern as recommendations.batch_id
    batch_id         uuid NOT NULL,

    cluster_role     text NOT NULL CHECK (cluster_role IN ('pillar', 'cluster')),
    parent_id        uuid REFERENCES blog_ideas(id) ON DELETE CASCADE,

    -- the losing-question topic this idea addresses (question_router.py's
    -- get_losing_questions() topic grouping - the "bank of LLM queries")
    topic            text,
    title            text NOT NULL,

    -- coverage angle, from the multi-blog doc's "cover all angles" list
    -- (§4.1) - cluster rows only; NULL on pillar rows
    angle            text CHECK (angle IN (
        'definition', 'how_to', 'comparison', 'case_study', 'faq',
        'advanced_technique', 'tool_framework', 'benchmark'
    )),

    -- question ids (from the bank passed into the LLM call) this idea
    -- targets - a pillar's is the union of its cluster rows' ids
    target_query_ids jsonb NOT NULL DEFAULT '[]'::jsonb,

    -- single-post writing guide shape: {heading, extractable_block,
    -- body_points: [...], comparison: {enabled, vs}}
    outline          jsonb,

    status           text NOT NULL DEFAULT 'idea'
                          CHECK (status IN ('idea', 'drafted', 'published')),
    generated_at     timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_blog_ideas_batch_id  ON blog_ideas (batch_id);
CREATE INDEX IF NOT EXISTS idx_blog_ideas_parent_id ON blog_ideas (parent_id);
CREATE INDEX IF NOT EXISTS idx_blog_ideas_status    ON blog_ideas (status);

COMMIT;
