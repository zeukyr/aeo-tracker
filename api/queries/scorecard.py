"""
"Improve Existing Pages" scorecard - the question router's FIX-branch leaf
(originally Phase 4 of docs/ai/recommendation-two-tab-plan.md, as
tab2_scorecard.py).

For a topic where QC HAS a page but engines skip it, this compares QC's page
against the top pages AI actually cites for the topic and produces the
intersection recommendation: a GEO-important feature that the cited pages
consistently have and QC lacks. The scorecard is the reasoning, so the
resulting rec is concrete (names the page, the missing sections) instead of
"improve the existing content".

Two detection layers per the plan:
  - deterministic features come straight from page_facts (schema, tables, ...);
  - semantic features (direct-answer-first, certification section, ...) are
    judged by one LLM pass per page over the extracted text.
Plus one emergent-pattern LLM call: what do the cited pages share that QC
lacks, beyond the fixed checklist.

Recommend rule (geo_weight is a veto floor, not a ranker): a feature is
recommended when EITHER (a) it is present in MOST cited pages ("consensus"),
OR (b) it is a "high" geo_weight feature present on the single most-cited
("top") comparable winner ("top_competitor") - a majority vote is rarely
reachable with the 3-5 readable winners a typical topic has, so requiring it
for every feature left most topics with nothing to recommend even when the
single strongest competitor clearly out-executes QC. The top-competitor path
is deliberately restricted to "high" weight only: single-instance evidence
is trustworthy enough to act on for the highest-confidence features, but not
for medium/low ones, which still require real cross-winner agreement. Either
way QC must lack the feature and geo_weight must not be "low".

The rec is EVIDENCE-GRADED, not binary: checklist gaps that clear the
consensus bar over a sufficient winner sample are tier "high"; a gap backed
only by the single top-cited competitor is tier "named" (concrete and real,
but single-instance); thin samples, sub-threshold gaps and the emergent LLM
pattern are tier "low" (still surfaced, clearly labelled). None is reserved
for the three genuinely empty states named by scorecard_triage_reason.
Unreadable cited winners are disclosed on the card, never silently dropped
from the denominator.
"""

import os
import json
import re
import statistics

from openai import OpenAI

from src.logger import logger
from api.queries.cited_urls import get_topic_cited_urls
from api.queries.page_facts import (
    get_pages_facts, get_page_facts, page_genre, winner_genre, winner_format, school_for_url,
    query_term_coverage, source_type,
)

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

_FEATURES_PATH = os.path.join(os.path.dirname(__file__), "..", "knowledge", "geo_features.json")

MIN_WINNERS = 3          # below this the comparison isn't trustworthy (high tier)
MIN_READABLE_WINNERS = 2 # below this there is no comparison at all - insufficient data
TOP_N_WINNERS = 15       # cited pages to compare against

# Cited pages fail to fetch (403s, JS-rendered pages, paywalls) or turn out
# not to be a comparable page_type often enough that asking for exactly
# TOP_N_WINNERS candidates routinely leaves fewer than that once the
# readability/genre filter below runs - overfetch by a wide margin so there's
# real headroom to still land TOP_N_WINNERS comparable winners.
CANDIDATE_POOL = 20

# Cited page types that carry a comparable information architecture. Community
# threads, videos and pages we couldn't read can't be scored.
_COMPARABLE_TYPES = {"competitor", "roundup", "directory", "association", "government", "guide", "editorial"}

# Priority order for LEADING a recommendation's narrative when several ratio
# ("metric") features are out of range at once - not a gate (the target-range
# check already decides in/out), just which one gets named as THE generic GEO
# fix so the card stays decisive instead of listing every failing metric.
# Deliberately NOT competitor-cross-compared (these are template/CMS-level
# properties measured against a small, often partly-unfetchable winner sample -
# noisy and not what the underlying research measured); ranked by how directly
# research-backed the metric is: query_term_coverage first (a page that never
# uses the query's own words can't be found regardless of structure), then
# macro-structure (44.9% of the structural-optimization effect in the source
# study), meso-structure (39.7%), then micro-structure (15.4%, the smallest and
# lowest-confidence slice).
_METRIC_PRIORITY = {
    "query_term_coverage": 0,
    "internal_linking_density": 1,
    "heading_hierarchy_depth": 2,
    "structured_content_ratio": 3,
    "paragraph_length_conformance": 4,
    "emphasis_density": 5,
}


# Features that don't apply to a commercial/course sales page - a course
# listing has no "author" to byline, so never recommend it there even when
# most cited winners (editorial guides) happen to have one. comparison_table/
# comparison_structure assume the page is weighing multiple options against
# each other ("X vs Y") - QC's course page sells ONE course, it isn't a
# roundup of alternatives, so "add a comparison" is never the right edit
# there even when cited editorial roundups (which ARE comparing options)
# commonly have one.
_INAPPLICABLE_ON_COMMERCIAL = {"author_expertise", "comparison_table", "comparison_structure"}


def _load_features():
    with open(_FEATURES_PATH, "r", encoding="utf-8") as f:
        return json.load(f)["features"]


def _effective_geo_weight(feat, genre):
    """Resolve a feature's geo_weight for the genre it's being scored against.
    Most features are genre-flat; a few carry a geo_features.json
    'geo_weight_by_genre' override where real-world lift measurably differs
    by genre (e.g. certification_pathway: a 2026-07-27 citation-correlation
    check found 1.43x lift on informational pages vs a weak 1.08x on
    commercial ones) - scoring those identically regardless of genre would
    overstate the commercial-page case. None/unmatched genre falls back to
    the feature's plain geo_weight."""
    overrides = feat.get("geo_weight_by_genre") or {}
    return overrides.get(genre, feat["geo_weight"])


# ─────────────────────────────────────────────────────────────────────────────
# Feature detection
# ─────────────────────────────────────────────────────────────────────────────

def _deterministic_present(feature_id, facts):
    """Read a deterministic feature off page_facts['features']."""
    f = facts.get("features") or {}
    if feature_id == "faq_schema":
        return bool(f.get("faq_schema"))
    if feature_id == "question_headings":
        return (f.get("question_headings") or 0) >= 2
    if feature_id == "comparison_table":
        return bool(f.get("comparison_table"))
    if feature_id == "org_schema":
        return bool(f.get("org_schema") or f.get("course_schema"))
    if feature_id == "video_embed":
        return bool(f.get("video_embed"))
    return False


