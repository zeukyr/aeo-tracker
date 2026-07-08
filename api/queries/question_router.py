"""
Per-question recommendation router
(docs/ai/recommendation-question-router-plan.md, §5.1).

Replaces the old "run every builder on every topic, additively" flow with:
select losing questions -> classify each question's cited winners FIRST ->
route to exactly one branch. The feature-diff (Tab 2 scorecard) is a LEAF of
the fix branch, not the entry point - so a course page is never scored against
informational guides (the bug the router exists to kill).

CURRENT SCOPE (router foundation, R1-R5): only the FIX branch dispatches to a
rec builder. Every non-fix outcome - build, reach-out, fragmented winners -
routes to TRIAGE: a visible list of losing questions the router found but
cannot yet auto-action. Triage reasons are findings, not errors:

  fragmented_field         no winner type clears the dominance bar; when the
                           topic is buildable it's flagged build_candidate
                           (QC could plausibly own the query with one page)
  no_cited_winners         QC loses but engines cite nothing external here
  non_ownable_winners      ugc/review/reference dominate -> future reach-out
                           branch (Tab 3, feasibility-gated)
  ownable_no_qc_page       editorial/competitor winners, QC has no page for
                           this intent -> future build branch (Tab 1)
  ownable_wrong_kind_page  QC has a page but engines reward the other genre
                           (genre_mismatch attached) -> future build branch

The governing principle: a losing question is NEVER silently dropped - every
route_question call returns a branch, and "triage" is a first-class outcome.

Until the build/reach-out branches land, build_tab1_recommendations still runs
at topic grain in recommendations_synthesis (so build/earn recs don't vanish);
it retires when those branches are implemented here.
"""

from src.logger import logger
from api.db import get_connection, _date_filter
from api.queries.page_facts import (
    get_page_facts,
    get_pages_facts,
    genre_gap,
    source_type,
    dominant_source_type,
)
from api.queries.tab1_strategy import get_question_cited_urls
from api.queries.tab2_scorecard import build_scorecard, scorecard_to_recommendation
from api.queries.sitemap_coverage import diagnose_text_coverage

# Topic gates the BUILD branch only (a reputation question can't build its way
# to credibility) - never selection, never the fix or reach-out branches.
BUILDABLE_TOPICS = {
    "Course Discovery", "How to Become",
    "Starting a Business", "Career Exploration",
}
REPUTATION_TOPICS = {"Brand Credibility", "Competitor Comparison"}

_MAX_QC_SHARE = 0.15          # "losing": QC cited in <= 15% of responses
_NON_OWNABLE = ("ugc", "review", "reference")


# ─────────────────────────────────────────────────────────────────────────────
# Selection: per-question QC citation share, ALL topics (topic-blind)
# ─────────────────────────────────────────────────────────────────────────────

def get_losing_questions(days=None, max_qc_share=_MAX_QC_SHARE):
    """
    Questions where QC is (almost) never cited, weakest first. Deliberately
    topic-blind - buildability gates the build branch, not selection, so no
    category of losing question is swallowed before it's even looked at.
    Only questions with mention_responses appear (sentiment-only questions are
    handled by the concern/credibility engines).
    """
    date_m = _date_filter(days).replace("AND created_at", "AND m.created_at")
    query = f"""
        SELECT q.id, q.question, q.topic, q.school,
               AVG(CASE WHEN m.qc_cited THEN 1 ELSE 0 END) as qc_share,
               COUNT(*) as n_responses,
               COALESCE(SUM(COALESCE(array_length(m.citations, 1), 0)), 0) as n_citations
        FROM mention_responses m
        JOIN questions q ON q.id = m.question_id
        WHERE 1=1 {date_m}
        GROUP BY q.id, q.question, q.topic, q.school
        HAVING AVG(CASE WHEN m.qc_cited THEN 1 ELSE 0 END) <= %s
        ORDER BY 5 ASC, 7 DESC;
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, [max_qc_share])
            rows = cur.fetchall()
    return [
        {
            "question_id": r[0], "question": r[1], "topic": r[2], "school": r[3],
            "qc_share": round(float(r[4]), 3), "n_responses": r[5], "n_citations": int(r[6]),
        }
        for r in rows
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Routing
# ─────────────────────────────────────────────────────────────────────────────

def triage(q, reason, build_candidate=False, **extra):
    """A first-class routing outcome (plan §5.9) - never a silent None."""
    return {"branch": "triage", "question": q, "reason": reason,
            "build_candidate": build_candidate, **extra}


def route_question(q, days=None):
    """
    Classify one losing question's cited winners and pick its branch.
    Returns {"branch": "fix"|"triage", "question": q, "winners": [...facts],
    "dominant": (bucket, share), "qc_url", "genre_mismatch", "reason", ...}.
    (build / reach_out become branches when their leaf builders land; until
    then their conditions terminate in triage with a descriptive reason.)
    """
    winners = get_question_cited_urls(q["question_id"], days)
    if not winners:
        return triage(q, "no_cited_winners")

    counts = {w["url"]: w["count"] for w in winners}
    facts = get_pages_facts([w["url"] for w in winners])
    for f in facts:
        f["citation_count"] = counts.get(f["url"], 0)

    bucket, share = dominant_source_type(facts)
    buildable = q["topic"] in BUILDABLE_TOPICS
    common = {"winners": facts, "dominant": (bucket, share)}

    # ── no dominant winner type: a finding, not a silent drop ──
    if bucket is None:
        return triage(q, "fragmented_field", build_candidate=buildable, **common)

    # ── non-ownable winners -> future reach-out branch (feasibility-gated) ──
    if bucket in _NON_OWNABLE:
        return triage(q, "non_ownable_winners", **common)

    # ── ownable winners (editorial / competitor): does QC have this page? ──
    cov = diagnose_text_coverage(q["question"], school=q["school"])
    qc_url = cov.get("qc_url") if cov.get("verdict") == "have_page" else None
    if not qc_url:
        return triage(q, "ownable_no_qc_page", build_candidate=buildable, **common)

    # Has a page - but is it the KIND engines reward? A mismatch SUPPRESSES the
    # feature-diff (the core bug fix); the future build branch owns that case.
    gm = genre_gap(get_page_facts(qc_url), facts)
    if gm:
        return triage(q, "ownable_wrong_kind_page", build_candidate=buildable,
                      qc_url=qc_url, genre_mismatch=gm, **common)

    # ── FIX: same-kind vs same-kind, the feature-diff is legitimate here ──
    return {"branch": "fix", "question": q, "qc_url": qc_url,
            "genre_mismatch": None, "reason": "qc_page_same_kind_still_loses",
            **common}


# ─────────────────────────────────────────────────────────────────────────────
# Dispatch + dedup
# ─────────────────────────────────────────────────────────────────────────────

def _winner_summary(route, limit=5):
    """Compact, JSON-safe view of a route's winners for the triage list."""
    facts = route.get("winners") or []
    facts = sorted(facts, key=lambda f: -(f.get("citation_count") or 0))[:limit]
    return [{"url": f["url"], "page_type": f.get("page_type"),
             "source_type": source_type(f),
             "citation_count": f.get("citation_count") or 0} for f in facts]


