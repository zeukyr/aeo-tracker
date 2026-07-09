-- Migration 004: move the per-URL page-facts cache from
-- api/knowledge/page_facts.json into a table. Additive & idempotent.
-- Safe to run on existing Supabase data.
--
-- One row per cited URL (url is the natural key -> uniqueness for free). The
-- full facts dict lives in `facts` jsonb (the source of truth the Python layer
-- reads back verbatim); the promoted scalar columns are an indexed projection
-- of the same dict, written on upsert, so SQL/dashboards can filter without
-- digging through jsonb.

BEGIN;

CREATE TABLE IF NOT EXISTS page_facts (
    -- the cited URL; natural key. status != 'ok' means content facts are absent.
    url               text PRIMARY KEY,
    -- registrable-ish host (www stripped), e.g. "coursera.org", "community.cvent.com"
    domain            text,
    -- ok | not_fetched | fetch_failed | blocked_robots | not_html | too_large
    status            text NOT NULL,
    -- plan taxonomy: qc_owned | competitor | community | video | government |
    -- roundup | directory | association | guide | editorial
    page_type         text,
    -- how page_type was decided: domain | heuristic | llm | fallback
    page_type_source  text,
    -- when the page was last fetched/classified; drives the failure-retry window
    fetched_at        timestamptz NOT NULL DEFAULT now(),
    -- the complete facts dict (headings, schema_types, brand_mentions, features,
    -- content_excerpt, qc_mentioned, ...). What get_page_facts returns.
    facts             jsonb NOT NULL,
    updated_at        timestamptz NOT NULL DEFAULT now()
);

-- The three columns the router / genre / coverage code filters on.
CREATE INDEX IF NOT EXISTS idx_page_facts_page_type ON page_facts (page_type);
CREATE INDEX IF NOT EXISTS idx_page_facts_status    ON page_facts (status);
CREATE INDEX IF NOT EXISTS idx_page_facts_domain    ON page_facts (domain);

COMMIT;
