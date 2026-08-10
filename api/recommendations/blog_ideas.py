"""Blog content ideation: an ongoing pillar/cluster content backlog, not a
falsifiable-hypothesis recommendation (see migrations/010_blog_ideas.sql for
why this is its own table).

Input is the full tracked-question bank (question_router's
get_losing_questions with the win/loss gate opened all the way, still
weakest-QC-share-first) grouped by (topic, school) - a "topic" like "How to
Become" spans every QC school, and persona/buyer data is school-specific, so
generation is scoped per school rather than mixing schools into one pillar.
One (topic, school) group becomes one pillar page idea plus several
cluster-page ideas.

Generation is LLM-authored (unlike the deterministic rec builders): ideation
benefits from variety in a way a fix/build rec's template doesn't. Each call
is grounded in the query text (no winner page_facts - a deliberate v1 scope
cut) plus:

  - api/knowledge/blog_pillar_strategy.md   - how the pillar/cluster tree and
    its cross-post signals (terminology, linking, schema) should be shaped.
  - api/knowledge/blog_post_writing_guide.md - how each individual cluster
    post should be structured (question heading, dual extractable/full
    blocks, comparison structure, tone).
  - blog_personas.get_persona(school) - user-entered buyer-persona survey
    data + named testimonials for that group's school, edited from the
    dashboard's Blog Ideas tab (see migrations/013_blog_personas.sql).
    School-specific and never extrapolated to other schools - a group whose
    school has no saved persona just gets no persona section.

Every LLM response is independently validated against ANGLE_VOCAB and the
query-id bank passed into that call (never trust an id or angle the model
invents) - same defense-in-depth spirit as the rest of this package. Fails
closed: a group that doesn't produce a valid pillar + at least one valid
cluster idea is skipped, never partially saved.

generate_blog_ideas_from_persona() is a second, independent ideation path:
instead of starting from a (topic, school) query-bank group, it starts from
one school's saved persona data alone and lets the model invent the topic(s)
themselves - for surfacing a topic the persona data clearly calls for but
that no tracked AI-engine query happens to cover yet. Saved to the same
table with source='persona' and empty target_query_ids (see
migrations/015_blog_ideas_source.sql).

generate_blog_ideas() is the single entry point the dashboard calls (one
"Generate ideas" button, no human picks a mode or a specific topic anymore):
it auto-picks the largest uncovered query-bank groups - "largest" already
means both "commonly asked" (many distinct tracked queries) and, since the
group is sorted internally weakest-QC-share-first, "an area QC is weak in" -
so one ranking captures both signals a human used to have to choose between.
Any school with saved persona data that has no pending query-bank groups
left this run automatically falls back to the persona path instead, so a
thin tracked-query bank for a school never blocks that school from getting
new ideas. See _MAX_GROUPS_PER_RUN / _MAX_PERSONA_FALLBACK_SCHOOLS_PER_RUN.
"""

import json
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from functools import lru_cache

from openai import OpenAI
from psycopg2.extras import Json

from api.db import get_connection
from api.queries.question_router import get_losing_questions
from api.recommendations.blog_personas import get_all_personas, get_persona
from api.recommendations.store import GENERATION_COOLDOWN_DAYS
from src.logger import logger

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

_KNOWLEDGE_DIR = os.path.join(os.path.dirname(__file__), "..", "knowledge")

ANGLE_VOCAB = (
    "definition", "how_to", "comparison", "case_study",
    "faq", "advanced_technique", "tool_framework", "benchmark",
)

# A (topic, school) group with fewer tracked queries than this can't support
# a pillar + multiple distinct cluster angles - skip rather than force a
# thin cluster.
_MIN_QUERIES_PER_GROUP = 2
# Bounds LLM spend per generate_blog_ideas() call regardless of bank size;
# remaining groups are picked up on a later call since already-covered
# groups are skipped (see _covered_topic_school_pairs).
_MAX_GROUPS_PER_RUN = 5
_MAX_QUERIES_PER_PROMPT = 12
# Bounds LLM spend per generate_blog_ideas_from_persona() call - that call
# has no query-bank size to naturally cap it against, since it's mining one
# school's persona text rather than iterating groups.
_MAX_PERSONA_TOPICS_PER_RUN = 3
# Bounds how many schools generate_blog_ideas() mines persona data for in one
# run - persona-mining runs alongside the query-bank picks every run (not
# only when a school's tracked-query bank is empty), rotated by how long
# it's been since a school was last persona-mined, so it stays small and
# spends fairly across schools rather than exhausting a whole run on one.
_MAX_PERSONA_SCHOOLS_PER_RUN = 2


@lru_cache(maxsize=None)
def _load_doc(filename):
    path = os.path.join(_KNOWLEDGE_DIR, filename)
    with open(path, encoding="utf-8") as f:
        return f.read()


def _format_persona(persona, include_testimonials):
    """Renders whichever of the three saved categories are non-empty as
    labeled subsections. `include_testimonials=False` for full-post drafting
    (see module docstring / blog_personas.py: that stage deliberately never
    sees named testimonials) - structural omission rather than an
    instruction the model has to remember to follow."""
    parts = []
    if persona.get("buyer_persona"):
        parts.append(f"Buyer persona:\n{persona['buyer_persona']}")
    if persona.get("stats"):
        parts.append(f"Survey stats / original data:\n{persona['stats']}")
    if include_testimonials and persona.get("testimonials"):
        parts.append(f"Named testimonials / case-study quotes:\n{persona['testimonials']}")
    return "\n\n".join(parts)


# ─────────────────────────────────────────────────────────────────────────────
# Input bank: the full tracked-question bank, grouped by (topic, school)
# ─────────────────────────────────────────────────────────────────────────────

def _group_query_bank(days=None):
    """Every tracked mention-type question (question_router's
    get_losing_questions with the qc_share gate opened to 1.0 - no win/loss
    filter, still globally qc_share-ascending so each group's slice stays
    weakest-first), grouped by (topic, school). Topic-less questions are
    dropped: a pillar page needs a coherent subject."""
    groups = {}
    for q in get_losing_questions(days, max_qc_share=1.0):
        topic = q.get("topic")
        if not topic:
            continue
        key = (topic, q.get("school"))
        groups.setdefault(key, []).append(q)
    return {
        key: queries[:_MAX_QUERIES_PER_PROMPT]
        for key, queries in groups.items()
        if len(queries) >= _MIN_QUERIES_PER_GROUP
    }


