"""User-editable buyer persona / stats / testimonials input for blog idea
generation - see migrations/013_blog_personas.sql and
migrations/014_blog_personas_categories.sql. Three separate free-form
markdown fields per school (school=None is General, same convention as
questions.school elsewhere), edited from the dashboard's Blog Ideas tab
*before* generating ideas, since ideation (angle/hook selection) benefits
from it as much as full-post drafting does - see blog_ideas.py's
_build_prompt and _build_full_post_prompt, which both call get_persona().

The three categories are split into their own columns (rather than one
combined blob) because they're used differently downstream: ideation draws
on all three, but full-post drafting deliberately excludes testimonials
(reserved for the ideation stage's case_study angle) - a real column split
makes that exclusion structural instead of an instruction the model has to
remember to follow.

Replaces the old hardcoded api/knowledge/qc_event_planning_persona.md, which
only ever covered one school - this table has no such restriction, and the
former file's content was migrated in as that school's seed row.
"""

from api.db import get_connection

# COALESCE(school, '') in every WHERE/ON CONFLICT clause here matches the
# functional unique index in migrations/013_blog_personas.sql - Postgres
# unique constraints treat NULL as distinct from NULL, so a plain UNIQUE
# (school) would allow multiple General rows.

def get_persona(school):
    """{"buyer_persona": str|None, "stats": str|None, "testimonials": str|None}
    for this school, or None if nothing's been entered in any category yet.
    `school=None` is General."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT buyer_persona, stats, testimonials FROM blog_personas "
                "WHERE COALESCE(school, '') = COALESCE(%s, '')",
                (school,),
            )
            row = cur.fetchone()
    if not row or not any(row):
        return None
    return {"buyer_persona": row[0], "stats": row[1], "testimonials": row[2]}


def get_all_personas():
    """Every saved persona, for the dashboard's editor to show which schools
    already have one and to prefill each category's box when a school is
    selected."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT school, buyer_persona, stats, testimonials, updated_at
                FROM blog_personas ORDER BY school NULLS FIRST
            """)
            rows = cur.fetchall()
    return [
        {
            "school": r[0],
            "buyer_persona": r[1],
            "stats": r[2],
            "testimonials": r[3],
            "updated_at": r[4].isoformat(),
        }
        for r in rows
    ]


def save_persona(school, buyer_persona=None, stats=None, testimonials=None):
    """Upserts the persona for this school. Each category is stored
    independently - a school can have just stats, just testimonials, etc.
    Blank/whitespace-only in all three clears the row entirely (delete)
    instead of storing an all-empty row - same end state as never having
    entered one, and lets the dashboard's "Clear" action reuse this one
    function rather than needing its own endpoint."""
    buyer_persona = (buyer_persona or "").strip() or None
    stats = (stats or "").strip() or None
    testimonials = (testimonials or "").strip() or None
    with get_connection() as conn:
        with conn.cursor() as cur:
            if not (buyer_persona or stats or testimonials):
                cur.execute(
                    "DELETE FROM blog_personas WHERE COALESCE(school, '') = COALESCE(%s, '')",
                    (school,),
                )
            else:
                cur.execute("""
                    INSERT INTO blog_personas (school, buyer_persona, stats, testimonials, updated_at)
                    VALUES (%s, %s, %s, %s, now())
                    ON CONFLICT (COALESCE(school, '')) DO UPDATE
                        SET buyer_persona = EXCLUDED.buyer_persona,
                            stats = EXCLUDED.stats,
                            testimonials = EXCLUDED.testimonials,
                            updated_at = now()
                """, (school, buyer_persona, stats, testimonials))
        conn.commit()
    return get_all_personas()
