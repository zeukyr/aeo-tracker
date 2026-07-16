"""
Backfill mention_response_brands.canonical_name from the brand registry
(api/knowledge/brand_registry.json). Run AFTER applying 006:

    python -m migrations.backfill_canonical_names

Rerunnable: run it again whenever scripts/build_brand_registry.py produces a
new registry (e.g. after variant reviews) — it recomputes canonical_name for
every row, so renames and newly merged variants are picked up. Rows whose
brand_name the registry doesn't know fall back to canonical_name = brand_name.
"""
from api.db import get_connection
from src.parsing.brands import variant_map


def backfill():
    aliases = variant_map()
    if not aliases:
        raise SystemExit("brand registry empty/unreadable — refusing to backfill identity-only")

    with get_connection() as conn:
        with conn.cursor() as cur:
            # Reset to identity first so variants dropped from the registry
            # don't keep a stale canonical name on rerun.
            cur.execute("UPDATE mention_response_brands SET canonical_name = brand_name")
            total = cur.rowcount

            remapped = 0
            # One UPDATE per canonical brand (registry is a few hundred rows).
            by_canonical = {}
            for variant, canonical in aliases.items():
                by_canonical.setdefault(canonical, []).append(variant)
            for canonical, variants in by_canonical.items():
                cur.execute("""
                    UPDATE mention_response_brands
                    SET canonical_name = %s
                    WHERE LOWER(TRIM(brand_name)) = ANY(%s) AND canonical_name != %s
                """, (canonical, variants, canonical))
                remapped += cur.rowcount
        conn.commit()

    print(f"canonical_name set on {total} rows; {remapped} remapped to a registry canonical name")
    return total, remapped


if __name__ == "__main__":
    backfill()