def _covered_topic_school_pairs():
    """(topic, school) pairs that already have a pillar idea - regenerating
    a covered pair would just duplicate ideas rather than grow the backlog,
    so new runs only pick up pairs not seen before."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT DISTINCT topic, school FROM blog_ideas WHERE cluster_role = 'pillar'")
            return {(r[0], r[1]) for r in cur.fetchall()}


def get_blog_idea_candidates(days=None):
    """Live, weakest-QC-share-first list of (topic, school) pairs not yet
    covered by a pillar - same priority order generate_blog_ideas() actually
    picks from, so this is what the dashboard's "N opportunities identified"
    count reflects. Ranked by weakness (real QC citation data), not group
    size: how many distinct query phrasings we happen to track for a topic
    isn't a real demand signal, so it's reported here but never drives
    priority."""
    groups = _group_query_bank(days)
    covered = _covered_topic_school_pairs()
    pending = {k: qs for k, qs in groups.items() if k not in covered}
    return [
        {
            "topic": topic,
            "school": school,
            "n_queries": len(queries),
            # first item in the already-qc_share-ascending list = the
            # weakest query in this group - free, no extra query.
            "weakest_qc_share": queries[0]["qc_share"],
        }
        for (topic, school), queries in sorted(pending.items(), key=lambda kv: kv[1][0]["qc_share"])
    ]


# ─────────────────────────────────────────────────────────────────────────────
# LLM call: one (topic, school) group -> one pillar + N cluster ideas
# ─────────────────────────────────────────────────────────────────────────────

def _build_prompt(topic, school, queries):
    query_lines = "\n".join(
        f'- id={q["question_id"]} qc_share={round(q["qc_share"] * 100)}% text="{q["question"]}"'
        for q in queries
    )
    angle_list = ", ".join(ANGLE_VOCAB)
    persona_section = ""
    persona = get_persona(school)
    if persona:
        persona_section = f"""

=== BUYER PERSONA / ORIGINAL DATA ({school or "General"}) ===
{_format_persona(persona, include_testimonials=True)}

Use this persona data where relevant: prefer angles and hooks that match the
real buyer motivations and constraints above. Where a cluster idea's full
paragraph needs original data (per the single-post guide), prefer citing a
statistic from the stats above over inventing a generic claim. Where a
case_study-angle idea is appropriate and a named testimonial is given above,
ground it in that (verbatim short quote, properly attributed) rather than a
hypothetical example."""

    return f"""Topic: {topic}
School: {school or "General (not school-specific)"}

Tracked queries in this topic/school (AI engines rarely cite QC when
answering these - this is the query bank to optimize for, weakest QC share
first; use ONLY these ids, never invent one):
{query_lines}

Using the multi-blog pillar strategy and the single-post writing guide below,
propose ONE pillar page idea for this topic and 3-5 cluster page ideas that
together cover it from different angles ({angle_list}).

Use the tracked queries as inspiration for what real people ask about this
topic - not as templates to paraphrase. Decompose the topic into distinct
facets (e.g. for "how to become a professional dog groomer": certification
requirements, day-to-day skills, building a portfolio, pricing/setting up a
business) and write one cluster idea per facet, each phrased as its own
natural question - not a reworded tracked query. If the tracked queries
themselves span several distinct roles/entities (e.g. dog groomer vs. dog
trainer vs. dog behavior specialist), that's a legitimate way to split
clusters too - one role per idea is fine - but still give each idea its own
real facet-lens (certification, day-to-day work, experience needed, etc.),
not a copy-pasted template with only the role name swapped. A cluster idea's
target_query_ids means "this facet would genuinely help someone who asked
these queries," not "this heading restates this query."

The post `title` and the outline's `heading` (H2) do different jobs and must
NOT be near-duplicates of each other. `heading` is a direct, natural-language
question for GEO extraction. `title` is the clickable editorial headline -
it can use a colon/subtitle structure, pose a real tension or doubt, and
should read like something a human editor wrote. Example: heading = "Is a
certificate enough to become an event planner?" -> title = "Becoming an
Event Planner: Is a Certificate Good Enough?" Do NOT create the title by
swapping one or two words in the heading (e.g. "necessary" <-> "need",
"establish" <-> "build") - that is not a distinct title, it's the same
sentence twice.

Each cluster idea must still target at least one of the query ids above
(target_query_ids - grounding only, use ONLY these ids, never invent one).
Each cluster idea's outline must follow the single-post guide exactly: a
question-phrased H2 heading for that facet, a 40-60 word extractable answer
block (the standalone quotable summary, not the full paragraph), 3-5
body_points capturing what the 150-300 word full paragraph would cover
(bullet form here, not prose), and comparison.enabled true only when a real
"X vs Y" framing applies to that idea.

Each cluster idea also needs a `description` (1-2 plain-language sentences
summarizing what the article covers and who it's for - reader-facing
editorial copy, distinct from the outline's `extractable_block`, which is
the GEO-facing quotable answer) and `keywords` (2-4 short, 2-5 word
search-style phrases a reader might type, drawn from the heading/topic -
phrases only, never invent a search-volume or difficulty number for them;
those are computed separately from real tracked-query data, not authored).

=== MULTI-BLOG PILLAR STRATEGY ===
{_load_doc("blog_pillar_strategy.md")}

=== SINGLE-POST WRITING GUIDE ===
{_load_doc("blog_post_writing_guide.md")}
{persona_section}

