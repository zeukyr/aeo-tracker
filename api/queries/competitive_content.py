"""
Competitive content engine - the aggregate counterpart to the question
router's BUILD branch.

The router's BUILD branch fires when ONE losing question has no QC page
(question_router.py). This engine fires when the SAME competitive win-reason
recurs across MANY questions/topics - a cross-question pattern the
per-question router structurally cannot see (it routes one question at a
time). Same deterministic-first discipline as concern_engine.py: aggregate ->
probe QC's own content index -> one narrow LLM confirm call per candidate
page. The LLM never authors the recommendation, only answers a yes/no
"does this page cover X" question with a mandatory quote.

Renders on the existing BUILD card shell (RecommendationCard.jsx /
RecTrail.jsx) via a `detail.router`-shaped payload, so no new card type is
needed - only RecTrail.jsx gets a second stepper (patternSteps), because the
per-question dominance-vote trail (which cited pages classified into which
source-type bucket) doesn't apply to a cross-question aggregate.

Scope (v1): only win-reason types tagged action_type "content" in
win_reason_taxonomy.json are actioned here - types whose honest fix is
earning third-party proof (reviews_ratings -> citation) or that are
structural (mention_position, reputation -> not addressable by content) are
classified but never produce a rec from this engine.
"""

import json
import os
from urllib.parse import urlsplit

from openai import OpenAI

from src.logger import logger
from api.db import get_connection, _date_filter
from api.queries.page_facts import get_pages_facts, source_type
from api.queries.signal_taxonomy import classify_win_reason, load_taxonomy
from api.queries.concern_engine import qc_content_index
from api.queries.rec_shaping import (
    volume_confidence, confidence_basis_note, format_spec_sentence, checkpoint_note,
    dominance_vote, channel_for_bucket,
)

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

_MIN_COUNT = 3          # sentiment responses citing this win-reason type
_MIN_QUESTIONS = 2      # distinct questions - the whole point is cross-question
_MAX_PROBE_CANDIDATES = 4   # content-index pages checked per reason type
_MAX_RECS = 2


# ─────────────────────────────────────────────────────────────────────────────
# Aggregation: classified win_reasons rolled up across questions
# ─────────────────────────────────────────────────────────────────────────────

def win_reason_patterns(days=None, school=None):
    """
    {reason_type: {count, competitors:set, questions:{question_id: {...}},
    citation_urls:{url: count}, examples:[...]}} - every sentiment response
    where a competitor beat QC, classified win_reasons rolled up cross-question.
    Same base population as recommendation_signals.get_win_reasons, but kept
    row-level (question + citations) instead of pre-aggregated, since this
    engine needs to know WHICH questions and WHICH pages back each pattern.
    """
    date_f = _date_filter(days).replace("AND created_at", "AND s.created_at")
    query = f"""
        SELECT s.competitor_won, s.win_reasons, s.citations, s.question_id,
               q.question, q.topic, q.school
        FROM sentiment_responses s
        LEFT JOIN questions q ON q.id = s.question_id
        WHERE s.competitor_won IS NOT NULL
          AND s.competitor_won != 'QC'
          AND s.competitor_won != 'no_clear_winner'
          {date_f};
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query)
            rows = cur.fetchall()

    out = {}
    for competitor, win_reasons, citations, qid, question, topic, qschool in rows:
        if school and qschool != school:
            continue
        seen_types = set()
        for raw in (win_reasons or []):
            rtype = classify_win_reason(raw)
            if rtype == "other" or rtype in seen_types:
                continue
            seen_types.add(rtype)
            entry = out.setdefault(rtype, {
                "count": 0, "competitors": set(), "questions": {}, "citation_urls": {},
                "examples": [],
            })
            entry["count"] += 1
            entry["competitors"].add(competitor)
            entry["questions"][str(qid)] = {
                "question_id": str(qid), "question": question, "topic": topic,
            }
            if raw and len(entry["examples"]) < 3 and raw not in entry["examples"]:
                entry["examples"].append(raw)
            for url in citations or []:
                entry["citation_urls"][url] = entry["citation_urls"].get(url, 0) + 1
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Content probe: does QC already publish something covering this angle?
# ─────────────────────────────────────────────────────────────────────────────

def _coverage_candidates(probe, index, limit=_MAX_PROBE_CANDIDATES):
    """QC pages whose BODY text hits the probe keywords, ranked by hits
    (mirrors concern_engine._rebuttal_candidates)."""
    scored = []
    for facts in index:
        haystack = " ".join([
            facts.get("title") or "",
            " ".join(facts.get("headings") or []),
            facts.get("content_excerpt") or "",
        ]).lower()
        hits = sum(1 for kw in probe["keywords"] if kw.lower() in haystack)
        if hits:
            scored.append((hits, facts))
    scored.sort(key=lambda s: -s[0])
    return [f for _h, f in scored[:limit]]


def _confirm_coverage(probe, facts):
    """Semantic confirm with a mandatory quote - fails closed (None)."""
    prompt = f"""Competitors are winning head-to-head AI comparisons against QC (an online school) \
because of: {probe["question"]}

