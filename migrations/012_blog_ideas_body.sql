-- Migration 012: full-post draft body for cluster blog ideas.
-- Additive & idempotent. Safe to run on existing Supabase data.
--
-- Ideation (migration 010) only ever produced a brief: heading, a 40-60
-- word extractable block, and bullet points describing what the full
-- paragraph would cover - not the paragraph itself. `body` holds the
-- generated markdown draft (title + heading + block + real full paragraph
-- + optional comparison table) once a human requests it for one specific
-- cluster idea (see generate_full_post() in api/recommendations/blog_ideas.py).
-- NULL until drafted - pillar rows never get one.

BEGIN;

ALTER TABLE blog_ideas
    ADD COLUMN IF NOT EXISTS body text;

COMMIT;
