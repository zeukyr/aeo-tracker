-- Migration 009: human-set correction for a question's matched QC page.
--
-- diagnose_text_coverage (api/queries/sitemap_coverage.py) fuzzy-matches a
-- question against QC's sitemap and picks ONE best page - which can be wrong
-- (matcher picked a different QC page than the right one) or absent (matcher
-- found nothing, even though a page exists). This lets a person override that
-- verdict directly, per question - checked before the matcher runs, no
-- scoring involved.

BEGIN;

ALTER TABLE questions
    ADD COLUMN IF NOT EXISTS qc_url_override text,
    ADD COLUMN IF NOT EXISTS qc_url_override_note text,
    ADD COLUMN IF NOT EXISTS qc_url_override_at timestamptz;

COMMIT;
