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
recommended when it is present in MOST cited pages, QC lacks it, and its
geo_weight is not "low".

The rec is EVIDENCE-GRADED, not binary: checklist gaps that clear the bar
over a sufficient winner sample are tier "high"; thin samples, sub-threshold
gaps and the emergent LLM pattern are tier "low" (still surfaced, clearly
labelled). None is reserved for the three genuinely empty states named by
scorecard_triage_reason. Unreadable cited winners are disclosed on the card,
never silently dropped from the denominator.
"""

import os
import json

from openai import OpenAI

from src.logger import logger
from api.queries.cited_urls import get_topic_cited_urls
from api.queries.page_facts import (
    get_pages_facts, get_page_facts, page_genre, school_for_url, query_term_coverage,
)

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

_FEATURES_PATH = os.path.join(os.path.dirname(__file__), "..", "knowledge", "geo_features.json")

MIN_WINNERS = 3          # below this the comparison isn't trustworthy (high tier)
MIN_READABLE_WINNERS = 2 # below this there is no comparison at all - insufficient data
TOP_N_WINNERS = 5        # cited pages to compare against

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
# most cited winners (editorial guides) happen to have one.
_INAPPLICABLE_ON_COMMERCIAL = {"author_expertise"}


def _load_features():
    with open(_FEATURES_PATH, "r", encoding="utf-8") as f:
        return json.load(f)["features"]


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

def _emergent_pattern(qc_facts, winner_facts, question):
    """
    One LLM call: what content/ordering pattern do the cited pages share that
    QC's page lacks? Grounded in the fetched outlines; labelled lower-confidence.
    """
    def outline(f):
        return {"title": f.get("title"), "headings": (f.get("headings") or [])[:18]}

    prompt = f"""Topic question: "{question}"

QC's page outline:
{json.dumps(outline(qc_facts), indent=1)}

Outlines of the pages AI engines cite for this topic:
{json.dumps([outline(f) for f in winner_facts], indent=1)}

What content or ordering pattern do the cited pages consistently share that QC's page does
NOT? Focus on information architecture (what they cover and in what order), not styling. Be
specific and only claim patterns visible across most cited outlines. If there is no clear
shared pattern QC lacks, say so.