Return JSON exactly in this shape:
{{
  "pillar": {{"title": "..."}},
  "cluster_ideas": [
    {{
      "title": "...",
      "description": "...",
      "keywords": ["...", "..."],
      "angle": "one of: {angle_list}",
      "target_query_ids": ["..."],
      "outline": {{
        "heading": "...",
        "extractable_block": "...",
        "body_points": ["...", "..."],
        "comparison": {{"enabled": false, "vs": null}}
      }}
    }}
  ]
}}"""


def _build_persona_prompt(school, persona, existing_topics):
    """Unlike _build_prompt, there's no tracked-query group to ground
    this in - the persona/stats/testimonials text IS the input, and the
    model invents the topic label itself. `existing_topics` (every topic
    already saved for this school, from either source) is passed so the
    model doesn't repropose one under a slightly different name."""
    angle_list = ", ".join(ANGLE_VOCAB)
    existing_block = "\n".join(f"- {t}" for t in existing_topics) if existing_topics else "(none yet)"

    return f"""School: {school or "General (not school-specific)"}

Below is buyer persona / survey / testimonial data collected directly from
real students and prospects for this school. Unlike the rest of this
pipeline (which starts from tracked AI-engine queries), this call starts
from that persona data alone - mine it for topics a prospective student in
this exact situation would search for or want answered, even though no
tracked query currently covers them.

=== BUYER PERSONA / ORIGINAL DATA ({school or "General"}) ===
{_format_persona(persona, include_testimonials=True)}

Topics already covered for this school (do not repeat one of these, or a
close rewording of one):
{existing_block}

Propose {_MAX_PERSONA_TOPICS_PER_RUN} distinct NEW topics this persona data
suggests. Each topic must be traceable to a specific motivation, doubt,
constraint, demographic detail, or named outcome in the data above - not a
generic industry topic that could apply to any school regardless of who its
students actually are. For each topic, using the multi-blog pillar strategy
and single-post writing guide below, propose ONE pillar page idea and 3-5
cluster page ideas that together cover it from different angles
({angle_list}).

The post `title` and the outline's `heading` (H2) do different jobs and must
NOT be near-duplicates of each other. `heading` is a direct, natural-language
question for GEO extraction. `title` is the clickable editorial headline -
it can use a colon/subtitle structure, pose a real tension or doubt, and
should read like something a human editor wrote. Do NOT create the title by
swapping one or two words in the heading - that is not a distinct title,
it's the same sentence twice.

Each cluster idea's outline must follow the single-post guide exactly: a
question-phrased H2 heading for that facet, a 40-60 word extractable answer
block (the standalone quotable summary, not the full paragraph), 3-5
body_points capturing what the 150-300 word full paragraph would cover
(bullet form here, not prose), and comparison.enabled true only when a real
"X vs Y" framing applies to that idea.

Each cluster idea also needs a `description` (1-2 plain-language sentences
summarizing what the article covers and who it's for) and `keywords` (2-4
short, 2-5 word search-style phrases a reader might type, drawn from the
heading/topic - phrases only, never invent a search-volume or difficulty
number for them).

=== MULTI-BLOG PILLAR STRATEGY ===
{_load_doc("blog_pillar_strategy.md")}

=== SINGLE-POST WRITING GUIDE ===
{_load_doc("blog_post_writing_guide.md")}

Return JSON exactly in this shape:
{{
  "topics": [
    {{
      "topic": "short topic label, e.g. 'Career Change After 40'",
      "pillar": {{"title": "..."}},
      "cluster_ideas": [
        {{
          "title": "...",
          "description": "...",
          "keywords": ["...", "..."],
          "angle": "one of: {angle_list}",
          "outline": {{
            "heading": "...",
            "extractable_block": "...",
            "body_points": ["...", "..."],
            "comparison": {{"enabled": false, "vs": null}}
          }}
        }}
      ]
    }}
  ]
}}"""


def _call_llm_json(prompt, error_context):
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=2000,
            messages=[
                {"role": "system", "content": "You are a content strategist optimizing for LLM "
                                               "citation (GEO). Follow the supplied strategy "
                                               "documents exactly. Respond with valid JSON only."},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
        )
        return json.loads(resp.choices[0].message.content)
    except Exception as e:
        logger.warning(f"Blog idea generation failed for {error_context}: {e}")
        return None


def _call_llm(topic, school, queries):
    return _call_llm_json(_build_prompt(topic, school, queries), f"{topic!r}/{school!r}")


def _call_llm_persona(school, persona, existing_topics):
    return _call_llm_json(_build_persona_prompt(school, persona, existing_topics), f"persona/{school!r}")


# ─────────────────────────────────────────────────────────────────────────────
# Priority / rationale / keyword stats - deterministic, never LLM-assigned.
# Built entirely from each idea's own validated target queries (real
# question_id/qc_share pairs already resolved above), matching this
# package's evidence-grounded ethos: the LLM writes the reader-facing prose
# (title, description, keyword phrases), but every NUMBER or claim of
# volume/weakness/priority comes from data we actually have. In particular,
# we have no external SEO search-volume or keyword-difficulty data source -
# fabricating one would misrepresent it as real, so keyword "difficulty" is
# derived from QC's own real citation share instead, and "volume" is the
# real count of tracked AI-search queries this idea targets, never a
# fabricated "N,NNN/mo" figure.
# ─────────────────────────────────────────────────────────────────────────────

_MAX_KEYWORDS = 4


def _compute_priority(targets):
    """High/medium/low, from real target-query volume and weakness (same
    "volume x weakness" spirit as api/recommendations/prioritization.py's
    evidence-based ranking) - never LLM-assigned. Persona-sourced ideas
    (targets=[]) have no query-bank signal to grade on, so they default to
    "medium" rather than a fabricated high/low."""
    if not targets:
        return "medium"
    avg_share = sum(t["qc_share"] for t in targets) / len(targets)
    if len(targets) >= 3 or avg_share <= 0.15:
        return "high"
    if len(targets) >= 2 or avg_share <= 0.35:
        return "medium"
    return "low"


def _why_this_article(topic, school, targets):
    """One sentence naming the real evidence behind this idea - built from
    already-validated target-query data, never LLM-authored prose."""
    label = topic or "this topic"
    if not targets:
        return (f"Sourced from {school or 'General'}'s buyer-persona data - no tracked AI-engine "
                f"query covers {label} yet, but the persona data points to real reader demand.")
    n = len(targets)
    weakest = min(targets, key=lambda t: t["qc_share"])
    avg_pct = round(100 * sum(t["qc_share"] for t in targets) / n)
    return (f"Targets {n} tracked quer{'y' if n == 1 else 'ies'} AI engines answer about {label} - "
            f"QC is cited only {avg_pct}% of the time on average "
            f"(as low as {round(weakest['qc_share'] * 100)}% on \"{weakest['text']}\").")


