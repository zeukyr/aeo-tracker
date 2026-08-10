-- Migration 016: deterministic priority for cluster ideas.
-- Additive & idempotent. Safe to run on existing Supabase data.
--
-- The dashboard's idea detail page (pages/BlogIdeaDetail.jsx) shows a
-- Priority/Type/Status info bar per cluster idea, matching how
-- recommendations already carry a priority. Unlike the LLM-authored
-- title/description/keywords (stored in the existing `outline` jsonb -
-- schemaless, no migration needed for those), priority is computed
-- deterministically in Python from the idea's real target_query_ids/
-- qc_share data (see blog_ideas.py's _compute_priority) - a real column so
-- it round-trips predictably and could be sorted/filtered on later, same
-- reasoning as recommendations.priority.
--
-- NULL on rows generated before this migration (backfilling would require
-- re-deriving priority from historical query-bank data this migration
-- doesn't have access to) and on pillar rows, which don't carry a priority
-- of their own - only their cluster children do.

BEGIN;

ALTER TABLE blog_ideas
    ADD COLUMN IF NOT EXISTS priority text
        CHECK (priority IN ('high', 'medium', 'low'));

COMMIT;