def _triage_entry(route):
    """Flatten a triage route for surfacing (kept small - no full page facts)."""
    q = route["question"]
    bucket, share = route.get("dominant") or (None, None)
    return {
        "question_id":     q["question_id"],
        "question":        q["question"],
        "topic":           q["topic"],
        "school":          q["school"],
        "qc_share":        q["qc_share"],
        "n_citations":     q["n_citations"],
        "reason":          route["reason"],
        "build_candidate": route.get("build_candidate", False),
        "dominant_source": bucket,
        "dominant_share":  share,
        "qc_url":          route.get("qc_url"),
        "genre_mismatch":  route.get("genre_mismatch"),
        "winners":         _winner_summary(route),
    }


def build_router_recommendations(days=None):
    """
    Route every losing question; returns (recommendations, triage). Fix routes
    are deduped by QC page (plan §5.6): near-duplicate questions hit the same
    URL, and the scorecard's LLM passes should run once per PAGE, not per
    question - the representative is the weakest / highest-volume question.
    The triage list is ranked weakest-first by construction (selection order).
    """
    routes = [route_question(q, days) for q in get_losing_questions(days)]

    triage_list = [_triage_entry(r) for r in routes if r["branch"] == "triage"]

    by_page = {}
    for r in routes:
        if r["branch"] == "fix":
            by_page.setdefault(r["qc_url"], []).append(r)

    recommendations = []
    for qc_url, group in by_page.items():
        rep = min(group, key=lambda r: (r["question"]["qc_share"],
                                        -r["question"]["n_citations"]))
        q = rep["question"]
        try:
            sc = build_scorecard(q["topic"], qc_url, question=q["question"],
                                 days=days, winner_facts=rep["winners"])
            rec = scorecard_to_recommendation(sc)
        except Exception as e:
            logger.warning(f"Router fix branch failed for {qc_url}: {e}")
            rec = None
        if not rec:
            logger.info(f"Router fix: nothing to recommend for {qc_url} "
                        f"(question: {q['question'][:60]})")
            continue
        rec["detail"]["router"] = {
            "branch": "fix",
            "question_id": q["question_id"],
            "question": q["question"],
            "qc_share": q["qc_share"],
            "grouped_questions": [r["question"]["question"] for r in group],
        }
        recommendations.append(rec)

    return recommendations, triage_list


if __name__ == "__main__":
    import io, sys, json
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    recs, tri = build_router_recommendations()
    print(f"=== fix recommendations ({len(recs)}) ===")
    for r in recs:
        print(json.dumps({k: r[k] for k in ("problem", "action", "target")}, indent=1))
    print(f"\n=== triage ({len(tri)}) ===")
    for t in tri:
        print(f"  [{t['reason']:<24}] share={t['qc_share']:.2f} "
              f"dominant={t['dominant_source']} {t['question'][:70]}")