def _semantic_features(facts, question, semantic_specs):
    """
    One LLM pass over a page's extracted text: does it have each semantic
    feature? Cached on the page_facts entry (keyed by the question) so a
    re-run doesn't re-call. Returns {feature_id: bool}.
    """
    if facts.get("status") != "ok":
        return {s["id"]: False for s in semantic_specs}

    cache_key = f"__semantic__{question}"
    if cache_key in facts:
        return facts[cache_key]

    checklist = "\n".join(f'- "{s["id"]}": {s["description"]}' for s in semantic_specs)
    prompt = f"""Topic question: "{question}"

Page title: {facts.get("title")}
Page headings: {json.dumps((facts.get("headings") or [])[:25])}
Page text (excerpt):
{(facts.get("content_excerpt") or "")[:3500]}

For each feature below, answer true only if the page clearly has it, false otherwise:
{checklist}

Return JSON: {{ {", ".join(f'"{s["id"]}": true|false' for s in semantic_specs)} }}"""

    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=400,
            messages=[
                {"role": "system", "content": "You inspect web-page content. Respond with valid JSON only."},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
        )
        result = json.loads(resp.choices[0].message.content)
        out = {s["id"]: bool(result.get(s["id"])) for s in semantic_specs}
    except Exception as e:
        logger.warning(f"Semantic feature pass failed for {facts.get('url')}: {e}")
        out = {s["id"]: False for s in semantic_specs}

    facts[cache_key] = out
    return out


def _page_features(facts, question, features):
    """All boolean feature ids -> present bool for one page (deterministic +
    semantic only; 'ratio' features are scored separately by _ratio_value,
    against a fixed target range rather than a per-page bool)."""
    semantic_specs = [f for f in features if f["detection"] == "semantic"]
    semantic = _semantic_features(facts, question, semantic_specs)
    present = {}
    for feat in features:
        if feat["detection"] == "semantic":
            present[feat["id"]] = semantic.get(feat["id"], False)
        elif feat["detection"] == "deterministic":
            present[feat["id"]] = _deterministic_present(feat["id"], facts)
    return present


def _fix_hint(feat, qc_value, in_range):
    """Direction-aware, concrete "what to actually change" text for an
    out-of-range structural metric - these are generic template/CMS-level
    properties (not winner-verified), so the guidance is fixed per metric
    and direction rather than derived from this topic's cited pages. None
    when in range, unmeasurable, or the feature has no guidance for that
    direction (e.g. paragraph conformance/query-term coverage can't
    realistically be "too high" against a 100% target_max)."""
    if qc_value is None or in_range:
        return None
    direction = "fix_above" if qc_value > feat["target_max"] else "fix_below"
    return feat.get(direction)


def _ratio_value(feature_id, facts, question):
    """Numeric value for a 'ratio'-detection feature (geo_features.json), or
    None when not measurable. query_term_coverage is question-specific so it's
    computed here rather than cached on page_facts; the rest come straight off
    the page_facts.py-computed structural metrics."""
    if facts.get("status") != "ok":
        return None
    if feature_id == "query_term_coverage":
        return query_term_coverage(question, facts.get("content_excerpt") or "")
    return (facts.get("features") or {}).get(feature_id)


# ─────────────────────────────────────────────────────────────────────────────
# Emergent pattern pass
# ─────────────────────────────────────────────────────────────────────────────

def _emergent_pattern(qc_facts, winner_facts, question, qc_genre=None):
    """
    One LLM call: what content/ordering pattern do the cited pages share that
    QC's page lacks? Grounded in the fetched outlines; labelled lower-confidence.

    qc_genre gates what kind of edit is even askable: cited winners are
    frequently roundup/editorial pages that compare MULTIPLE courses or
    certifications - a pattern that's real for THEM but doesn't transfer to
    QC's page when it's commercial (a single course's own sales page, not a
    directory). Without this the LLM would happily suggest "add a roundup of
    top certifications" to a page that only has the one QC sells.
    """
    def outline(f):
        return {"title": f.get("title"), "headings": (f.get("headings") or [])[:18]}

    genre_note = (
        "\n\nQC's page is COMMERCIAL: it sells one specific course, it is not a directory or "
        "roundup of options. Never suggest a section that compares, ranks, or lists multiple "
        "courses/certifications/providers (e.g. \"top N certifications\", \"X vs Y\") - QC has only "
        "the one course to offer, so that kind of section doesn't apply here even if cited pages "
        "have it. Only suggest edits about QC's own single course."
        if qc_genre == "commercial" else ""
    )

    prompt = f"""Topic question: "{question}"

QC's page outline:
{json.dumps(outline(qc_facts), indent=1)}

Outlines of the pages AI engines cite for this topic:
{json.dumps([outline(f) for f in winner_facts], indent=1)}

What content or ordering pattern do the cited pages consistently share that QC's page does
NOT? Focus on information architecture (what they cover and in what order), not styling. Be
specific and only claim patterns visible across most cited outlines. If there is no clear
shared pattern QC lacks, say so.{genre_note}

Return JSON: {{"insight": "one or two sentences, or empty if none", "edit": "one short, concrete section-level change for QC (under 12 words), or empty"}}"""
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=300,
            messages=[
                {"role": "system", "content": "You compare web-page information architecture. Respond with valid JSON only."},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
        )
        r = json.loads(resp.choices[0].message.content)
        return (r.get("insight") or "").strip(), (r.get("edit") or "").strip()
    except Exception as e:
        logger.warning(f"Emergent pattern pass failed: {e}")
        return "", ""


# ─────────────────────────────────────────────────────────────────────────────
# Scorecard
# ─────────────────────────────────────────────────────────────────────────────

_PREVALENCE_MOST = 0.6


def _prevalence_label(present, total):
    if total == 0:
        return "none"
    frac = present / total
    return "most" if frac >= _PREVALENCE_MOST else ("some" if frac >= 0.3 else "few")