def _normalize_keywords(raw_keywords, targets):
    """LLM-authored short phrases (text only, capped at _MAX_KEYWORDS), each
    annotated with real stats derived from this idea's own targets rather
    than a fabricated external number - see module-section note above."""
    phrases = [p.strip() for p in (raw_keywords or []) if isinstance(p, str) and p.strip()][:_MAX_KEYWORDS]
    if not phrases:
        return []
    difficulty = None
    if targets:
        avg_share = sum(t["qc_share"] for t in targets) / len(targets)
        difficulty = "high" if avg_share <= 0.15 else "medium" if avg_share <= 0.35 else "low"
    return [{"phrase": p, "tracked_queries": len(targets), "difficulty": difficulty} for p in phrases]


# ─────────────────────────────────────────────────────────────────────────────
# Validation: never trust an LLM-invented angle or query id
# ─────────────────────────────────────────────────────────────────────────────

def _normalize_outline(raw):
    if not isinstance(raw, dict):
        return None
    heading = (raw.get("heading") or "").strip()
    extractable_block = (raw.get("extractable_block") or "").strip()
    body_points = [p.strip() for p in (raw.get("body_points") or []) if isinstance(p, str) and p.strip()]
    if not heading or not extractable_block or not body_points:
        return None
    comparison = raw.get("comparison") or {}
    return {
        "heading": heading,
        "extractable_block": extractable_block,
        "body_points": body_points,
        "comparison": {
            "enabled": bool(comparison.get("enabled")),
            "vs": comparison.get("vs") if comparison.get("enabled") else None,
        },
    }


def _normalize_cluster_idea(raw, queries_by_id, topic, school):
    """queries_by_id: {str(question_id): query_dict} for this group's bank -
    used both to validate target_query_ids (never trust an id the model
    invents) and to resolve display text/qc_share for the UI (never trust
    the LLM's own echo of the query text either)."""
    title = (raw.get("title") or "").strip()
    description = (raw.get("description") or "").strip()
    angle = raw.get("angle")
    target_query_ids = [str(qid) for qid in (raw.get("target_query_ids") or []) if str(qid) in queries_by_id]
    outline = _normalize_outline(raw.get("outline"))
    if not title or not description or angle not in ANGLE_VOCAB or not target_query_ids or outline is None:
        return None
    targets = [
        {
            "question_id": qid,
            "text": queries_by_id[qid]["question"],
            "qc_share": queries_by_id[qid]["qc_share"],
        }
        for qid in target_query_ids
    ]
    outline["targets"] = targets
    outline["description"] = description
    outline["keywords"] = _normalize_keywords(raw.get("keywords"), targets)
    outline["why_this_article"] = _why_this_article(topic, school, targets)
    return {
        "title": title,
        "angle": angle,
        "target_query_ids": target_query_ids,
        "outline": outline,
        "priority": _compute_priority(targets),
    }


def _normalize_response(raw, queries_by_id, topic, school):
    """None on any structural failure - a group is saved all-or-nothing,
    never a pillar with zero surviving cluster ideas under it."""
    if not isinstance(raw, dict):
        return None
    pillar_title = ((raw.get("pillar") or {}).get("title") or "").strip()
    if not pillar_title:
        return None
    cluster_ideas = [
        idea for raw_idea in (raw.get("cluster_ideas") or [])
        if (idea := _normalize_cluster_idea(raw_idea, queries_by_id, topic, school)) is not None
    ]
    if not cluster_ideas:
        return None
    return {"pillar_title": pillar_title, "cluster_ideas": cluster_ideas}


def _normalize_persona_cluster_idea(raw, topic, school):
    """Same shape as _normalize_cluster_idea minus target_query_ids - a
    persona-sourced idea has no tracked-query bank to validate ids against,
    so it's stored with an empty list instead (outline.targets stays empty,
    which _build_full_post_prompt already renders as "no tracked queries
    recorded on this idea")."""
    if not isinstance(raw, dict):
        return None
    title = (raw.get("title") or "").strip()
    description = (raw.get("description") or "").strip()
    angle = raw.get("angle")
    outline = _normalize_outline(raw.get("outline"))
    if not title or not description or angle not in ANGLE_VOCAB or outline is None:
        return None
    outline["targets"] = []
    outline["description"] = description
    outline["keywords"] = _normalize_keywords(raw.get("keywords"), [])
    outline["why_this_article"] = _why_this_article(topic, school, [])
    return {
        "title": title, "angle": angle, "target_query_ids": [], "outline": outline,
        "priority": _compute_priority([]),
    }


def _normalize_persona_response(raw, school):
    """A list of {"topic", "pillar_title", "cluster_ideas"} groups (0 or
    more survive) rather than _normalize_response's single group - one
    persona call proposes several topics at once. None only if the response
    isn't even a dict; an empty list from a dict with no valid topics is
    reported as generation_failed by the caller either way."""
    if not isinstance(raw, dict):
        return None
    topics = []
    for raw_topic in (raw.get("topics") or []):
        if not isinstance(raw_topic, dict):
            continue
        topic = (raw_topic.get("topic") or "").strip()
        pillar_title = ((raw_topic.get("pillar") or {}).get("title") or "").strip()
        if not topic or not pillar_title:
            continue
        cluster_ideas = [
            idea for raw_idea in (raw_topic.get("cluster_ideas") or [])
            if (idea := _normalize_persona_cluster_idea(raw_idea, topic, school)) is not None
        ]
        if not cluster_ideas:
            continue
        topics.append({"topic": topic, "pillar_title": pillar_title, "cluster_ideas": cluster_ideas})
    return topics


# ─────────────────────────────────────────────────────────────────────────────
# Persistence
# ─────────────────────────────────────────────────────────────────────────────

