import os
import re
import json
import uuid
from datetime import datetime, timedelta, timezone
from openai import OpenAI
from psycopg2.extras import Json
from dotenv import load_dotenv
from src.logger import logger
from api.queries.recommendations import (
    get_competitor_wins,
    get_qc_buried_positions,
    get_citation_gaps,
    get_recurring_concerns,
)
from api.queries.recommendation_signals import (
    get_momentum,
    get_weakest_engines,
    get_weakest_categories,
    get_weakest_schools,
    get_weakest_topics,
    get_win_reasons,
    get_top_citation_domains,
    get_competitor_profile,
    get_citation_contrast,
)
from api.queries.sentiment import get_top_positives
from api.queries.citations import get_qc_citations
from api.queries.sitemap_coverage import diagnose_coverage, diagnose_text_coverage
from api.queries.tab1_strategy import analyze_strategic_topic, strategic_evidence
from api.queries.tab2_scorecard import build_tab2_recommendations
from api.queries.page_facts import load_cache, inclusion_opportunity

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

from api.db import get_connection

_PLAYBOOK_PATH = os.path.join(os.path.dirname(__file__), "..", "knowledge", "geo_playbook.md")

ACTION_TYPES   = {"content", "technical", "citation", "outreach", "strategy"}
EFFORT_LEVELS  = {"S", "M", "L"}
METRIC_NAMES   = {
    "mention_rate", "citation_rate", "positive_sentiment_rate",
    "avg_rank", "sov", "visibility_score",
}
SEGMENT_DIMENSIONS = {"engine", "topic", "school", "category", "global"}

# Minimum gap between generate_recommendations() runs. Recommendations are a
# periodic report, not an on-demand toy - this keeps a batch's worth of work
# stable long enough to act on before the next one supersedes it.
GENERATION_COOLDOWN_DAYS = 30

# A rec counts as "active" (committed work, immune to supersession/dedup-skip)
# once it's past the untouched-suggestion stage.
ACTIVE_STATUSES = (
    "accepted", "in_progress", "implemented",
    "measuring", "validated", "failed", "inconclusive",
)


def _load_geo_playbook():
    with open(_PLAYBOOK_PATH, "r", encoding="utf-8") as f:
        return f.read()


def _normalize_recommendation(rec):
    """
    Defense-in-depth schema validation, independent of the LLM judge pass:
    coerces out-of-vocabulary or malformed fields to None rather than trusting
    the model followed the enum exactly. A rec with a bad field is still
    savable (just missing that one piece of structure), not rejected wholesale.
    """
    action_type = rec.get("action_type")
    if action_type not in ACTION_TYPES:
        action_type = None

    effort = rec.get("effort")
    if effort not in EFFORT_LEVELS:
        effort = None

    metric_impact = rec.get("metric_impact")
    if metric_impact not in METRIC_NAMES:
        metric_impact = None

    expected_direction = rec.get("expected_direction")
    if expected_direction not in (1, -1):
        expected_direction = None

    expected_magnitude = rec.get("expected_magnitude")
    try:
        expected_magnitude = float(expected_magnitude) if expected_magnitude is not None else None
    except (TypeError, ValueError):
        expected_magnitude = None

    confidence = rec.get("confidence")
    try:
        confidence = float(confidence) if confidence is not None else None
        if confidence is not None and not (0.0 <= confidence <= 1.0):
            confidence = None
    except (TypeError, ValueError):
        confidence = None

    segment = rec.get("segment")
    if not isinstance(segment, dict) or segment.get("dimension") not in SEGMENT_DIMENSIONS or not segment.get("value"):
        segment = None

    rec["action_type"]         = action_type
    rec["effort"]              = effort
    rec["metric_impact"]       = metric_impact
    rec["expected_direction"]  = expected_direction
    rec["expected_magnitude"]  = expected_magnitude
    rec["confidence"]          = confidence
    rec["segment"]             = segment
    return rec