def _comparable_target_winners(winner_facts, target_genre, min_winners):
    """
    Shared winner-set resolution for BUILD-branch analysis (checklist + page
    plan): comparable page types, genre-stratified to winners that share the
    KIND of page being built when enough of them exist (falls back to the
    full comparable pool otherwise - never asserts a stratum that isn't
    there), sorted by citation weight. [] below min_winners - a builder needs
    a real sample to name required features, same bar the fix side uses.
    """
    comparable = [f for f in (winner_facts or [])
                  if f.get("status") == "ok" and f.get("page_type") in _COMPARABLE_TYPES]
    if target_genre:
        matched = [f for f in comparable if winner_genre(f) == target_genre]
        if len(matched) >= min_winners:
            comparable = matched
    comparable.sort(key=lambda f: -(f.get("citation_count") or 0))
    return comparable if len(comparable) >= min_winners else []


def build_winner_checklist(winner_facts, question, target_genre=None, min_winners=MIN_WINNERS):
    """
    For a BUILD rec (no existing QC page to score against): which
    geo_features.json checklist features do the cited winners consistently
    share? Same detection + prevalence machinery as the Tab 2 scorecard,
    minus the "QC already has it" half - there's no QC page here, so a
    "most winners share X" finding IS the recommendation ("the new page
    needs X"), not a gap against QC.

    target_genre stratifies to winners that share the KIND of page being
    built (mirrors build_scorecard's own genre stratification - "most cited
    pages have X" should mean "most pages like the one we're building have
    X"); falls back to the full comparable pool when too few genre-matched
    winners exist. None skips stratification (e.g. the earn_indirect branch,
    where the target page's genre isn't knowable).

    Returns [] below min_winners readable+comparable pages - a builder needs
    a real sample to name required features, same bar the fix side uses.
    """
    features = _load_features()
    comparable = _comparable_target_winners(winner_facts, target_genre, min_winners)
    n = len(comparable)
    if n == 0:
        return []

    present = [_page_features(f, question, features) for f in comparable]
    rows = []
    for feat in features:
        if feat["detection"] == "ratio":
            continue   # template-level metrics need a page to measure; nothing to measure yet
        if target_genre == "commercial" and feat["id"] in _INAPPLICABLE_ON_COMMERCIAL:
            continue
        weight = _effective_geo_weight(feat, target_genre)
        wp = sum(1 for p in present if p.get(feat["id"]))
        if _prevalence_label(wp, n) != "most" or weight == "low":
            continue
        rows.append({
            "id": feat["id"], "label": feat["label"], "geo_weight": weight,
            "winners_present": wp, "winners_total": n,
            "winners_pct": round(100 * wp / n),
        })
    _weight_rank = {"high": 2, "medium": 1, "low": 0}
    rows.sort(key=lambda r: (-_weight_rank[r["geo_weight"]], -r["winners_pct"]))
    return rows


# Ordered section slots per target_format (page_facts.py's winner_format()
# buckets: how_to/long_form/listicle/landing). Each slot's checklist_ids are
# tried in order against build_winner_checklist's output - the first id that
# clears the prevalence bar names the section as winner-backed; none clearing
# falls back to the slot's static `template` sentence. First-draft skeleton -
# section order reflects where each element typically appears on a real page
# of that format, not a ranking.
#
# "Comparison table"/"comparison framing" on listicle will usually render via
# its template, not the checklist: FORMAT_TO_GENRE maps listicle to
# "commercial", and _INAPPLICABLE_ON_COMMERCIAL drops comparison_table/
# comparison_structure from the checklist on commercial genre (line ~93)
# - pre-existing scorecard behavior, not a bug in this table.
#
# heading_hint: a compiled regex used to pull a REAL example heading for this
# slot from a cited winner's own page_facts.headings (see
# _match_example_heading) - keyword matching, not semantic understanding, so
# it can occasionally grab a heading that uses the right word out of context.
# Same class of tradeoff as the checklist/format templates themselves: a
# useful heuristic, not a guarantee. Shared regex objects are reused across
# slots for the same concept (e.g. "Requirements / prerequisites" and
# "Certification / pathway" both want a certification-ish heading).
#
# No trailing \b on the truncated stems (certif, licens, qualif, accredit,
# earn, employ) - they're deliberately prefixes meant to also match
# "certified"/"certification"/"earning"/"employment" etc; a closing \b would
# require the stem to be a complete word and silently miss every inflected
# form (a real, actually-occurring miss: "Becoming a Certified Dog Trainer"
# needs "certif" to match inside "Certified", where there's no boundary
# between the "f" and the "i"). The leading \b still anchors to a word start,
# so this can't match mid-word inside an unrelated token.
_HINT_DIRECT_ANSWER = re.compile(r"\b(what is|what does|overview|introduction|definition)\b", re.I)
_HINT_STEPS = re.compile(r"\b(step|steps|how to|process|path|getting started)\b", re.I)
_HINT_REQUIREMENTS = re.compile(r"\b(requirement|certif|licens|prerequisite|qualif|accredit)", re.I)
_HINT_OUTCOMES = re.compile(r"\b(salary|career|job|outcome|earn|pay|income|employ)", re.I)
_HINT_FAQ = re.compile(r"\?\s*$|^(how|what|why|can|do|does|is|are|should|where|when|which)\b", re.I)
_HINT_OVERVIEW = re.compile(r"\b(overview|guide|everything|what you need to know)\b", re.I)
_HINT_EVIDENCE = re.compile(r"\b(research|studies|data|statistics|according to)\b", re.I)
_HINT_AUTHOR = re.compile(r"\b(about the author|written by|expert|credential)\b", re.I)
_HINT_CRITERIA = re.compile(r"\b(how we (chose|ranked)|criteria|methodology|what to look for)\b", re.I)
_HINT_COMPARISON = re.compile(r"\b(compar\w+|\bvs\b|side.by.side)\b", re.I)
_HINT_PROS_CONS = re.compile(r"\b(pros|cons|advantages|disadvantages)\b", re.I)
_HINT_COST = re.compile(r"\b(cost|price|tuition|fee|how much)", re.I)
_HINT_CURRICULUM = re.compile(r"\b(curriculum|what.?s included|course content|syllabus)\b", re.I)
_HINT_PROOF = re.compile(r"\b(accredited|guarantee|rating|certified by|award)", re.I)