def _save_group_idea(cur, batch_id, topic, school, idea, source="query_bank"):
    all_query_ids = sorted({qid for c in idea["cluster_ideas"] for qid in c["target_query_ids"]})
    cur.execute("""
        INSERT INTO blog_ideas (batch_id, cluster_role, parent_id, topic, school, title, target_query_ids, source)
        VALUES (%s, 'pillar', NULL, %s, %s, %s, %s, %s)
        RETURNING id
    """, (batch_id, topic, school, idea["pillar_title"], Json(all_query_ids), source))
    pillar_id = cur.fetchone()[0]

    for cluster in idea["cluster_ideas"]:
        cur.execute("""
            INSERT INTO blog_ideas (batch_id, cluster_role, parent_id, topic, school, title, angle, target_query_ids, outline, source, priority)
            VALUES (%s, 'cluster', %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            batch_id, pillar_id, topic, school, cluster["title"], cluster["angle"],
            Json(cluster["target_query_ids"]), Json(cluster["outline"]), source, cluster["priority"],
        ))
    return pillar_id


def _existing_topics_for_school(school):
    """Every topic already saved for this school (either source) - passed
    into the persona prompt so it doesn't repropose a topic the query-bank
    path (or an earlier persona call) already covered."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT DISTINCT topic FROM blog_ideas
                WHERE cluster_role = 'pillar' AND topic IS NOT NULL
                    AND COALESCE(school, '') = COALESCE(%s, '')
            """, (school,))
            return [r[0] for r in cur.fetchall()]


def _last_persona_generated_at_by_school():
    """{school: most recent generated_at} over persona-sourced pillars only
    - used to rotate generate_blog_ideas()'s persona pass fairly across
    schools (never-mined and longest-since-mined schools go first) instead
    of always hitting the same one or two."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT school, MAX(generated_at) FROM blog_ideas
                WHERE cluster_role = 'pillar' AND source = 'persona'
                GROUP BY school
            """)
            return {r[0]: r[1] for r in cur.fetchall()}


def generate_blog_ideas(days=None):
    """The dashboard's single "Generate ideas" entry point
    (dashboard/src/tabs/BlogIdeas.jsx) - fully automatic, no human picks a
    (topic, school) pair or a generation mode, and no either/or between the
    tracked-query bank and persona data - both run every call:

      1. Auto-picks the weakest _MAX_GROUPS_PER_RUN uncovered (topic,
         school) groups from the tracked-query bank, ranked by QC's real
         citation share on each group's weakest query. Deliberately NOT
         ranked by group size (how many distinct query phrasings we happen
         to track for a topic) - that's an artifact of what got tracked, not
         a real demand signal, so it's reported (n_queries) but never used
         to prioritize.
      2. Independently, mines persona data for up to
         _MAX_PERSONA_SCHOOLS_PER_RUN schools with saved persona data,
         rotated by how long it's been since each was last persona-mined
         (never-mined schools first) - this runs alongside step 1 regardless
         of whether a school also got a query-bank pick this call, so a
         school's ideas can come from both sources in the same run rather
         than one path blocking the other.

    Never raises for a single group/school's LLM failure - it's just
    skipped and left for a later run."""
    groups = _group_query_bank(days)
    covered = _covered_topic_school_pairs()
    pending = {k: qs for k, qs in groups.items() if k not in covered}
    groups_this_run = sorted(pending, key=lambda k: pending[k][0]["qc_share"])[:_MAX_GROUPS_PER_RUN]

    batch_id = str(uuid.uuid4())
    pillars_saved, clusters_saved, skipped, succeeded = 0, 0, [], []

    if groups_this_run:
        with get_connection() as conn:
            with conn.cursor() as cur:
                for topic, school in groups_this_run:
                    queries = pending[(topic, school)]
                    queries_by_id = {str(q["question_id"]): q for q in queries}
                    raw = _call_llm(topic, school, queries)
                    idea = _normalize_response(raw, queries_by_id, topic, school) if raw is not None else None
                    if idea is None:
                        skipped.append({"topic": topic, "school": school})
                        continue
                    _save_group_idea(cur, batch_id, topic, school, idea)
                    succeeded.append({"topic": topic, "school": school})
                    pillars_saved += 1
                    clusters_saved += len(idea["cluster_ideas"])
            conn.commit()

    # Persona pass: independent of the query-bank picks above - rotated by
    # how long it's been since each school was last persona-mined (never
    # -mined schools sort first), so it's a fair rotation, not a fallback
    # gated on the query-bank being empty for that school.
    last_mined = _last_persona_generated_at_by_school()
    persona_candidate_schools = sorted(
        (p["school"] for p in get_all_personas()),
        key=lambda school: (1, last_mined[school]) if school in last_mined else (0,),
    )

    persona_pillars = persona_clusters = 0
    persona_topics = []
    for school in persona_candidate_schools[:_MAX_PERSONA_SCHOOLS_PER_RUN]:
        result = generate_blog_ideas_from_persona(school)
        if result["generated"]:
            persona_pillars += result["pillars"]
            persona_clusters += result["cluster_ideas"]
            persona_topics.append({"school": school, "topics": result["topics"]})

    if not succeeded and not persona_topics:
        return {"generated": False, "reason": "no_new_topics", "pillars": 0, "cluster_ideas": 0,
                "topics": [], "skipped_topics": skipped, "persona_topics": []}

    return {
        "generated": True,
        "batch_id": batch_id,
        "pillars": pillars_saved + persona_pillars,
        "cluster_ideas": clusters_saved + persona_clusters,
        "topics": succeeded,
        "skipped_topics": skipped,
        "persona_topics": persona_topics,
    }


def generate_blog_ideas_from_persona(school):
    """Generate pillar/cluster ideas mined from one school's saved
    buyer-persona/stats/testimonials data alone (blog_personas.get_persona),
    rather than the tracked-query bank generate_blog_ideas() draws from -
    lets ideation surface a topic no AI-engine query has surfaced yet but
    that the persona data itself points to (a specific doubt, demographic
    constraint, or named outcome). One call proposes up to
    _MAX_PERSONA_TOPICS_PER_RUN topics at once, each saved as its own
    pillar + cluster set with source='persona' and empty target_query_ids
    (see migrations/015_blog_ideas_source.sql). Shares the same blog_ideas
    table and cooldown gate (get_blog_idea_generation_status) as the
    query-bank path - callers should check that status the same way before
    calling this."""
    persona = get_persona(school)
    if persona is None:
        return {"generated": False, "reason": "no_persona", "pillars": 0, "cluster_ideas": 0}

    existing_topics = _existing_topics_for_school(school)
    raw = _call_llm_persona(school, persona, existing_topics)
    topics = _normalize_persona_response(raw, school) if raw is not None else None
    if not topics:
        return {"generated": False, "reason": "generation_failed", "pillars": 0, "cluster_ideas": 0}

    batch_id = str(uuid.uuid4())
    pillars_saved = 0
    clusters_saved = 0

    with get_connection() as conn:
        with conn.cursor() as cur:
            for topic_group in topics:
                _save_group_idea(
                    cur, batch_id, topic_group["topic"], school,
                    {"pillar_title": topic_group["pillar_title"], "cluster_ideas": topic_group["cluster_ideas"]},
                    source="persona",
                )
                pillars_saved += 1
                clusters_saved += len(topic_group["cluster_ideas"])
        conn.commit()

    return {
        "generated": pillars_saved > 0,
        "batch_id": batch_id,
        "pillars": pillars_saved,
        "cluster_ideas": clusters_saved,
        "topics": [t["topic"] for t in topics],
    }


def get_blog_idea_generation_status(cooldown_days=GENERATION_COOLDOWN_DAYS):
    """Same cadence-gate shape as the rec engine's get_generation_status, so
    the dashboard button can reuse the same lock/countdown pattern."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT MAX(generated_at) FROM blog_ideas")
            last_generated_at = cur.fetchone()[0]

    if last_generated_at is None:
        return {"last_generated_at": None, "next_available_at": None, "can_generate": True}

    next_available_at = last_generated_at + timedelta(days=cooldown_days)
    return {
        "last_generated_at": last_generated_at.isoformat(),
        "next_available_at": next_available_at.isoformat(),
        "can_generate": datetime.now(timezone.utc) >= next_available_at,
    }


