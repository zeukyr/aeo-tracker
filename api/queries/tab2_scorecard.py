"""
Tab 2 "Improve Existing Pages" scorecard (Phase 4 of
docs/ai/recommendation-two-tab-plan.md).

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
"""

import os
import json

from openai import OpenAI

from src.logger import logger
from api.queries.tab1_strategy import get_topic_cited_urls
from api.queries.page_facts import get_pages_facts, get_page_facts

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

_FEATURES_PATH = os.path.join(os.path.dirname(__file__), "..", "knowledge", "geo_features.json")

MIN_WINNERS = 3          # below this the comparison isn't trustworthy
TOP_N_WINNERS = 5        # cited pages to compare against

# Cited page types that carry a comparable information architecture. Community
# threads, videos and pages we couldn't read can't be scored.
_COMPARABLE_TYPES = {"competitor", "roundup", "directory", "association", "government", "guide", "editorial"}


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
            max_tokens=300,
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


def build_scorecard(topic, qc_url, question=None, days=None):
    """
    Full Tab 2 scorecard comparing QC's page against the pages AI cites for the
    topic. `sufficient` is False when too few comparable pages could be fetched
    (caller should fall back to a generic rec rather than assert a comparison).
    """
    question = question or f"{topic}"
    features = _load_features()

    qc_facts = get_page_facts(qc_url)

    cited = get_topic_cited_urls({"dimension": "topic", "value": topic}, days, limit=TOP_N_WINNERS + 4)
    counts = {c["url"]: c["count"] for c in cited}
    winner_facts = [f for f in get_pages_facts([c["url"] for c in cited])
                    if f.get("status") == "ok" and f.get("page_type") in _COMPARABLE_TYPES]
    winner_facts.sort(key=lambda f: -counts.get(f["url"], 0))
    winner_facts = winner_facts[:TOP_N_WINNERS]
    n = len(winner_facts)

    qc_present = _page_features(qc_facts, question, features) if qc_facts.get("status") == "ok" else {}
    winner_present = [_page_features(f, question, features) for f in winner_facts]

    rows = []
    for feat in features:
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
             "citation_count": counts.get(f["url"], 0)}
            for f in winner_facts
        ],
        "winners_total": n,
        "sufficient": n >= MIN_WINNERS,
        "features": rows,
        "emergent_insight": insight,
        "suggested_edits": suggested_edits,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Scorecard -> recommendation (deterministic; bypasses the generic-prose LLM)
# ─────────────────────────────────────────────────────────────────────────────

_DOMAIN_SCHOOL = {
    "qcpetstudies": "QC Pet Studies",
    "qceventplanning": "QC Event Planning",
    "qcdesignschool": "QC Design School",
    "qcmakeupacademy": "QC Makeup Academy",
}


def _school_for(url):
    for tok, name in _DOMAIN_SCHOOL.items():
        if tok in (url or ""):
            return name
    return None


def scorecard_to_recommendation(sc):
    """
    Turn a scorecard into a Tab 2 (technical) recommendation, or None if there's
    nothing to recommend / too little data. Built from the scorecard - not free
    LLM prose - so it names the page and the missing sections concretely, and
    carries the full scorecard in `detail` for the frontend card.
    """
    rec_feats = [r for r in sc["features"] if r["recommend"]]
    if not sc.get("sufficient") or not sc.get("qc_readable") or not rec_feats:
        return None

    labels = ", ".join(r["label"].lower() for r in rec_feats)
    problem = (
        f"QC has a page for '{sc['topic']}' ({sc['qc_url']}) but AI engines cite other pages "
        f"for this topic. Across {sc['winners_total']} cited pages it is missing {len(rec_feats)} "
        f"feature(s) they share: {labels}."
    )
    action = "; ".join(sc["suggested_edits"][:5]) or f"Add: {labels}"
    evidence = "; ".join(
        f"{r['label']} — {r['winners_present']}/{r['winners_total']} cited pages have it, QC does not"
        for r in rec_feats
    )
    return {
        "problem": problem,
        "action": action,
        "priority": "high" if any(r["geo_weight"] == "high" for r in rec_feats) else "medium",
        "school": _school_for(sc["qc_url"]),
        "evidence": evidence,
        "action_type": "technical",
        "target": sc["qc_url"],
        "segment": {"dimension": "topic", "value": sc["topic"]},
        "metric_impact": "citation_rate",
        "expected_direction": 1,
        "expected_magnitude": None,
        "effort": "M",
        "confidence": 0.7,
        "detail": {"scorecard": sc},
    }


def build_tab2_recommendations(days=None, max_topics=2):
    """
    Deterministic Tab 2 recs for the weakest topics where QC has a page engines
    skip: for each, score QC's covered page against the cited winners and emit a
    scorecard-backed rec. Bounded to keep fetch/LLM cost small.
    """
    from api.queries.recommendation_signals import get_weakest_topics
    from api.queries.sitemap_coverage import diagnose_coverage

    out = []
    topics = [t for t in get_weakest_topics(days, limit=20)
              if t.get("kind") == "mention" and (t.get("sample_n") or 0) >= 5]
    for t in topics:
        if len(out) >= max_topics:
            break
        seg = {"dimension": "topic", "value": t["topic"]}
        coverage = diagnose_coverage(seg)
        if not coverage.get("covered"):
            continue
        top = coverage["covered"][0]
        try:
            sc = build_scorecard(t["topic"], top["qc_url"], question=top["intent"], days=days)
            rec = scorecard_to_recommendation(sc)
        except Exception as e:
            logger.warning(f"Tab 2 scorecard failed for {t['topic']}: {e}")
            rec = None
        if rec:
            out.append(rec)
    return out


if __name__ == "__main__":
    import io, sys
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    topic = sys.argv[1] if len(sys.argv) > 1 else "How to Become"
    qc_url = sys.argv[2] if len(sys.argv) > 2 else "https://www.qcpetstudies.com/certification-courses/dog-grooming"
    question = sys.argv[3] if len(sys.argv) > 3 else "how to become a dog groomer"
    print(json.dumps(build_scorecard(topic, qc_url, question), indent=2, default=str))