Page title: {facts.get("title")}
Page text (excerpt):
{(facts.get("content_excerpt") or "")[:3500]}

Does this QC page substantively cover this angle? Answer true only if it does, and quote the
exact sentence(s) from the text that do it.

Return JSON: {{"covers": true|false, "quote": "verbatim sentence or empty"}}"""
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=200,
            messages=[
                {"role": "system", "content": "You inspect web-page content. Respond with valid JSON only."},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
        )
        r = json.loads(resp.choices[0].message.content)
        quote = (r.get("quote") or "").strip()
        if r.get("covers") and quote:
            return quote
    except Exception as e:
        logger.warning(f"Coverage confirm failed for {facts.get('url')}: {e}")
    return None


def analyze_pattern(rtype, entry, index):
    """
    State for one win-reason type:
      out_of_scope - taxonomy says this isn't a content fix (structural, or
                      the fix is earning citations rather than publishing)
      covered       - a QC page was confirmed to cover this angle
      missing        - no QC page confirmed to cover it
    """
    spec = next(t for t in load_taxonomy("win_reason") if t["id"] == rtype)
    analysis = {
        "reason_type": rtype,
        "label": spec["label"],
        "as_question": spec.get("as_question"),
        "count": entry["count"],
        "competitors": sorted(entry["competitors"]),
        "questions": list(entry["questions"].values()),
        "examples": entry.get("examples", []),
    }
    if not spec.get("addressable") or spec.get("action_type") != "content":
        analysis["state"] = "out_of_scope"
        return analysis

    candidates = _coverage_candidates(spec["probe"], index)
    quote = None
    for facts in candidates:
        quote = _confirm_coverage(spec["probe"], facts)
        if quote:
            break
    analysis["candidates_checked"] = [c.get("final_url") or c["url"] for c in candidates]

    analysis["state"] = "covered" if quote else "missing"
    return analysis


# ─────────────────────────────────────────────────────────────────────────────
# Winners (cited pages backing the pattern) -> the BUILD card's benchmark list
# ─────────────────────────────────────────────────────────────────────────────

def _fetch_winners(citation_urls, limit=5):
    """Top cited URLs behind this pattern, fetched/classified the same way
    the question router classifies a question's cited winners."""
    top = sorted(citation_urls.items(), key=lambda kv: -kv[1])[:limit]
    counts = dict(top)
    facts = get_pages_facts([u for u, _n in top])
    for f in facts:
        f["citation_count"] = counts.get(f["url"], 0)
    return facts


def _benchmarkable(f):
    """Same exclusions as question_router._benchmarkable: unclassified/video
    pages abstain, bare homepages aren't a page to model content on."""
    if source_type(f) == "other":
        return False
    path = urlsplit(f.get("final_url") or f.get("url") or "").path
    return bool(path.strip("/"))


def _winner_summary(facts, limit=5):
    ranked = sorted(facts, key=lambda f: -(f.get("citation_count") or 0))[:limit]
    return [{"url": f["url"], "page_type": f.get("page_type"),
             "source_type": source_type(f), "citation_count": f.get("citation_count") or 0}
            for f in ranked]


# ─────────────────────────────────────────────────────────────────────────────
# Templated recommendation, rendered on the BUILD card shell
# ─────────────────────────────────────────────────────────────────────────────