_SELECT = """
    SELECT id, batch_id, cluster_role, parent_id, topic, school, title, angle,
           target_query_ids, outline, status, generated_at, body, source, priority
    FROM blog_ideas
"""


def _idea_dict(r):
    return {
        "id": str(r[0]),
        "batch_id": str(r[1]) if r[1] is not None else None,
        "cluster_role": r[2],
        "parent_id": str(r[3]) if r[3] is not None else None,
        "topic": r[4],
        "school": r[5],
        "title": r[6],
        "angle": r[7],
        "target_query_ids": r[8] or [],
        "outline": r[9],
        "status": r[10],
        "generated_at": str(r[11]),
        "body": r[12],
        "source": r[13],
        "priority": r[14],
    }


def get_blog_ideas():
    """Flat list (pillars and clusters both), newest first - the dashboard
    groups cluster rows under their parent_id client-side, same pattern
    Prompts.jsx already uses for topic/prompt grouping."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(f"{_SELECT} ORDER BY generated_at DESC")
            rows = cur.fetchall()
    return [_idea_dict(r) for r in rows]


def get_blog_idea(idea_id):
    """One idea (pillar or cluster) by id - powers its own detail page
    (dashboard/src/pages/BlogIdeaDetail.jsx), same pattern as
    get_recommendation() backing /recommendations/:recId."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(f"{_SELECT} WHERE id = %s", (idea_id,))
            row = cur.fetchone()
    return _idea_dict(row) if row else None


def update_blog_idea_status(idea_id, status):
    if status not in ("idea", "drafted", "published"):
        raise ValueError(f"Invalid blog idea status: {status!r}")
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE blog_ideas SET status = %s WHERE id = %s", (status, idea_id))
        conn.commit()


# ─────────────────────────────────────────────────────────────────────────────
# Full-post drafting: one cluster idea -> a complete published article
#
# Ideation above only ever produces a brief (heading, a 40-60 word
# extractable block, and bullet points describing what the full paragraph
# would cover - not the paragraph itself). This is the second, separate
# generation stage that turns one specific cluster idea into an actual
# publish-ready draft, triggered per-idea by a human (the "Generate full
# post" button on the idea's own page, pages/BlogIdeaDetail.jsx) rather than
# swept automatically - most ideas in the backlog will never be worth
# spending on.
#
# A published post is NOT one "Structure per heading" unit (that earlier,
# smaller version of this function only produced a single H2 + block +
# paragraph + takeaway, ~200 words - a comparison against a real target
# example showed that's ~1/8th the length and missing most of the guide's
# own checklist). A full post is: a persona-targeted opener, a TL;DR, the
# idea's own fixed heading/block expanded into the main answer section, 2-4
# additional H2 sub-facet sections, an optional comparison table, 1-2
# illustrative Challenge->Intervention->Result vignettes, an FAQ, and a
# closing CTA. The idea's planned heading and extractable block are spliced
# in verbatim rather than re-asked of the model, so the published draft
# can't silently drift from what a human already reviewed at the idea
# stage. Testimonial integration (named quotes from the saved persona
# content) is still deliberately out of scope here - only survey-style
# statistics are used, and the prompt explicitly tells the model not to
# quote a named individual in this draft. Vignettes are explicitly
# illustrative/hypothetical (not claimed as real documented cases), since we
# have no real case data to ground them in yet.
#
# The writing guide is injected in full, but a small model won't reliably
# self-enforce a 200+ line doc against its own generation - the hard
# constraints most likely to get skipped (banned AI-tell filler transitions
# and their synonym variants, inventing an unsupported claim to sound
# authoritative when no real data is available, a title that's just a
# reworded heading) are called out explicitly in the prompt below instead of
# trusted to the doc alone. One deliberate override of the guide: Section 6
# bans promotional language/CTAs outright, but a closing CTA is kept here at
# the user's explicit direction - it's the one guide rule this function
# intentionally does not enforce. Scope note: this still does NOT attempt
# live citation hyperlinks, structured-data/schema markup, or content-mode
# assignment - those are deterministic templating work, not prose the model
# should freehand.
# ─────────────────────────────────────────────────────────────────────────────