_FORMAT_SECTION_SKELETONS = {
    "how_to": [
        {"title": "Direct answer up front", "checklist_ids": ["direct_answer_first"],
         "heading_hint": _HINT_DIRECT_ANSWER,
         "template": "Answer the core question in the first 1-2 sentences, before any steps."},
        {"title": "Step-by-step process", "checklist_ids": [], "heading_hint": _HINT_STEPS,
         "template": "Numbered steps covering the full path, in the order someone would actually complete them."},
        {"title": "Requirements / prerequisites", "checklist_ids": ["certification_pathway"],
         "heading_hint": _HINT_REQUIREMENTS,
         "template": "Certification, licensing, or prerequisite requirements along the way."},
        {"title": "Career outcomes", "checklist_ids": ["career_outcomes"], "heading_hint": _HINT_OUTCOMES,
         "template": "What this leads to: salary range, job titles, employment prospects."},
        {"title": "FAQ / common questions", "checklist_ids": ["faq_section", "question_headings"],
         "heading_hint": _HINT_FAQ,
         "template": "A visible Q&A section answering the related questions people ask."},
    ],
    "long_form": [
        {"title": "Direct answer up front", "checklist_ids": ["direct_answer_first"],
         "heading_hint": _HINT_DIRECT_ANSWER,
         "template": "Answer the core question in the first 1-2 sentences, before any background."},
        {"title": "Comprehensive overview", "checklist_ids": ["comprehensiveness"],
         "heading_hint": _HINT_OVERVIEW,
         "template": "Fully answer the topic end-to-end - requirements, process, costs, outcomes."},
        {"title": "Certification / pathway", "checklist_ids": ["certification_pathway"],
         "heading_hint": _HINT_REQUIREMENTS,
         "template": "Certification requirements, professional bodies, and the path into the career."},
        {"title": "Career outcomes", "checklist_ids": ["career_outcomes"], "heading_hint": _HINT_OUTCOMES,
         "template": "Concrete outcomes: salary ranges, job titles, employment prospects."},
        {"title": "Evidence & primary sources", "checklist_ids": ["evidence_density", "primary_sources"],
         "heading_hint": _HINT_EVIDENCE,
         "template": "Statistics, quotations, or references to professional bodies and government data."},
        {"title": "Author / expertise byline", "checklist_ids": ["author_expertise"],
         "heading_hint": _HINT_AUTHOR,
         "template": "A named author with stated credentials or first-hand experience."},
        {"title": "FAQ / common questions", "checklist_ids": ["faq_section", "question_headings"],
         "heading_hint": _HINT_FAQ,
         "template": "A visible Q&A section answering the related questions people ask."},
    ],
    "listicle": [
        {"title": "Selection criteria intro", "checklist_ids": ["direct_answer_first"],
         "heading_hint": _HINT_CRITERIA,
         "template": "State up front what's being ranked/compared and on what basis."},
        {"title": "Comparison table", "checklist_ids": ["comparison_table", "comparison_structure"],
         "heading_hint": _HINT_COMPARISON,
         "template": "A table or side-by-side comparison of the options, not just prose."},
        {"title": "Ranked entries with pros/cons", "checklist_ids": ["pros_cons"],
         "heading_hint": _HINT_PROS_CONS,
         "template": "Each option's advantages/drawbacks laid out explicitly."},
        {"title": "Tuition / cost per option", "checklist_ids": ["tuition_pricing"], "heading_hint": _HINT_COST,
         "template": "Actual costs stated per option, not \"contact us for pricing\"."},
        {"title": "FAQ / common questions", "checklist_ids": ["faq_section", "question_headings"],
         "heading_hint": _HINT_FAQ,
         "template": "A visible Q&A section answering the related questions people ask."},
    ],
    "landing": [
        {"title": "Direct answer / value proposition", "checklist_ids": ["direct_answer_first"],
         "heading_hint": _HINT_DIRECT_ANSWER,
         "template": "State plainly what the program is and who it's for, before any pitch."},
        {"title": "Curriculum / what's included", "checklist_ids": ["comprehensiveness"],
         "heading_hint": _HINT_CURRICULUM,
         "template": "What the program actually covers, end-to-end."},
        {"title": "Tuition / cost breakdown", "checklist_ids": ["tuition_pricing"], "heading_hint": _HINT_COST,
         "template": "Actual costs stated - tuition, fees, payment plans."},
        {"title": "Career outcomes", "checklist_ids": ["career_outcomes"], "heading_hint": _HINT_OUTCOMES,
         "template": "Concrete outcomes: salary ranges, job titles, employment prospects."},
        {"title": "Justification assets (proof points)", "checklist_ids": ["justification_assets"],
         "heading_hint": _HINT_PROOF,
         "template": "Short, quotable value propositions (accreditation, guarantees, ratings)."},
        {"title": "FAQ / common questions", "checklist_ids": ["faq_section", "question_headings"],
         "heading_hint": _HINT_FAQ,
         "template": "A visible Q&A section answering the related questions people ask."},
    ],
}


_MAX_EXAMPLE_HEADING_LEN = 90  # longer strings are unlikely to be a real subheading


def _match_example_heading(slot, comparable, used):
    """
    First (winner-url, heading) pair matching this slot's heading_hint, from
    the citation-sorted `comparable` pool, not already claimed by an earlier
    slot in the same build_page_plan call (`used`) - so two sections never
    quote the same heading. None when the slot has no hint or nothing on any
    comparable winner's page matches it.
    """
    hint = slot.get("heading_hint")
    if not hint:
        return None
    for f in comparable:
        for h in (f.get("headings") or []):
            if not h or len(h) > _MAX_EXAMPLE_HEADING_LEN or (f["url"], h) in used:
                continue
            if hint.search(h):
                used.add((f["url"], h))
                return {"heading": h, "domain": f.get("domain")}
    return None