def _apply_coverage_diagnosis(rec):
    """
    Deterministic create-vs-fix branch: for topic-scoped page recs, QC's own
    sitemap decides the action_type - missing page -> "content" (create it),
    page exists but engines skip it -> "technical" (fix the existing URL) -
    so a missing-page rec is never phrased as "restructure your page" and
    vice versa, regardless of what the model chose. Citation/outreach recs
    are left alone; so is anything without a sitemap verdict.
    """
    segment = rec.get("segment") or {}
    if segment.get("dimension") != "topic" or rec.get("action_type") not in ("content", "technical"):
        return rec

    # Judge the rec's SPECIFIC target, not the bucket label - a topic like
    # "How to Become" holds both covered intents (dog grooming) and uncovered
    # ones (event decorator). The target is the intent the model chose.
    probe = rec.get("target") or segment.get("value") or ""
    coverage = diagnose_text_coverage(probe, rec.get("school"))
    if coverage["verdict"] == "missing_page":
        rec["action_type"] = "content"
    elif coverage["verdict"] == "have_page":
        rec["action_type"] = "technical"
        if coverage.get("qc_url") and not rec.get("target"):
            rec["target"] = coverage["qc_url"]
    return rec


def _work_stream(action_type):
    """
    Which dashboard tab a rec belongs to (docs/ai/recommendation-two-tab-plan.md):
      on_page   - "Improve Existing Pages": fix a QC page that exists but engines
                  skip. action_type 'technical' is set deterministically by
                  _apply_coverage_diagnosis when the sitemap shows the page exists.
      strategic - "Strategic Growth": build new owned content or earn external
                  presence (content / citation / outreach, or unclassified).
    """
    return "on_page" if action_type == "technical" else "strategic"


def _segment_key(rec):
    """(dimension, value, metric_impact) - identifies 'the same underlying problem'
    for dedup against active recs, independent of exact wording."""
    segment = rec.get("segment") or {}
    return (segment.get("dimension"), segment.get("value"), rec.get("metric_impact"))


