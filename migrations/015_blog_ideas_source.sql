-- Migration 015: distinguish where a blog idea's topic came from.
-- Additive & idempotent. Safe to run on existing Supabase data.
--
-- Every idea up to now was seeded from the tracked-query bank (topic derived
-- from question_router's topic grouping). generate_blog_ideas_from_persona()
-- adds a second path that mines a school's saved buyer-persona/stats/
-- testimonials data directly for topics no tracked query covers yet - the
-- LLM invents the topic label itself rather than it coming from a
-- (topic, school) group. `source` records which path produced a given
-- pillar/cluster row, mainly so the dashboard can label persona-sourced
-- ideas distinctly (they have no target_query_ids to show instead).
-- Backfilled to 'query_bank' since every existing row predates the persona
-- path.

BEGIN;

ALTER TABLE blog_ideas
    ADD COLUMN IF NOT EXISTS source text NOT NULL DEFAULT 'query_bank'
        CHECK (source IN ('query_bank', 'persona'));

COMMIT;