def build_page_plan(winner_facts, question, target_format, target_genre=None, min_winners=MIN_WINNERS):
    """
    Deterministic, format-templated page plan for a BUILD rec - no new LLM
    call. Reuses build_winner_checklist's own output for section content
    (matching each section slot's checklist_ids against it) and the same
    comparable-winner sample (_comparable_target_winners) for the word-count
    target, so both are drawn from the exact same vetted sample, not
    separately-filtered pools.

    Each section also gets a real example heading when one of the comparable
    winners' cached page_facts.headings matches the slot's heading_hint
    (_match_example_heading) - keyword extraction, not an LLM, so it's
    heuristic (can occasionally match a heading out of context) but free and
    deterministic. When found, it's folded INTO the section's existing
    `detail` text (quote + domain, plus the prevalence stat when the slot is
    also checklist-backed) rather than added as a separate field to render -
    a section never gets taller for having a real example, just more useful.

    None when target_format is unrecognized, or too few comparable winners
    exist (same min_winners gate as build_winner_checklist) - callers then
    fall back to the existing checklist-only content_brief.
    """
    skeleton = _FORMAT_SECTION_SKELETONS.get(target_format)
    if not skeleton:
        return None
    comparable = _comparable_target_winners(winner_facts, target_genre, min_winners)
    if not comparable:
        return None

    checklist = build_winner_checklist(winner_facts, question, target_genre=target_genre, min_winners=min_winners)
    checklist_by_id = {r["id"]: r for r in checklist}

    used_headings = set()
    sections = []
    for slot in skeleton:
        row = next((checklist_by_id[fid] for fid in slot["checklist_ids"] if fid in checklist_by_id), None)
        example = _match_example_heading(slot, comparable, used_headings)
        if row:
            base = f"{row['winners_pct']}% of cited pages have it"
            detail = f'"{example["heading"]}" ({example["domain"]}) — {base}' if example else base
            section = {"title": slot["title"], "source": "checklist", "detail": detail,
                       "geo_weight": row["geo_weight"]}
        else:
            detail = f'"{example["heading"]}" ({example["domain"]})' if example else slot["template"]
            section = {"title": slot["title"], "source": "template", "detail": detail}
        if example:
            section["example"] = example
        sections.append(section)

    # median, not mean - robust to one outlier winner (a single much-longer
    # explainer next to a cluster of shorter pages shouldn't drag the target).
    word_counts = [f["word_count"] for f in comparable
                   if isinstance(f.get("word_count"), int) and f["word_count"] > 0]
    word_count_target = ({"value": round(statistics.median(word_counts)),
                           "based_on_n_winners": len(word_counts)}
                          if len(word_counts) >= min_winners else None)

    # Format-flat: these are absolute literature targets (geo_features.json),
    # not winner-relative, so they don't vary by target_format and aren't
    # nested per-section. fix_above is intentionally not surfaced - there's
    # no existing page to be "too high" on; a build target only needs a floor
    # to aim for.
    structure_targets = [
        {"id": f["id"], "label": f["label"], "unit": f["unit"],
         "target_min": f["target_min"], "target_max": f["target_max"], "guidance": f.get("fix_below")}
        for f in _load_features() if f["detection"] == "ratio"
    ]

    return {"format": target_format, "sections": sections,
            "word_count_target": word_count_target, "structure_targets": structure_targets}