_BANNED_FILLER_NOTE = (
    'No banned AI-tell filler transitions or their synonyms: "Additionally,", '
    '"Furthermore,", "Moreover,", "It is also essential", "It\'s also crucial", '
    '"It is important to note", "Overall,", "In conclusion," - and no sentence, '
    "however worded, whose only job is to introduce a restatement of a point "
    "already made rather than new information."
)


def _build_full_post_prompt(idea):
    outline = idea["outline"] or {}
    heading = outline.get("heading", idea["title"])
    block = outline.get("extractable_block", "")
    points = outline.get("body_points") or []
    comparison = outline.get("comparison") or {}
    targets = outline.get("targets") or []
    target_lines = "\n".join(
        f'- "{t["text"]}" (QC cited {round(t["qc_share"] * 100)}% of the time)' for t in targets
    ) or "(no tracked queries recorded on this idea)"

    persona_section = ""
    persona = get_persona(idea["school"])
    persona_text = _format_persona(persona, include_testimonials=False) if persona else ""
    if persona_text:
        persona_section = f"""

=== BUYER PERSONA / ORIGINAL DATA ({idea["school"] or "General"}) ===
Use the persona and survey stats below (motivations, demographics, learning
preferences, format preferences, completion timeline, social platform, etc.)
as original-data support throughout the piece - the opener, the sections,
and the FAQ should all draw on these where relevant. Named testimonials are
deliberately not included here - that's a later phase, not part of this
draft.
{persona_text}"""

    return f"""Write a complete, publish-ready blog post for QC ({idea["school"] or "General"}), following the single-post writing guide below.

Post angle: {idea["title"]} ({idea["angle"]})
Target queries this post answers:
{target_lines}

Planned main section (already fixed, do not change - expand into real prose,
do not just restate the bullets):
- H2 heading: "{heading}"
- Extractable answer block: "{block}"
- Key points the full paragraph should cover: {"; ".join(points) if points else "(none recorded)"}
- Comparison: {f'enabled, vs {comparison.get("vs")}' if comparison.get("enabled") else "not applicable"}

=== SINGLE-POST WRITING GUIDE ===
{_load_doc("blog_post_writing_guide.md")}
{persona_section}

Write the FULL post, not just the main section. Structure:
1. h1_title - the clickable editorial headline. Can use a colon/subtitle,
   should pose the real tension or doubt behind the question. Must NOT be a
   synonym-reworded copy of the H2 heading above (e.g. swapping "necessary"
   for "need") - that is the same sentence twice, not a distinct title.
2. opener - 1-2 sentences naming the specific reader/persona this post
   speaks to and giving the direct answer up front, including its key
   condition or nuance.
3. tldr - exactly 3 bullet points, the core claims of the whole piece.
4. main_section - expands the fixed heading/block above: full_paragraph
   (150-300 words) + bold_takeaway. Do NOT open full_paragraph by restating
   the extractable block's sentence verbatim or near-verbatim - the block is
   already shown directly above it in the published post; start with new
   information instead.
5. sections - 2-4 ADDITIONAL H2 sub-facets of the same core question (not
   covered by the main section) - each its own natural question, with
   full_paragraph (120-250 words) + bold_takeaway.
6. comparison_table - only if comparison is enabled above.
7. vignettes - 1-2 illustrative Challenge/Intervention/Result scenarios
   showing what acting on this advice looks like. These are explicitly
   hypothetical/illustrative (phrase them as "a [persona]..." not as a named
   real person or a documented QC case) - do not present them as real
   verified outcomes.
8. faq - 3-5 question/answer pairs covering realistic follow-up questions;
   prefer citing the real data given above in answers over generic claims.
9. cta - ONE closing sentence inviting the reader to explore the relevant QC
   program/course by name. This is the one exception to the guide's
   no-promotional-language rule - keep it to one sentence, genuine next step
   framing, not hype, and use a bracketed placeholder like "[Explore
   {idea["school"] or "QC's programs"}]" rather than a fabricated URL. Do not
   prefix the school name with "QC's" if it already starts with "QC" (e.g.
   "QC Pet Studies", not "QC's QC Pet Studies").

Hard constraints, on top of the guide above, applying to every paragraph in
opener/main_section/sections/vignettes/faq:
- {_BANNED_FILLER_NOTE}
- No invented claims. Do not state a comparative, statistical, or benefit
  claim (e.g. "higher earning potential", "growing demand") unless directly
  backed by the tracked-query data or persona statistics given above. If no
  such data exists for a claim, ground it in the concrete, verifiable
  mechanics of the named organization/process instead.
- Prefer real, specific named entities (a certifying body, standard, or
  organization already implied by the topic) over generic phrasing - but
  never fabricate a specific number or fact about a named entity beyond
  what's given in this prompt.

Return JSON exactly in this shape:
{{
  "h1_title": "...",
  "opener": "...",
  "tldr": ["...", "...", "..."],
  "main_section": {{"full_paragraph": "...", "bold_takeaway": "..."}},
  "sections": [
    {{"heading": "...", "full_paragraph": "...", "bold_takeaway": "..."}}
  ],
  "comparison_table": null,
  "vignettes": [
    {{"heading": "...", "challenge": "...", "intervention": "...", "result": "..."}}
  ],
  "faq": [
    {{"question": "...", "answer": "..."}}
  ],
  "cta": "..."
}}
If comparison is enabled above, set comparison_table to:
{{"vs": "...", "rows": [{{"label": "...", "a": "...", "b": "..."}}]}}"""


def _call_llm_full_post(prompt):
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=3500,
            messages=[
                {"role": "system", "content": "You are a content writer producing a complete, "
                                               "publish-ready article that follows the supplied "
                                               "writing guide exactly. Respond with valid JSON only."},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
        )
        return json.loads(resp.choices[0].message.content)
    except Exception as e:
        logger.warning(f"Full-post generation failed: {e}")
        return None


