-- Migration 011: scope blog ideas by school, not just topic.
-- Additive & idempotent. Safe to run on existing Supabase data.
--
-- A "topic" (e.g. "How to Become") spans every QC school - grouping blog
-- ideation by topic alone silently mixed queries from Event Planning, Pet
-- Studies, Career School, etc. into one pillar. Persona/buyer data (survey
-- stats, testimonials) is school-specific, so generation now groups by
-- (topic, school) pair. Nullable, no CHECK constraint - mirrors
-- questions.school's existing General/NULL convention.

BEGIN;

ALTER TABLE blog_ideas
    ADD COLUMN IF NOT EXISTS school text;

COMMIT;