def build_scorecard(topic, qc_url, question=None, days=None, winner_facts=None):
    """
    Full Tab 2 scorecard comparing QC's page against the pages AI cites for the
    topic. `sufficient` is False when too few comparable pages could be fetched
    (caller should fall back to a generic rec rather than assert a comparison).

    `winner_facts` (plan §5.4): the question router passes THIS question's
    already-fetched winners (with citation_count attached) so the comparison is
    per-question and nothing is refetched; None falls back to the topic-level
    cited-URL path.
    """
    question = question or f"{topic}"
    features = _load_features()

    qc_facts = get_page_facts(qc_url)

    if winner_facts is None:
        cited = get_topic_cited_urls({"dimension": "topic", "value": topic}, days, limit=CANDIDATE_POOL)
        counts = {c["url"]: c["count"] for c in cited}
        winner_facts = get_pages_facts([c["url"] for c in cited])
        for f in winner_facts:
            f["citation_count"] = counts.get(f["url"], 0)
    all_winners = winner_facts
    # Dropped winners are DISCLOSED, not silently removed from the denominator:
    # prevalence over 4 readable pages means something different when 4 more
    # couldn't be fetched, and the card must say so.
    # "not_fetched" (page_facts.py's community/video short-circuit, e.g.
    # Reddit threads) never attempted a fetch - it isn't a failure, so it
    # belongs with the other not-comparable page types, not in the
    # "could not be fetched" failure list.
    unreadable = [f for f in all_winners if f.get("status") not in ("ok", "not_fetched")]
    excluded = [f for f in all_winners
                if (f.get("status") == "ok" and f.get("page_type") not in _COMPARABLE_TYPES)
                or f.get("status") == "not_fetched"]
    winner_facts = [f for f in all_winners
                    if f.get("status") == "ok" and f.get("page_type") in _COMPARABLE_TYPES]
    winner_facts.sort(key=lambda f: -(f.get("citation_count") or 0))
    winner_facts = winner_facts[:TOP_N_WINNERS]
    n = len(winner_facts)

    qc_present = _page_features(qc_facts, question, features) if qc_facts.get("status") == "ok" else {}
    winner_present = [_page_features(f, question, features) for f in winner_facts]
    qc_genre = page_genre(qc_facts) if qc_facts.get("status") == "ok" else None

    # Prevalence over the FULL comparable pool conflates genres that share
    # almost no structural features by construction - a .gov stats page
    # (informational) will never phrase "career outcomes" the way a
    # commercial course page does, so pooling them just drags every feature's
    # count toward "few" regardless of whether it actually transfers to QC's
    # page. Stratify to the subset that shares QC's own genre: "most cited
    # pages have X" should mean "most pages LIKE QC's has X", not "most pages
    # of any kind cited for this topic". Falls back to the full pool when
    # too few same-genre winners exist to trust a stratified count, or QC's
    # own genre couldn't be determined - never silently asserts a stratum
    # that isn't there.
    winner_genres = [winner_genre(f) for f in winner_facts]
    genre_matched_idx = [i for i, g in enumerate(winner_genres) if qc_genre and g == qc_genre]
    genre_stratified = qc_genre is not None and len(genre_matched_idx) >= MIN_WINNERS
    strat_idx = genre_matched_idx if genre_stratified else range(len(winner_facts))
    strat_present = [winner_present[i] for i in strat_idx]
    # Aligned with strat_present - winner_facts is sorted by citation count
    # descending (above), so strat_winners[0] is the single most-cited
    # comparable winner for this question, used by the top-competitor
    # recommend path below.
    strat_winners = [winner_facts[i] for i in strat_idx]
    n_strat = len(strat_present)

    rows = []
    metric_rows = []
    for feat in features:
        if feat["id"] in _INAPPLICABLE_ON_COMMERCIAL and qc_genre == "commercial":
            continue
        if feat["detection"] == "ratio":
            # Absolute literature target, not winner-relative (confirmed scoring
            # model) - QC's own measured value is scored against target_min/max
            # regardless of what the specific cited winners happen to measure.
            qc_value = _ratio_value(feat["id"], qc_facts, question)
            in_range = qc_value is not None and feat["target_min"] <= qc_value <= feat["target_max"]
            metric_rows.append({
                "id": feat["id"],
                "label": feat["label"],
                "geo_weight": feat["geo_weight"],
                "confidence": feat.get("confidence"),
                "unit": feat["unit"],
                "target_min": feat["target_min"],
                "target_max": feat["target_max"],
                "qc_value": qc_value,
                "in_range": in_range,
                "recommend": bool(qc_facts.get("status") == "ok" and qc_value is not None and not in_range),
                "fix_hint": _fix_hint(feat, qc_value, in_range),
            })
            continue
        wp = sum(1 for w in strat_present if w.get(feat["id"]))
        qc_has = bool(qc_present.get(feat["id"]))
        prevalence = _prevalence_label(wp, n_strat)
        weight = _effective_geo_weight(feat, qc_genre)
        # Single-competitor path: a "high" geo_weight feature the single
        # most-cited comparable winner has is real, named, actionable
        # evidence even when it isn't shared by most of the (typically thin,
        # 3-5-page) winner sample - see module docstring. Restricted to
        # "high" weight so medium/low features still require real
        # cross-winner agreement rather than one page's idiosyncrasy.
        top_has = bool(strat_present) and bool(strat_present[0].get(feat["id"]))
        top_competitor_eligible = top_has and weight == "high"
        recommend = (prevalence == "most" or top_competitor_eligible) and (not qc_has) and (weight != "low")
        evidence_basis = top_domain = top_url = None
        if recommend:
            if prevalence == "most":
                evidence_basis = "consensus"
            else:
                evidence_basis = "top_competitor"
                top_winner = strat_winners[0]
                top_domain = top_winner.get("domain")
                top_url = top_winner.get("url")
        rows.append({
            "id": feat["id"],
            "label": feat["label"],
            "geo_weight": weight,
            "winners_present": wp,
            "winners_total": n_strat,
            "winners_pct": round(100 * wp / n_strat) if n_strat else None,
            "prevalence": prevalence,
            "qc_has": qc_has,
            "recommend": recommend,
            "evidence_basis": evidence_basis,
            "top_domain": top_domain,
            "top_url": top_url,
        })

    insight, emergent_edit = (
        _emergent_pattern(qc_facts, winner_facts, question, qc_genre=qc_genre)
        if n >= MIN_WINNERS else ("", "")
    )

    suggested_edits = [f"Add {r['label'].lower()}" for r in rows if r["recommend"]]
    if emergent_edit:
        suggested_edits.insert(0, emergent_edit)

    return {
        "topic": topic,
        "question": question,
        "qc_url": qc_facts.get("final_url") or qc_url,
        "qc_title": qc_facts.get("title"),
        "qc_readable": qc_facts.get("status") == "ok",
        # source_type is added on every bucket (not just comparable winners) so
        # the frontend can render one merged "all cited pages" list - source_type()
        # is explicitly designed to classify unfetched pages too (domain-derived
        # rules still apply without page content), so this isn't a guess.
        "winners": [
            {"url": f["url"], "domain": f.get("domain"), "page_type": f.get("page_type"),
             "citation_count": f.get("citation_count") or 0, "source_type": source_type(f),
             "genre": winner_genres[i], "format": winner_format(f)}
            for i, f in enumerate(winner_facts)
        ],
        "winners_total": n,
        "winners_cited_total": len(all_winners),
        # Feature rows above are computed over the genre-matched stratum when
        # one exists (qc_genre, genre_matched_winners) - fall back to the full
        # winners_total pool otherwise, which is what genre_stratified=False
        # discloses.
        "qc_genre": qc_genre,
        "genre_stratified": genre_stratified,
        "genre_matched_winners": len(genre_matched_idx),
        "winners_unreadable": [
            {"url": f["url"], "domain": f.get("domain"), "status": f.get("status"),
             "citation_count": f.get("citation_count") or 0, "source_type": source_type(f)}
            for f in unreadable
        ],
        "winners_excluded": [
            {"url": f["url"], "domain": f.get("domain"), "page_type": f.get("page_type"),
             "status": f.get("status"),
             "citation_count": f.get("citation_count") or 0, "source_type": source_type(f)}
            for f in excluded
        ],
        "sufficient": n >= MIN_WINNERS,
        "features": rows,
        "metric_rows": metric_rows,
        "emergent_insight": insight,
        "emergent_edit": emergent_edit,
        "suggested_edits": suggested_edits,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Scorecard -> recommendation (deterministic; bypasses the generic-prose LLM)
# ─────────────────────────────────────────────────────────────────────────────

def _coverage_note(sc):
    """One sentence disclosing how much of the cited field was actually
    analyzed - 'most winners have X' over 4 readable pages means something
    different when 4 more couldn't be fetched."""
    n = sc["winners_total"]
    total = sc.get("winners_cited_total") or n
    if total == n:
        return f"Analyzed all {n} cited page(s)."
    parts = [f"Analyzed {n} of {total} cited pages"]
    unread = sc.get("winners_unreadable") or []
    if unread:
        urls = ", ".join(w["url"] for w in unread)
        parts.append(f"{len(unread)} could not be fetched: {urls}")
    excluded = sc.get("winners_excluded") or []
    if excluded:
        parts.append(f"{len(excluded)} not comparable (videos/threads/etc.)")
    capped = total - n - len(unread) - len(excluded)
    if capped > 0:
        parts.append(f"{capped} beyond the top-{n} most-cited compared here")
    return "; ".join(parts) + "."


def _frac(r):
    """'2/4 (50%)' - raw fraction so the reader judges significance themselves."""
    pct = f" ({r['winners_pct']}%)" if r.get("winners_pct") is not None else ""
    return f"{r['winners_present']}/{r['winners_total']}{pct}"


def scorecard_triage_reason(sc):
    """
    Why scorecard_to_recommendation returned None, as a precise triage slug -
    these are three DIFFERENT states and the UI must not render them all as
    "QC's page already matches the winners":
      fix_qc_page_unreadable       QC's own page couldn't be fetched/read
      fix_insufficient_winner_data too few readable winners to compare at all
      fix_true_feature_parity      evidence sufficient, QC genuinely at parity
    """
    if not sc.get("qc_readable"):
        return "fix_qc_page_unreadable"
    if (sc.get("winners_total") or 0) < MIN_READABLE_WINNERS:
        return "fix_insufficient_winner_data"
    return "fix_true_feature_parity"


def scorecard_to_recommendation(sc):
    """
    Turn a scorecard into a Tab 2 (technical) recommendation, graded by
    evidence quality. Returns None only when there is nothing actionable at
    all (QC page unreadable, too few readable winners, or true feature
    parity with no weaker signal either) - scorecard_triage_reason(sc) says
    which. Built from the scorecard - not free LLM prose - so it names the
    page and the missing sections concretely, and carries the full scorecard
    in `detail` for the frontend card.

    detail.evidence_tier:
      high  - >= MIN_WINNERS readable winners AND at least one checklist
              feature most of them share that QC lacks (the verified gap).
      named - at least one checklist gap, but every one of them is backed
              only by the single most-cited winner (evidence_basis
              "top_competitor"), not by cross-winner consensus - concrete
              and real, but single-instance evidence.
      low   - a real but weaker signal: thin-sample consensus gaps that
              never reach MIN_WINNERS, sub-threshold gaps (some-but-not-most
              readable winners have a feature QC lacks), and/or the emergent
              LLM pattern.
    detail.evidence_grade keeps checklist gaps, sub-threshold gaps and the
    emergent insight structurally separate - they have different reliability
    and the UI labels them differently.
    """
    if not sc.get("qc_readable"):
        return None

    # Metric gaps (ratio features) are scored against a fixed literature target,
    # independent of winner data, so - unlike the checklist below - they can
    # still be actionable even when too few winners were readable to compare.
    # Sorted by _METRIC_PRIORITY up front so every downstream use (narrative,
    # evidence, detail.evidence_grade) agrees on which gap leads.
    metric_gaps = sorted((r for r in sc.get("metric_rows", []) if r["recommend"]),
                          key=lambda r: _METRIC_PRIORITY.get(r["id"], 99))
    sufficient_winners = sc["winners_total"] >= MIN_READABLE_WINNERS

    rec_feats = [r for r in sc["features"] if r["recommend"]] if sufficient_winners else []
    # Sub-threshold gaps: QC lacks the feature and at least one readable
    # winner has it, but prevalence never cleared the "most" bar. Quantified
    # supplementary evidence, never asserted as a shared pattern.
    partial = ([r for r in sc["features"]
                if not r["qc_has"] and not r["recommend"]
                and r["winners_present"] > 0 and r["geo_weight"] != "low"]
               if sufficient_winners else [])
    emergent_insight = (sc.get("emergent_insight") or "").strip() if sufficient_winners else ""
    emergent_edit = (sc.get("emergent_edit") or "").strip() if sufficient_winners else ""
    has_emergent = bool(emergent_insight or emergent_edit)

    if not rec_feats and not partial and not has_emergent and not metric_gaps:
        return None   # true feature parity / insufficient winners - scorecard_triage_reason says which

    # Three-way, not binary: a card only earns "high" when a real majority of
    # a sufficient sample agrees (has_consensus_feat AND sc["sufficient"]);
    # "named" is a real, concrete gap but backed by a single named page only;
    # "low" covers everything weaker (thin-sample consensus that never
    # reached MIN_WINNERS, sub-threshold gaps, the emergent pattern alone).
    has_consensus_feat = any(r.get("evidence_basis") == "consensus" for r in rec_feats)
    has_named_feat = any(r.get("evidence_basis") == "top_competitor" for r in rec_feats)
    if has_consensus_feat and sc.get("sufficient"):
        tier = "high"
    elif has_named_feat:
        tier = "named"
    else:
        tier = "low"
    coverage = _coverage_note(sc)

    problem_parts, action_parts, evidence_parts = [], [], []
    confidence = 0.35
    priority = "low"

    if rec_feats:
        labels = ", ".join(r["label"].lower() for r in rec_feats)
        # QC's own page URL is shown in its own box on the card (TargetBox,
        # RecommendationCard.jsx) - kept out of this sentence so it stays a
        # short, scannable headline instead of a run-on with a URL in it.
        problem_parts.append(
            f"AI engines cite other pages for '{sc['question']}' instead - "
            f"missing {len(rec_feats)} feature(s) they share: {labels}."
        )
        action_parts.extend(sc["suggested_edits"][:5] or [f"Add: {labels}"])
        evidence_parts.extend(
            f"{r['label']} — the top-cited page for this question "
            f"({r.get('top_domain') or 'unknown domain'}) has it, QC does not"
            if r.get("evidence_basis") == "top_competitor"
            else f"{r['label']} — {_frac(r)} cited pages have it, QC does not"
            for r in rec_feats
        )
        confidence = {"high": 0.7, "named": 0.55}.get(tier, 0.45)
        priority = "high" if any(r["geo_weight"] == "high" for r in rec_feats) else "medium"
    elif sufficient_winners:
        problem_parts.append(
            "QC matches the analyzed winners on every checklist feature most of them share - "
            "remaining signals are weaker, below the evidence bar."
        )
        # Only a short pointer here - the partial gaps themselves are already
        # visible below (the feature-diff table falls back to showing them
        # by default when there's no verified gap), so repeating each one's
        # "Consider adding X - frac" line here would just duplicate that
        # section in flat prose instead of pointing at it.
        if emergent_edit:
            action_parts.append(f"{emergent_edit} (LLM-observed pattern - see note below)")
        if partial:
            action_parts.append(
                f"{len(partial)} weaker signal{'s' if len(partial) != 1 else ''} below the evidence "
                f"bar - see feature diff below"
            )
        evidence_parts.extend(
            f"{r['label']} — {_frac(r)} cited pages have it, QC does not (below prevalence bar)"
            for r in partial
        )
        if emergent_insight:
            evidence_parts.append(f"LLM-observed pattern (lower confidence): {emergent_insight}")
    else:
        problem_parts.append(
            f"Too few cited pages were readable ({sc['winners_total']}) to run the "
            f"winner-comparison checklist."
        )

    # Metric-gap evidence is built and joined SEPARATELY from the checklist
    # evidence above, never folded into `evidence_parts`/`coverage` - these are
    # generic, template-level properties (paragraph length, link density...)
    # scored against a fixed literature target, not verified against this
    # topic's cited winners the way a competitor-prevalence gap is. Mixing them
    # into the same sentence/evidence string would imply a technical gap has
    # the same topic-specific evidentiary weight as a competitor-verified one,
    # and would wrongly inherit `coverage`'s "N of M winners readable" caveat,
    # which describes the winner sample these metrics were never compared to.
    metric_evidence_parts = []
    if metric_gaps:
        def _fmt(r, key):
            return f"{r[key]}%" if r["unit"] == "pct" else f"{r[key]} levels"

        # Lead the narrative with exactly ONE metric - the most research-backed
        # one out of range - so the card stays decisive instead of dumping every
        # failing metric into one sentence; the rest stay fully available in
        # `metric_evidence_parts`/detail.evidence_grade.metric_gaps (and the
        # frontend's structural-metrics table) as supporting data, not competing
        # for the reader's attention as if all were equally worth acting on.
        lead, rest = metric_gaps[0], metric_gaps[1:]

        # One short sentence, always - naming every out-of-range metric here
        # (as an earlier version did) just re-produced the structural-metrics
        # table in prose. The lead is which one to act on FIRST, not the only
        # one worth acting on; the rest (with their own fix hints) are one
        # click away in that table, not duplicated here.
        problem_parts.append(
            f"Separately, independent of the winner comparison, QC's {lead['label'].lower()} measures "
            f"{_fmt(lead, 'qc_value')} against a {lead['target_min']}-{lead['target_max']}"
            f"{'%' if lead['unit'] == 'pct' else ' levels'} target" +
            (f" - {len(rest)} more also measured out of range, see below."
             if rest else " - see structural metrics below.")
        )
        # fix_hint is deliberately left out here - it already renders under this
        # metric's row in the structural-metrics table (FixDiffModule.jsx), so
        # repeating it in the checklist action would duplicate the same detail
        # twice on the card.
        lead_action = (f"Bring {lead['label'].lower()} into the {lead['target_min']}-{lead['target_max']}"
                       f"{'%' if lead['unit'] == 'pct' else ' levels'} target range")
        action_parts.append(
            lead_action +
            (f"; {len(rest)} more metric(s) out of range - see structural metrics table"
             if rest else "")
        )
        metric_evidence_parts.extend(
            f"{r['label']} — QC measures {_fmt(r, 'qc_value')}, literature target is "
            f"{r['target_min']}-{r['target_max']}{'%' if r['unit'] == 'pct' else ' levels'} "
            f"({r.get('confidence', 'medium')}-confidence research)"
            for r in metric_gaps
        )
        # Capped at 0.5, never maxed against checklist confidence/priority: a
        # metric gap is backed by literature, not by this topic's competitors,
        # so it can nudge an otherwise-unremarkable card up but never outrank
        # (or masquerade as) a genuine competitor-verified finding on its own.
        conf_score = {"high": 0.5, "medium": 0.45, "low": 0.35}
        metric_confidence = max(conf_score.get(r.get("confidence"), 0.4) for r in metric_gaps)
        confidence = max(confidence, metric_confidence)
        if priority == "low":
            priority = "medium"

    # coverage (winner-sample completeness) only qualifies the checklist half
    # of the evidence - it says nothing about the metric half, which was never
    # compared against the winner sample in the first place.
    has_checklist_evidence = bool(rec_feats or partial or has_emergent or not sufficient_winners)
    evidence = (f"{coverage} " + "; ".join(evidence_parts)).strip() if has_checklist_evidence else ""
    if metric_evidence_parts:
        metric_evidence = "Structural metrics (independent of the winner comparison): " + "; ".join(metric_evidence_parts)
        evidence = f"{evidence} | {metric_evidence}" if evidence else metric_evidence

    return {
        "problem": " ".join(problem_parts),
        "action": "; ".join(action_parts),
        "priority": priority,
        "school": school_for_url(sc["qc_url"]),
        "evidence": evidence,
        "action_type": "technical",
        "target": sc["qc_url"],
        "segment": {"dimension": "topic", "value": sc["topic"]},
        "metric_impact": "citation_rate",
        "expected_direction": 1,
        "expected_magnitude": None,
        "effort": "M",
        "confidence": confidence,
        "detail": {
            "scorecard": sc,
            "evidence_tier": tier,
            "evidence_grade": {
                "tier": tier,
                "winners_readable": sc["winners_total"],
                "winners_cited_total": sc.get("winners_cited_total") or sc["winners_total"],
                "winners_unreadable": sc.get("winners_unreadable") or [],
                "checklist_gaps": [
                    {k: r[k] for k in ("id", "label", "geo_weight",
                                       "winners_present", "winners_total", "winners_pct",
                                       "evidence_basis", "top_domain", "top_url")}
                    for r in rec_feats
                ],
                "partial_gaps": [
                    {k: r[k] for k in ("id", "label", "geo_weight",
                                       "winners_present", "winners_total", "winners_pct")}
                    for r in partial
                ],
                "metric_gaps": [
                    {k: r.get(k) for k in ("id", "label", "geo_weight", "confidence", "unit",
                                            "qc_value", "target_min", "target_max", "fix_hint")}
                    for r in metric_gaps
                ],
                "emergent": ({"insight": emergent_insight, "edit": emergent_edit}
                             if has_emergent else None),
            },
        },
    }


if __name__ == "__main__":
    import io, sys
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    topic = sys.argv[1] if len(sys.argv) > 1 else "How to Become"
    qc_url = sys.argv[2] if len(sys.argv) > 2 else "https://www.qcpetstudies.com/certification-courses/dog-grooming"
    question = sys.argv[3] if len(sys.argv) > 3 else "how to become a dog groomer"
    print(json.dumps(build_scorecard(topic, qc_url, question), indent=2, default=str))