def save_recommendations(recommendations):
    """
    Appends a new batch. Never deletes anything - this is the core of the
    non-destructive lifecycle:
      1. Any rec already committed to (status in ACTIVE_STATUSES) is left
         untouched, and new candidates covering the same segment+metric are
         skipped so in-progress work doesn't get a duplicate "new" suggestion.
      2. All previously `proposed` (untouched) recs are archived to
         `superseded` - kept for history, just no longer shown as live
         suggestions. A rec becomes immune to this the moment it's Accepted
         or marked Implemented, since it's no longer `proposed`.
      3. Surviving candidates are inserted as `proposed`, tagged with one
         fresh batch_id shared across the whole call.
    """
    batch_id = str(uuid.uuid4())
    inserted, skipped = 0, 0

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT segment, metric_impact FROM recommendations WHERE status IN %s",
                (ACTIVE_STATUSES,)
            )
            active_keys = {(r[0].get("dimension") if r[0] else None,
                             r[0].get("value") if r[0] else None,
                             r[1]) for r in cur.fetchall()}

            cur.execute("UPDATE recommendations SET status = 'superseded' WHERE status = 'proposed'")

            for rec in recommendations:
                key = _segment_key(rec)
                if key != (None, None, None) and key in active_keys:
                    skipped += 1
                    logger.info(f"Skipping duplicate recommendation for active segment {key}: {rec.get('problem', '')[:80]}")
                    continue

                cur.execute("""
                    INSERT INTO recommendations (
                        problem, action, priority, school, evidence,
                        action_type, target, segment, metric_impact,
                        expected_direction, expected_magnitude, effort, confidence,
                        batch_id, detail
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    rec["problem"],
                    rec["action"],
                    rec["priority"],
                    rec.get("school"),
                    rec.get("evidence"),
                    rec.get("action_type"),
                    rec.get("target"),
                    Json(rec["segment"]) if rec.get("segment") is not None else None,
                    rec.get("metric_impact"),
                    rec.get("expected_direction"),
                    rec.get("expected_magnitude"),
                    rec.get("effort"),
                    rec.get("confidence"),
                    batch_id,
                    Json(rec["detail"]) if rec.get("detail") is not None else None,
                ))
                inserted += 1
        conn.commit()

    return {"batch_id": batch_id, "inserted": inserted, "skipped": skipped}


def get_generation_status(cooldown_days=GENERATION_COOLDOWN_DAYS):
    """
    Whether a new batch may be generated right now, gated by a cooldown since
    the last batch - keeps generation to a periodic-report cadence instead of
    an on-demand action that can be spammed.
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT MAX(generated_at) FROM recommendations")
            last_generated_at = cur.fetchone()[0]

    if last_generated_at is None:
        return {"last_generated_at": None, "next_available_at": None, "can_generate": True}

    next_available_at = last_generated_at + timedelta(days=cooldown_days)
    return {
        "last_generated_at": last_generated_at.isoformat(),
        "next_available_at": next_available_at.isoformat(),
        "can_generate": datetime.now(timezone.utc) >= next_available_at,
    }


def update_recommendation_status(rec_id, status, implemented_at=None):
    with get_connection() as conn:
        with conn.cursor() as cur:
            if implemented_at is not None:
                cur.execute(
                    "UPDATE recommendations SET status = %s, implemented_at = %s WHERE id = %s",
                    (status, implemented_at, rec_id)
                )
            else:
                cur.execute(
                    "UPDATE recommendations SET status = %s WHERE id = %s",
                    (status, rec_id)
                )
        conn.commit()

def get_saved_recommendations(include_superseded=False):
    where = "" if include_superseded else "WHERE status != 'superseded'"
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT id, generated_at, problem, action, priority, school, evidence, status,
                       action_type, target, segment, metric_impact,
                       expected_direction, expected_magnitude, effort, confidence,
                       implemented_at, measurement_window_days, batch_id, detail
                FROM recommendations
                {where}
                ORDER BY generated_at DESC, priority ASC;
            """)
            rows = cur.fetchall()
    return [
        {
            "id": str(r[0]),
            "generated_at": str(r[1]),
            "problem": r[2],
            "action": r[3],
            "priority": r[4],
            "school": r[5],
            "evidence": r[6],
            "status": r[7],
            "action_type": r[8],
            "target": r[9],
            "segment": r[10],
            "metric_impact": r[11],
            "expected_direction": r[12],
            "expected_magnitude": float(r[13]) if r[13] is not None else None,
            "effort": r[14],
            "confidence": float(r[15]) if r[15] is not None else None,
            "implemented_at": str(r[16]) if r[16] is not None else None,
            "measurement_window_days": r[17],
            "batch_id": str(r[18]) if r[18] is not None else None,
            "detail": r[19],
            "work_stream": _work_stream(r[8]),
        }
        for r in rows
    ]

def build_evidence(days=None):
    """
    Assembles the full evidence bundle for the recommendation LLM: momentum
    (trends), weakest segments (engine/category/school/topic), competitive
    intel (losses, buried positions, win reasons, competitor profiles,
    concerns), and content leverage (positives, working QC citations,
    citation-worthy domains).

    Each section is capped to keep token usage bounded.
    """
    momentum          = get_momentum(days)
    weakest_engines    = get_weakest_engines(days, limit=10)
    weakest_categories = get_weakest_categories(days, limit=10)
    weakest_schools    = get_weakest_schools(days, limit=10)
    weakest_topics     = get_weakest_topics(days, limit=10)

    competitor_wins   = get_competitor_wins(days)
    buried_positions  = get_qc_buried_positions(days)
    win_reasons       = get_win_reasons(days, limit=15)
    concerns          = get_recurring_concerns(days)

    positives         = get_top_positives(days)
    qc_citations      = get_qc_citations(days)
    citation_gaps     = get_citation_gaps(days)
    citation_domains  = get_top_citation_domains(days, limit=15)

    # Profile the top 2 competitors from momentum so the model can see
    # *why*/*where* the leading rival wins, not just that they win.
    top_competitor_names = [c["name"] for c in momentum.get("top_competitors", [])[:2]]
    competitor_profiles = [get_competitor_profile(name, days, limit=8) for name in top_competitor_names]

    # For the weakest citation segments, pre-compute the exact QC-vs-rival
    # citation contrast (which domains, how many times) so the model can
    # quote real numbers in `evidence` instead of "competitors are higher".
    lead_competitor = top_competitor_names[0] if top_competitor_names else None
    weak_segments = [
        {"dimension": "topic", "value": t["topic"]}
        for t in weakest_topics
        if t.get("kind") == "mention" and (t.get("sample_n") or 0) >= 5
    ][:2]
    citation_contrast = []
    strategic_topics = []
    for seg in weak_segments:
        contrast = get_citation_contrast(seg, lead_competitor, days)
        # Coverage is evaluated per underlying question (real intent), not the
        # bucket label: `covered` intents have a QC page (fix it -> Tab 2),
        # `uncovered` intents have none (build it -> Tab 1). A bucket like
        # "How to Become" is typically `partial` - both at once.
        coverage = diagnose_coverage(seg)
        contrast["coverage"] = coverage
        citation_contrast.append(contrast)

        # When the topic has any uncovered intent (Tab 1 / Strategic Growth),
        # classify the pages AI cites instead and derive page-type-templated
        # actions + a build-vs-earn verdict. `coverage` rides along so the model
        # targets the specific uncovered intents, not the bucket label.
        if coverage.get("uncovered"):
            strat = analyze_strategic_topic(seg, days)
            strat["coverage"] = coverage
            strategic_topics.append(strat)

    return f"""
## MOMENTUM (current value + period-over-period change in headline KPIs)
{json.dumps(momentum, indent=2, default=str)}

## WEAKEST SEGMENTS (lower rate/score = worse; prioritize fixing these)
Engines:
{json.dumps(weakest_engines, indent=2, default=str)}

Categories (course/general/credibility/competition):
{json.dumps(weakest_categories, indent=2, default=str)}

Schools:
{json.dumps(weakest_schools, indent=2, default=str)}

Topics:
{json.dumps(weakest_topics, indent=2, default=str)}

## COMPETITIVE LOSSES
Questions where competitors appear and QC is invisible (top patterns):
{json.dumps(competitor_wins[:20], indent=2, default=str)}

Questions where QC appears but is buried behind competitors:
{json.dumps(buried_positions[:15], indent=2, default=str)}

Reasons competitors win head-to-head (from win_reasons):
{json.dumps(win_reasons[:15], indent=2, default=str)}

Profiles of the top competitors (domains that back their visibility, any recorded win reasons):
{json.dumps(competitor_profiles, indent=2, default=str)}

## RECURRING CONCERNS RAISED ABOUT QC
{json.dumps(concerns[:15], indent=2, default=str)}

## WHAT'S WORKING (reinforce, don't disrupt these)
Positives raised about QC in sentiment-focused responses:
{json.dumps(positives[:10], indent=2, default=str)}

QC pages that already earn citations:
{json.dumps(qc_citations[:10], indent=2, default=str)}

## CITATION GAPS (authority sources to pursue)
Topics where external sites are cited instead of QC (3+ times):
{json.dumps(citation_gaps[:20], indent=2, default=str)}

Top cited domains overall (QC owned vs external):
{json.dumps(citation_domains, indent=2, default=str)}

## CITATION CONTRAST (per segment)
For each of the weakest citation segments: exactly which domains engines cite when QC is
mentioned there (QC-owned vs third-party), which domains they cite when the leading
competitor appears, and the gap list (domains vouching for the rival but never for QC).
Quote these domains and counts verbatim in `evidence`. Each entry also carries a
per-intent `coverage` read from QC's own sitemaps, evaluated against the ACTUAL questions
in the segment (not the bucket label, which is often generic like "How to Become"):
`coverage.covered` lists intents where a QC page already exists (`qc_url`) but engines skip
it - recommend fixing that specific URL (schema, direct-answer structure, third-party links
- action_type "technical"); `coverage.uncovered` lists intents with no QC page - recommend
creating one (action_type "content"). Always target the SPECIFIC intent text (e.g. "become
a dog behavior specialist"), never the bucket label. Never recommend creating a page for a
covered intent, or restructuring one for an uncovered intent:
{json.dumps(citation_contrast, indent=2, default=str)}

## STRATEGIC GROWTH ANALYSIS (Tab 1 — topics where QC has no page)
For each such topic, the pages AI cites instead have been fetched and classified. Base the
recommendation on THIS, not on guesswork. Fields:
- `gap` = "build": rivals won with their own pages → create an equivalent QC page (action_type
  "content"). "earn": impartial third parties (roundups/associations/guides) dominate → an owned
  "best courses" page won't win the neutral slot; either earn placement or build EDUCATIONAL
  (not sales) content (action_type "outreach"/"citation"/"content"). Follow `gap` — don't tell
  QC to build a self-serving comparison page.
- `specific_opportunities`: roundups/directories VERIFIED to list named competitors and NOT QC.
  ONLY here may you recommend "seek inclusion" / "submit listing", and you MUST use the given
  `url` as target and cite its `lists_competitors`. If this list is empty, do NOT invent an
  inclusion opportunity.
- `authority_patterns`: associations/government/guides. Action is "benchmark & align content" —
  NEVER "contact"/"pitch" these; they list no providers. Use as the spec for the new page.
- `ecosystem`: the aggregate mix (community/impartial/commercial share). Drives one broad-strategy
  rec (action_type "strategy") when a share is "most" — e.g. community-heavy → authentic presence;
  guides over sales pages → invest in educational content. Do not attach it to a single URL.
- `coverage.uncovered`: the specific intents in this topic QC has NO page for. A build ("content")
  rec must target one of these exact intents (e.g. "become an event decorator"), never the bucket
  label. `coverage.covered` intents already have a page — those belong in Tab 2 (fix), not here.
Never assert a page's contents beyond the classification/`lists_competitors` shown here.
{json.dumps(strategic_topics, indent=2, default=str)}
"""


# ─────────────────────────────────────────────────────────────────────────────
# Deterministic fabrication guard - runs BEFORE the LLM judge.
# In testing the LLM judge passed all three planted fabrications ("APDT lists
# Penn Foster", etc.) - an LLM can't be trusted to police an LLM's fabrications.
# These regex checks hard-drop the exact two claim shapes that caused the
# original bug, verifying the only page-contents claim we allow against
# page_facts (a real roundup/directory that actually lists providers).
# ─────────────────────────────────────────────────────────────────────────────

# A page-contents claim: a page/domain SUBJECT immediately followed (within a few
# words) by a listing verb - "APDT's page lists Penn Foster", "the eventbrite.com
# comparison ranks Coursera". The adjacency requirement is what keeps an honest
# "QC ranks below competitors" (subject is QC, not a page) from tripping it, even
# when the text mentions "comparison articles" and a domain elsewhere.
_PAGE_CONTENTS_CLAIM = re.compile(
    r"(?P<subj>[a-z0-9][a-z0-9-]*\.(?:com|org|edu|net|gov|io|co|us)|"
    r"\b(?:page|roundup|article|comparison|listicle|directory|directories|guide|resource)\b)"
    r"(?:['’]s)?\s+(?:\w+\s+){0,3}?"
    r"(?:lists?|listed|names?|named|mentions?|ranks?|ranked|omits?|omitting|excludes?|excluding)\b",
    re.I)
_COMPARATIVE = re.compile(
    r"\b(more|higher|greater|better|ahead|outrank\w*|dominat\w*|outperform\w*)\b", re.I)
_COMPETITOR_WORD = re.compile(r"\b(competitors?|rivals?)\b", re.I)
_HAS_NUMBER = re.compile(r"\d")
_DOMAIN_RE = re.compile(r"\b([a-z0-9][a-z0-9-]*\.(?:com|org|edu|net|gov|io|co|us))\b", re.I)
_QC_TOKENS = ("qccareerschool", "qcpetstudies", "qceventplanning", "qcdesignschool", "qcmakeupacademy")


def _domain_is_verified_lister(domain):
    """True only if page_facts has a cached page on this domain that is a
    verified roundup/directory actually listing providers (inclusion_opportunity)."""
    cache = load_cache()
    for url, facts in cache.get("pages", {}).items():
        if domain in url.lower() and inclusion_opportunity(facts):
            return True
    return False


def _fabrication_guard(rec):
    """
    (keep, reason). Deterministically rejects the two claim shapes the LLM
    judge misses:
      1. a page-contents claim ("X lists/ranks Penn Foster") about a specific
         third-party page that page_facts has NOT verified as a roundup/directory
         actually listing providers;
      2. a comparative claim about competitors with no supporting number
         (the vague "competitors are cited more" that started all this).
    """
    text = " ".join(str(rec.get(k) or "") for k in ("problem", "evidence", "action"))
    if _COMPARATIVE.search(text) and _COMPETITOR_WORD.search(text) and not _HAS_NUMBER.search(text):
        return False, "comparative claim about competitors with no supporting count"

    m = _PAGE_CONTENTS_CLAIM.search(text)
    if m:
        dom = (_DOMAIN_RE.search(m.group("subj"))
               or _DOMAIN_RE.search(str(rec.get("target") or ""))
               or _DOMAIN_RE.search(text))
        if dom:
            d = dom.group(1).lower()
            # QC's own pages are verified via a different mechanism (Phase 4); the
            # guard polices claims about THIRD-PARTY pages.
            if not any(tok in d for tok in _QC_TOKENS) and not _domain_is_verified_lister(d):
                return False, f"asserts {d} lists/ranks providers, but it is not a verified roundup/directory"
    return True, ""


def critique_recommendations(recommendations, evidence):
    """
    Quality gate. First a deterministic fabrication guard (page-contents claims
    must trace to page_facts; no numberless comparatives), then a cheap LLM pass
    scoring specificity / evidence-grounding / GEO-soundness / measurability.
    The guard is the hard floor - the LLM pass is unreliable at catching
    fabrication, so it only trims for vagueness/soundness on top.

    Fails open on the LLM pass - if the judge call errors or a rec is missing
    from its response, that rec is kept. The guard never fails open.
    """
    if not recommendations:
        return recommendations

    guarded = []
    for rec in recommendations:
        keep, reason = _fabrication_guard(rec)
        if keep:
            guarded.append(rec)
        else:
            logger.info(f"Fabrication guard dropped ({rec.get('problem', '')[:70]}): {reason}")
    recommendations = guarded
    if not recommendations:
        return recommendations

    prompt = f"""You are a strict QA reviewer for AI-visibility recommendations. Review each
recommendation below against the evidence it was generated from.

EVIDENCE:
{evidence}

RECOMMENDATIONS TO REVIEW:
{json.dumps(recommendations, indent=2, default=str)}

For each recommendation (by its index in the list above, 0-based), score 1-5 on:
- specificity: does it cite an exact question/competitor/segment from the evidence, not a vague claim?
- evidence_grounding: is every factual claim in "problem" and "evidence" actually present in the
  evidence above (not invented)? Score 2 or lower if the evidence makes a comparative claim
  (e.g. "competitors are cited more") without quoting the specific domains/counts/rates that
  support it — the CITATION CONTRAST section provides these, so vagueness there is a failure.
  A claim about a third-party page's contents (who it lists/ranks/mentions, its page type) is
  ONLY allowed when it matches the STRATEGIC GROWTH ANALYSIS for that URL — its `page_type` and
  `lists_competitors`. Score 2 or lower if the rec asserts page contents NOT backed there (e.g.
  "this roundup lists Penn Foster" when that URL isn't a specific_opportunity naming Penn Foster),
  or recommends "seek inclusion"/"contact" a page that is an authority_pattern (association/guide),
  or claims a page lists QC's rivals when no specific_opportunity says so.
- geo_soundness: is "action" a real generative-engine-optimization tactic (third-party citations,
  listicles, structured Q&A, community presence, primary-source authority - not generic SEO advice
  like "improve keywords" or "write more blog posts")?
- measurability: does it name a real metric_impact and expected_direction that could be checked later?

Return JSON: {{
    "scores": [
        {{"index": 0, "specificity": 1-5, "evidence_grounding": 1-5, "geo_soundness": 1-5,
          "measurability": 1-5, "verdict": "keep"|"drop", "reason": "one sentence"}}
    ]
}}

Only mark "drop" if evidence_grounding <= 2 (fabricated/unsupported) or specificity <= 2 (too vague
to act on). Do not drop for style or phrasing."""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=1500,
            messages=[
                {
                    "role": "system",
                    "content": "You are a strict but fair QA reviewer. Respond with valid JSON only. No markdown, no preamble.",
                },
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
        )
        result = json.loads(response.choices[0].message.content)
        scores_by_index = {s["index"]: s for s in result["scores"]}
    except Exception as e:
        logger.error(f"Recommendation judge pass failed, keeping all candidates: {e}")
        return recommendations

    survivors = []
    for i, rec in enumerate(recommendations):
        score = scores_by_index.get(i)
        if score is None:
            survivors.append(rec)
            continue
        if score.get("verdict") == "drop":
            logger.info(f"Judge dropped recommendation {i} ({rec.get('problem', '')[:80]}): {score.get('reason')}")
            continue
        survivors.append(rec)

    return survivors


def generate_recommendations(days=None):
    evidence = build_evidence(days)
    playbook = _load_geo_playbook()

    prompt = f"""You are an AI visibility strategist analyzing data for QC Career School,
an online school with faculties in pet care (QC Pet Studies), event planning (QC Event Planning),
design, makeup, and wellness.

Use this GEO (Generative Engine Optimization) playbook as your reference for what actions
actually move AI-visibility metrics. Map each recommendation's action onto one of these
tactics rather than inventing generic SEO/marketing advice:

{playbook}

Based on this data:

{evidence}

Generate 5-8 specific, actionable recommendations. For each one:
- State the specific problem, citing the exact question, competitor, segment, or concern from the data above
- evidence: quote the specific numbers behind the problem. When the CITATION CONTRAST section
  covers the recommendation's segment, name the exact domains and citation counts on both sides
  (e.g. "engines cite eventbrite.com (5x) and coursera.org (4x) alongside Coursera; QC earns only
  2 citations here, both from qceventplanning.com (owned) — zero third-party"). Never write a
  comparative claim like "competitors' citations are higher" without the domains and numbers.
- NEVER assert what a third-party page contains — who it lists, ranks, mentions, or links to.
  You have citation counts only; none of those pages have been read. Wrong: "this roundup lists
  Penn Foster but not QC", "APDT's directory omits QC". Right: "engines cite apdt.com 9x for
  this query while QC earns zero citations". For outreach/citation actions, phrase the action
  as earning coverage/citations on the sources engines already cite — not as "request inclusion
  in their list", since you don't know the page is a list.
- Recommend a specific, concrete action QC could take, drawn from the GEO playbook tactics above
- Specify which school it applies to (QC Pet Studies, QC Event Planning, or both)
- action_type: one of "content" (build a new owned page), "technical" (fix an existing QC page),
  "citation" (submit a listing / earn a citation), "outreach" (seek inclusion where rivals are
  listed), "strategy" (a broad ecosystem-level shift not tied to one URL). For a topic covered by
  the STRATEGIC GROWTH ANALYSIS, the action_type and the action itself must follow that section's
  `gap`, `specific_opportunities`, `authority_patterns`, and `ecosystem` — do not invent an action
  the classification doesn't support.
- target: the specific page, topic, competitor, or domain the action addresses
- segment: {{"dimension": "engine|topic|school|category|global", "value": "..."}} - the segment this
  recommendation is scoped to (use the exact engine/topic/school/category name from the evidence)
- metric_impact: the one metric this should move - one of "mention_rate", "citation_rate",
  "positive_sentiment_rate", "avg_rank", "sov", "visibility_score"
- expected_direction: 1 if the metric should increase, -1 if it should decrease (avg_rank is the
  only metric where lower is better)
- expected_magnitude: a rough expected change in the metric's own units (percentage points for
  rates, rank positions for avg_rank), or null if you can't estimate one
- effort: "S", "M", or "L" or null if you can't estimate one
- confidence: your own confidence 0.0-1.0 that this recommendation is correct and will work

Prioritize recommendations using this rubric, in order:
1. How often the underlying pattern repeats in the data (frequency)
2. Whether the related MOMENTUM metric is declining (a negative diff means this is actively getting
   worse, not just historically weak - weight these higher)
3. Whether the problem shows up in a WEAKEST SEGMENT AND in COMPETITIVE LOSSES at the same time
   (compounding evidence beats a single data point)
Assign priority (high/medium/low) based on this rubric, not on how the recommendation "feels."

Only make claims that are directly supported by the data provided. Do not invent patterns that aren't there.

Return as JSON: {{
    "recommendations": [
        {{
            "problem": "...",
            "action": "...",
            "priority": "high|medium|low",
            "school": "...",
            "evidence": "...",
            "action_type": "content|technical|citation|outreach|strategy",
            "target": "...",
            "segment": {{"dimension": "...", "value": "..."}},
            "metric_impact": "...",
            "expected_direction": 1,
            "expected_magnitude": 0.0,
            "effort": "S|M|L",
            "confidence": 0.0
        }}
    ]
}}"""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        max_tokens=3000,
        messages=[
            {
                "role": "system",
                "content": "You are a data-driven strategy consultant. Always respond with valid JSON only. No markdown, no preamble. Never fabricate data not present in the input."
            },
            {"role": "user", "content": prompt}
        ],
        response_format={"type": "json_object"}
    )

    result = json.loads(response.choices[0].message.content)
    recommendations = [_normalize_recommendation(r) for r in result["recommendations"]]
    recommendations = [_apply_coverage_diagnosis(r) for r in recommendations]
    recommendations = critique_recommendations(recommendations, evidence)

    # Tab 2 recs are built deterministically from the scorecard (page + cited-page
    # comparison + section edits), not from LLM prose - so they name the page and
    # the missing sections concretely. They replace any generic LLM `technical`
    # rec for the same topic.
    scorecard_recs = build_tab2_recommendations(days)
    scored_topics = {(r["segment"]["dimension"], r["segment"]["value"]) for r in scorecard_recs}

    def _is_superseded_technical(r):
        seg = r.get("segment") or {}
        return r.get("action_type") == "technical" and (seg.get("dimension"), seg.get("value")) in scored_topics

    recommendations = [r for r in recommendations if not _is_superseded_technical(r)]
    recommendations = recommendations + scorecard_recs

    # Attach truthful citation evidence (what AI cites for the topic + QC's count)
    # to strategic recs so the Tab 1 card can show it. Tab 2 recs already carry a
    # scorecard in `detail`; leave those untouched.
    for rec in recommendations:
        if rec.get("detail") or rec.get("action_type") == "technical":
            continue
        seg = rec.get("segment") or {}
        try:
            ev = strategic_evidence(seg, school=rec.get("school"))
            if ev:
                rec["detail"] = {"evidence": ev}
        except Exception as e:
            logger.warning(f"strategic_evidence failed for {seg}: {e}")
    return recommendations
