-- 006: mention_response_brands.canonical_name
--
-- brand_name stores the LLM's verbatim extraction ("Penn Foster's Pet
-- Grooming Certificate", "pennfoster.edu", ...), which fragments per-brand
-- aggregation across spelling variants. canonical_name holds the registry-
-- canonical name ("Penn Foster") so dashboards can group by it, while
-- brand_name stays untouched for scripts/build_brand_registry.py to keep
-- rebuilding the registry from raw strings.
--
-- After applying, run the (rerunnable) alias backfill:
--     python -m migrations.backfill_canonical_names
-- and rerun it whenever the registry is rebuilt.

ALTER TABLE mention_response_brands
    ADD COLUMN IF NOT EXISTS canonical_name TEXT;

-- Identity default so the column is immediately queryable; the backfill
-- overwrites registry-known variants with their canonical names.
UPDATE mention_response_brands
SET canonical_name = brand_name
WHERE canonical_name IS NULL;