# Mechanical safety net, not another LLM call - the prompt tells the model
# not to use these filler transitions and their synonyms, but a small model
# doesn't reliably self-enforce that over a long multi-section response
# (observed 7 occurrences of the exact banned words in one real draft
# despite the explicit instruction, then a second draft dodged those exact
# words but produced new synonyms - "In addition to X," "Consequently," -
# confirming this needs to match the *pattern* of a throat-clearing
# sentence-opener, not a fixed phrase list, since the model will keep
# finding new synonyms for whichever exact words are banned). Only strips at
# a real sentence boundary (start of string, or right after ./!/?), so it
# can't clip a mid-sentence word. "In addition to <clause>," loses that
# clause's content when stripped (unlike the single-word openers) - an
# accepted lossy tradeoff since leaving the filler pattern in is worse.
_FILLER_RE = re.compile(
    r"(^|[.!?]\s+)(?:"
    r"Additionally|Furthermore|Moreover|Overall|In conclusion|Consequently|"
    r"As a result|Notably|Importantly|Similarly|Likewise|"
    r"It is also essential|It's also crucial|It is important to note|"
    r"It's worth noting|It is worth noting|In addition(?:\s+to\s+[^,]+)?"
    r")\s*,\s*",
    re.IGNORECASE,
)
_SENTENCE_START_RE = re.compile(r"(^|[.!?]\s+)([a-z])")


def _strip_banned_filler(text):
    stripped = _FILLER_RE.sub(lambda m: m.group(1), text)
    return _SENTENCE_START_RE.sub(lambda m: m.group(1) + m.group(2).upper(), stripped)


def _clean(v):
    return _strip_banned_filler(str(v or "").strip())


def _normalize_full_post(raw, outline):
    """Assembles the stored markdown ourselves from validated pieces rather
    than trusting LLM-authored markdown - the main section's heading/block
    come from the idea's own outline (never re-trusted from the model's
    echo). Fails closed on the structural minimum (title, opener, 3-item
    TL;DR, main section, >=1 additional section, >=2 FAQ pairs, a CTA);
    individual malformed sections/vignettes/FAQ entries are dropped rather
    than failing the whole draft, since a large multi-field JSON response
    from a small model is more likely to have one bad item than be entirely
    broken."""
    if not isinstance(raw, dict):
        return None

    h1 = _clean(raw.get("h1_title"))
    opener = _clean(raw.get("opener"))
    tldr = [_clean(b) for b in (raw.get("tldr") or []) if _clean(b)]
    cta = _clean(raw.get("cta"))
    heading = _clean(outline.get("heading"))
    block = _clean(outline.get("extractable_block"))

    main = raw.get("main_section") or {}
    main_paragraph = _clean(main.get("full_paragraph"))
    main_takeaway = _clean(main.get("bold_takeaway"))

    sections = []
    for s in (raw.get("sections") or []):
        if not isinstance(s, dict):
            continue
        s_heading = _clean(s.get("heading"))
        s_paragraph = _clean(s.get("full_paragraph"))
        s_takeaway = _clean(s.get("bold_takeaway"))
        if s_heading and s_paragraph and s_takeaway:
            sections.append((s_heading, s_paragraph, s_takeaway))

    if not h1 or not opener or len(tldr) < 3 or not main_paragraph or not main_takeaway \
            or not heading or not block or not sections or not cta:
        return None

    lines = [f"# {h1}", "", opener, "", "## TL;DR"]
    lines += [f"- {b}" for b in tldr]
    lines += ["", f"## {heading}", "", block, "", main_paragraph, "", f"**{main_takeaway}**"]

    for s_heading, s_paragraph, s_takeaway in sections:
        lines += ["", f"## {s_heading}", "", s_paragraph, "", f"**{s_takeaway}**"]

    table = raw.get("comparison_table")
    if isinstance(table, dict) and isinstance(table.get("rows"), list) and table["rows"]:
        vs = _clean(table.get("vs")) or "Comparison"
        lines += ["", f"### {vs}", "", "| | A | B |", "|---|---|---|"]
        for row in table["rows"][:8]:
            if not isinstance(row, dict):
                continue
            label = _clean(row.get("label")).replace("|", "/")
            a = _clean(row.get("a")).replace("|", "/")
            b = _clean(row.get("b")).replace("|", "/")
            if label or a or b:
                lines.append(f"| {label} | {a} | {b} |")

    vignettes = []
    for v in (raw.get("vignettes") or []):
        if not isinstance(v, dict):
            continue
        v_heading = _clean(v.get("heading"))
        challenge, intervention, result = _clean(v.get("challenge")), _clean(v.get("intervention")), _clean(v.get("result"))
        if v_heading and challenge and intervention and result:
            vignettes.append((v_heading, challenge, intervention, result))
    if vignettes:
        lines += ["", "## What this looks like in practice"]
        for v_heading, challenge, intervention, result in vignettes[:3]:
            lines += [
                "", f"**{v_heading}**",
                f"- Challenge: {challenge}",
                f"- Intervention: {intervention}",
                f"- Result: {result}",
            ]

    faq = []
    for qa in (raw.get("faq") or []):
        if not isinstance(qa, dict):
            continue
        q, a = _clean(qa.get("question")), _clean(qa.get("answer"))
        if q and a:
            faq.append((q, a))
    if len(faq) < 2:
        return None
    lines += ["", "## FAQ"]
    for q, a in faq[:6]:
        lines += ["", f"**{q}**", a]

    lines += ["", cta]

    return "\n".join(lines)


def generate_full_post(idea_id):
    """On-demand full-post draft for one cluster idea. Returns
    {"generated": True, "idea": <updated row>} or
    {"generated": False, "reason": "not_found" | "generation_failed"}."""
    idea = get_blog_idea(idea_id)
    if idea is None or idea["cluster_role"] != "cluster":
        return {"generated": False, "reason": "not_found"}

    prompt = _build_full_post_prompt(idea)
    raw = _call_llm_full_post(prompt)
    body = _normalize_full_post(raw, idea["outline"] or {}) if raw is not None else None
    if body is None:
        return {"generated": False, "reason": "generation_failed"}

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE blog_ideas SET body = %s, status = 'drafted' WHERE id = %s", (body, idea_id))
        conn.commit()

    return {"generated": True, "idea": get_blog_idea(idea_id)}
