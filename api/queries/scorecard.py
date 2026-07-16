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
from api.queries.page_facts import get_pages_facts, get_page_facts, page_genre, school_for_url

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

_FEATURES_PATH = os.path.join(os.path.dirname(__file__), "..", "knowledge", "geo_features.json")

MIN_WINNERS = 3          # below this the comparison isn't trustworthy (high tier)
MIN_READABLE_WINNERS = 2 # below this there is no comparison at all - insufficient data
TOP_N_WINNERS = 5        # cited pages to compare against

# Cited page types that carry a comparable information architecture. Community
# threads, videos and pages we couldn't read can't be scored.
_COMPARABLE_TYPES = {"competitor", "roundup", "directory", "association", "government", "guide", "editorial"}

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
    """All feature ids -> present bool for one page (deterministic + semantic)."""
    semantic_specs = [f for f in features if f["detection"] == "semantic"]
    semantic = _semantic_features(facts, question, semantic_specs)
    present = {}
    for feat in features:
        if feat["detection"] == "semantic":
            present[feat["id"]] = semantic.get(feat["id"], False)
        else:
            present[feat["id"]] = _deterministic_present(feat["id"], facts)
    return present


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
    for feat in features:
        if feat["id"] in _INAPPLICABLE_ON_COMMERCIAL and qc_genre == "commercial":
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
    if not sc.get("qc_readable") or sc["winners_total"] < MIN_READABLE_WINNERS:
        return None

    rec_feats = [r for r in sc["features"] if r["recommend"]]
    # Sub-threshold gaps: QC lacks the feature and at least one readable
    # winner has it, but prevalence never cleared the "most" bar. Quantified
    # supplementary evidence, never asserted as a shared pattern.
    partial = [r for r in sc["features"]
               if not r["qc_has"] and not r["recommend"]
               and r["winners_present"] > 0 and r["geo_weight"] != "low"]
    emergent_insight = (sc.get("emergent_insight") or "").strip()
    emergent_edit = (sc.get("emergent_edit") or "").strip()
    has_emergent = bool(emergent_insight or emergent_edit)

    if not rec_feats and not partial and not has_emergent:
        return None   # true feature parity - the triage reason says exactly that

    tier = "high" if (rec_feats and sc.get("sufficient")) else "low"
    coverage = _coverage_note(sc)

    if rec_feats:
        labels = ", ".join(r["label"].lower() for r in rec_feats)
        problem = (
            f"QC has a page for '{sc['question']}' ({sc['qc_url']}) but AI engines cite other pages "
            f"for this question. Across {sc['winners_total']} analyzed cited pages it is missing "
            f"{len(rec_feats)} feature(s) they share: {labels}."
        )
        action = "; ".join(sc["suggested_edits"][:5]) or f"Add: {labels}"
        evidence = "; ".join(
            f"{r['label']} — {_frac(r)} cited pages have it, QC does not"
            for r in rec_feats
        )
        confidence = 0.7 if tier == "high" else 0.45
        priority = "high" if any(r["geo_weight"] == "high" for r in rec_feats) else "medium"
    else:
        problem = (
            f"QC has a page for '{sc['question']}' ({sc['qc_url']}) but AI engines cite other pages "
            f"for this question. It matches the analyzed winners on every checklist feature most of "
            f"them share - the remaining signals are weaker and below the evidence bar."
        )
        actions = []
        if emergent_edit:
            actions.append(f"{emergent_edit} (LLM-observed pattern, not a verified structural gap)")
        actions.extend(
            f"Consider adding {r['label'].lower()} - {_frac(r)} analyzed cited pages have it"
            for r in partial[:3]
        )
        action = "; ".join(actions)
        parts = [f"{r['label']} — {_frac(r)} cited pages have it, QC does not (below prevalence bar)"
                 for r in partial]
        if emergent_insight:
            parts.append(f"LLM-observed pattern (lower confidence): {emergent_insight}")
        evidence = "; ".join(parts)
        confidence = 0.35
        priority = "low"

    return {
        "problem": problem,
        "action": action,
        "priority": priority,
        "school": school_for_url(sc["qc_url"]),
        "evidence": f"{coverage} {evidence}".strip(),
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