def pattern_to_recommendation(analysis, winner_facts):
    if analysis["state"] != "missing":
        return None

    label = analysis["label"].lower()
    # format_spec_sentence needs a natural page heading, not the internal
    # win-reason label (see concern_engine.py's identical heading/label split).
    heading = analysis.get("as_question") or analysis["label"]
    questions = analysis["questions"]
    n_q = len(questions)
    count = analysis["count"]
    competitors = ", ".join(analysis["competitors"][:3])
    card_winners = [f for f in winner_facts if _benchmarkable(f)]
    benchmark = ", ".join(
        w["url"] for w in _winner_summary(card_winners, limit=2)
    )

    problem = (f"Across {n_q} questions, engines credit {competitors} for '{label}' "
               f"({count} head-to-head judgments) - no QC page in the indexed "
               f"content corpus was confirmed to cover this angle.")

    # Channel check: don't default to "publish" when the citations backing
    # this pattern are dominated by sources QC doesn't own (mirrors
    # concern_engine.py's dominance check and question_router's per-question vote).
    bucket, ch_share, top_fact, vote = dominance_vote(winner_facts)
    feas = channel_for_bucket(bucket, top_fact) if bucket else None
    dominant_source = "competitor"
    target = analysis["label"]
    content_brief = None  # only content-writing branches (below) fill this in
    if bucket and feas and feas["feasibility"] in ("open", "gated"):
        action = (f"Competitors aren't the only factor here - engines also lean on {bucket} "
                  f"sources QC doesn't own ({ch_share:.0%} of citations backing this pattern) - "
                  f"{feas['mechanism']}")
        if feas["feasibility"] == "gated":
            action += " (Requires application/approval - budget lead time.)"
        action_type = "community" if bucket == "ugc" else "citation"
        dominant_source = bucket
        # Reach-out cards render a TargetDossier keyed on a real URL (mirrors
        # question_router._reach_out_rec) - the topic label isn't pitchable.
        # top_fact["url"] (not final_url) matches the "url" key _winner_summary
        # puts in router_detail["winners"], so TargetDossier's winner lookup hits.
        target = top_fact.get("url") or top_fact.get("final_url") or analysis["label"]
    elif bucket == "reference":
        action_core = (f"Engines lean on reference sources QC can't pitch directly for '{label}' "
                        f"({ch_share:.0%} of citations) - publish the authoritative, citable "
                        f"content on '{label}' such sources would reference, to earn the "
                        f"citation indirectly.")
        action = f"{action_core} {format_spec_sentence(heading)}"
        action_type = "content"
        dominant_source = bucket
        content_brief = {"heading": heading, "action": action_core, "outline": None,
                          "evidence_quotes": analysis["examples"][:3]}
    else:
        # candidates_checked (kept in detail, not asserted here) are
        # keyword-hit pages the confirm step already ran and rejected -
        # crude keyword overlap isn't reliable enough evidence of relevance
        # to name a page as a "near miss" once the quote-gated check has
        # already said it doesn't cover this (see concern_engine.py).
        action_core = (f"Publish content that directly demonstrates '{label}' (specifics, not "
                        f"marketing copy) so engines can cite it the next time this comparison "
                        f"comes up.")
        action = f"{action_core} {format_spec_sentence(heading)}"
        action_type = "content"
        content_brief = {"heading": heading, "action": action_core, "outline": None,
                          "evidence_quotes": analysis["examples"][:3]}
    if benchmark:
        action += f" Benchmark: {benchmark}."

    topic = next((q["topic"] for q in questions if q.get("topic")), None)
    priority = "high" if (n_q >= 4 and count >= 6) else "medium"
    confidence = volume_confidence(count, _MIN_COUNT, floor=0.40, cap=0.75)

    router_detail = {
        "branch": "competitive_pattern",
        "reason": "recurring_win_reason_no_coverage",
        "reason_type": analysis["reason_type"],
        "reason_label": analysis["label"],
        "dominant_source": dominant_source,
        "pattern_count": count,
        "competitors": analysis["competitors"],
        "winners": _winner_summary(winner_facts),
        "source_questions": questions[:10],
        "grouped_questions": [q["question"] for q in questions],
        "confidence_basis": confidence_basis_note(count, _MIN_COUNT),
        "checkpoint": checkpoint_note(),
    }
    if bucket:
        router_detail["vote"] = vote
    if feas:
        router_detail["outreach_feasibility"] = feas
    if content_brief:
        router_detail["content_brief"] = content_brief

    return {
        "problem": problem,
        "action": action,
        "priority": priority,
        "school": None,
        "evidence": problem,
        "action_type": action_type,
        "target": target,
        "segment": {"dimension": "topic", "value": topic} if topic else {"dimension": "global", "value": "all"},
        "metric_impact": "citation_rate",
        "expected_direction": 1,
        "expected_magnitude": None,
        "effort": "L",
        "confidence": confidence,
        "detail": {"router": router_detail},
    }


def build_competitive_content_recommendations(days=None, school=None, min_count=_MIN_COUNT,
                                               min_questions=_MIN_QUESTIONS, max_recs=_MAX_RECS):
    """Deterministic competitive-content recs for the most-recurring,
    content-addressable win-reason patterns. Bounded: content index is
    cached, <= _MAX_PROBE_CANDIDATES LLM calls per in-scope type."""
    patterns = win_reason_patterns(days, school)
    ranked = sorted(patterns.items(), key=lambda kv: -kv[1]["count"])
    index = None
    out = []
    for rtype, entry in ranked:
        if len(out) >= max_recs:
            break
        if entry["count"] < min_count or len(entry["questions"]) < min_questions:
            continue
        try:
            spec = next(t for t in load_taxonomy("win_reason") if t["id"] == rtype)
            if not spec.get("addressable") or spec.get("action_type") != "content":
                continue
            if index is None:
                index = qc_content_index()
            analysis = analyze_pattern(rtype, entry, index)
            if analysis["state"] != "missing":
                continue
            # limit=20 so the dominance vote (pattern_to_recommendation) sees a
            # representative citation sample; the card's own display slicing
            # (_winner_summary/benchmark) still narrows to 5/2 separately.
            winner_facts = _fetch_winners(entry["citation_urls"], limit=20)
            rec = pattern_to_recommendation(analysis, winner_facts)
        except Exception as e:
            logger.warning(f"Competitive content engine failed for {rtype}: {e}")
            rec = None
        if rec:
            out.append(rec)
    return out


if __name__ == "__main__":
    import io, sys
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    recs = build_competitive_content_recommendations()
    print(f"{len(recs)} competitive content recs")
    for r in recs:
        d = r.pop("detail", {})
        print(json.dumps(r, indent=1, default=str))
        print("  reason_type:", d.get("router", {}).get("reason_type"),
              "| questions:", len(d.get("router", {}).get("source_questions", [])))
        print()