Return JSON: {{"insight": "one or two sentences, or empty if none", "edit": "one concrete section-level change for QC, or empty"}}"""
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
        cited = get_topic_cited_urls({"dimension": "topic", "value": topic}, days, limit=TOP_N_WINNERS + 4)
        counts = {c["url"]: c["count"] for c in cited}
        winner_facts = get_pages_facts([c["url"] for c in cited])
        for f in winner_facts:
            f["citation_count"] = counts.get(f["url"], 0)
    all_winners = winner_facts
    # Dropped winners are DISCLOSED, not silently removed from the denominator:
    # prevalence over 4 readable pages means something different when 4 more
    # couldn't be fetched, and the card must say so.
    unreadable = [f for f in all_winners if f.get("status") != "ok"]
    excluded = [f for f in all_winners
                if f.get("status") == "ok" and f.get("page_type") not in _COMPARABLE_TYPES]
    winner_facts = [f for f in all_winners
                    if f.get("status") == "ok" and f.get("page_type") in _COMPARABLE_TYPES]
    winner_facts.sort(key=lambda f: -(f.get("citation_count") or 0))
    winner_facts = winner_facts[:TOP_N_WINNERS]
    n = len(winner_facts)

    qc_present = _page_features(qc_facts, question, features) if qc_facts.get("status") == "ok" else {}
    winner_present = [_page_features(f, question, features) for f in winner_facts]
    qc_genre = page_genre(qc_facts) if qc_facts.get("status") == "ok" else None

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
            })
            continue
        wp = sum(1 for w in winner_present if w.get(feat["id"]))
        qc_has = bool(qc_present.get(feat["id"]))
        prevalence = _prevalence_label(wp, n)
        recommend = (prevalence == "most") and (not qc_has) and (feat["geo_weight"] != "low")
        rows.append({
            "id": feat["id"],
            "label": feat["label"],
            "geo_weight": feat["geo_weight"],
            "winners_present": wp,
            "winners_total": n,
            "winners_pct": round(100 * wp / n) if n else None,
            "prevalence": prevalence,
            "qc_has": qc_has,
            "recommend": recommend,
        })

    insight, emergent_edit = _emergent_pattern(qc_facts, winner_facts, question) if n >= MIN_WINNERS else ("", "")

    suggested_edits = [f"Add {r['label'].lower()}" for r in rows if r["recommend"]]
    if emergent_edit:
        suggested_edits.insert(0, emergent_edit)

    return {
        "topic": topic,
        "question": question,
        "qc_url": qc_facts.get("final_url") or qc_url,
        "qc_title": qc_facts.get("title"),
        "qc_readable": qc_facts.get("status") == "ok",
        "winners": [
            {"url": f["url"], "domain": f.get("domain"), "page_type": f.get("page_type"),
             "citation_count": f.get("citation_count") or 0}
            for f in winner_facts
        ],
        "winners_total": n,
        "winners_cited_total": len(all_winners),
        "winners_unreadable": [
            {"url": f["url"], "domain": f.get("domain"), "status": f.get("status"),
             "citation_count": f.get("citation_count") or 0}
            for f in unreadable
        ],
        "winners_excluded": [
            {"url": f["url"], "domain": f.get("domain"), "page_type": f.get("page_type"),
             "citation_count": f.get("citation_count") or 0}
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
      high - >= MIN_WINNERS readable winners AND at least one checklist
             feature most of them share that QC lacks (the verified gap).
      low  - a real but weaker signal: checklist gaps over a thin winner
             sample, sub-threshold gaps (some-but-not-most readable winners
             have a feature QC lacks), and/or the emergent LLM pattern.
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

    tier = "high" if (rec_feats and sc.get("sufficient")) else "low"
    coverage = _coverage_note(sc)

    problem_parts, action_parts, evidence_parts = [], [], []
    confidence = 0.35
    priority = "low"

    if rec_feats:
        labels = ", ".join(r["label"].lower() for r in rec_feats)
        problem_parts.append(
            f"QC has a page for '{sc['question']}' ({sc['qc_url']}) but AI engines cite other pages "
            f"for this question. Across {sc['winners_total']} analyzed cited pages it is missing "
            f"{len(rec_feats)} feature(s) they share: {labels}."
        )
        action_parts.extend(sc["suggested_edits"][:5] or [f"Add: {labels}"])
        evidence_parts.extend(
            f"{r['label']} — {_frac(r)} cited pages have it, QC does not"
            for r in rec_feats
        )
        confidence = 0.7 if tier == "high" else 0.45
        priority = "high" if any(r["geo_weight"] == "high" for r in rec_feats) else "medium"
    elif sufficient_winners:
        problem_parts.append(
            f"QC has a page for '{sc['question']}' ({sc['qc_url']}) but AI engines cite other pages "
            f"for this question. It matches the analyzed winners on every checklist feature most of "
            f"them share - the remaining signals are weaker and below the evidence bar."
        )
        if emergent_edit:
            action_parts.append(f"{emergent_edit} (LLM-observed pattern, not a verified structural gap)")
        action_parts.extend(
            f"Consider adding {r['label'].lower()} - {_frac(r)} analyzed cited pages have it"
            for r in partial[:3]
        )
        evidence_parts.extend(
            f"{r['label']} — {_frac(r)} cited pages have it, QC does not (below prevalence bar)"
            for r in partial
        )
        if emergent_insight:
            evidence_parts.append(f"LLM-observed pattern (lower confidence): {emergent_insight}")
    else:
        problem_parts.append(
            f"QC has a page for '{sc['question']}' ({sc['qc_url']}) but too few cited pages were "
            f"readable ({sc['winners_total']}) to run the winner-comparison checklist."
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

        problem_parts.append(
            f"Separately, independent of the winner comparison above, QC's {lead['label'].lower()} "
            f"is {_fmt(lead, 'qc_value')} against a published target of {lead['target_min']}-"
            f"{lead['target_max']}{'%' if lead['unit'] == 'pct' else ' levels'} - the highest-priority "
            f"structural metric out of range" +
            (f" ({len(rest)} more also measured out of range - see structural metrics)."
             if rest else ".")
        )
        action_parts.append(
            f"Bring {lead['label'].lower()} into the {lead['target_min']}-{lead['target_max']}"
            f"{'%' if lead['unit'] == 'pct' else ' levels'} target range (QC: {_fmt(lead, 'qc_value')})" +
            (f"; {len(rest)} more metric(s) also out of range - see structural metrics table"
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
                                       "winners_present", "winners_total", "winners_pct")}
                    for r in rec_feats
                ],
                "partial_gaps": [
                    {k: r[k] for k in ("id", "label", "geo_weight",
                                       "winners_present", "winners_total", "winners_pct")}
                    for r in partial
                ],
                "metric_gaps": [
                    {k: r[k] for k in ("id", "label", "geo_weight", "confidence", "unit",
                                       "qc_value", "target_min", "target_max")}
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
