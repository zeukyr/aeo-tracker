"""
Per-question recommendation router
(docs/ai/recommendation-question-router-plan.md, §5.1).

Replaces the old "run every builder on every topic, additively" flow with:
select losing questions -> classify each question's cited winners FIRST ->
route to exactly one branch. The feature-diff (Tab 2 scorecard) is a LEAF of
the fix branch, not the entry point - so a course page is never scored against
informational guides (the bug the router exists to kill).

Branches (each losing question terminates in exactly one):

  FIX        QC has a same-kind page that still loses -> per-question
             feature-diff (scorecard), deduped by QC page.
  BUILD      ownable winners (editorial/competitor) and QC lacks the page or
             has the wrong KIND of page - buildability-gated by topic; also
             the fallback for known-unownable winners (wikipedia/.gov ->
             "earn the slot indirectly").
  REACH OUT  non-ownable winners (ugc/review/reference) with a real channel
             (registry / page affordance / source-type default, §5.7), or a
             reputation question whose ownable winners are pitchable.
  TRIAGE     everything the router cannot action with confidence - visible,
             never a silent drop:
               fragmented_field       no winner type clears the dominance bar
                                      (deliberately NOT auto-built; flagged
                                      build_candidate when the topic is
                                      buildable, for a human to green-light)
               no_cited_winners       QC loses but nothing external is cited
               feasibility_unknown    non-ownable winners, no channel found
               reputation_no_channel  can't build credibility, nothing to pitch

Work-stream note (R9): reach-out recs emit action_type in
{outreach, citation, community}; _work_stream still maps those to "strategic"
until the Tab 3 frontend lands, so the cards stay visible in Strategic Growth.
"""

import os
import re
import json

from src.logger import logger
from api.db import get_connection, _date_filter
from api.queries.page_facts import (
    get_page_facts,
    get_pages_facts,
    genre_gap,
    source_type,
    dominant_source_type,
    inclusion_opportunity,
    school_for_url,
    _root_domain,
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

_CHANNELS_PATH = os.path.join(os.path.dirname(__file__), "..", "knowledge", "outreach_channels.json")


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
# Outreach feasibility (§5.7): registry -> page affordance -> source default
# ─────────────────────────────────────────────────────────────────────────────

_channels_cache = None


def _load_channels():
    global _channels_cache
    if _channels_cache is None:
        with open(_CHANNELS_PATH, "r", encoding="utf-8") as f:
            _channels_cache = json.load(f)
    return _channels_cache


# Self-serve submission/claim affordances visible in page content. A match is
# the evidence - deterministic, no LLM.
_OUTREACH_AFFORDANCE = re.compile(
    r"\b(write for us|submit (a )?(listing|guest|your)|contribute|"
    r"add your (business|school|listing)|claim (this|your) (listing|profile|business)|"
    r"get listed|nominate|advertise with us)\b", re.I)

# A contact route but no self-serve channel -> pitchable, gated.
_CONTACT_HINT = re.compile(r"\bcontact (us|the editor)|editorial team|media inquir|press@|editor@", re.I)

# When the domain is unknown and the page couldn't be read, the ownability
# bucket itself implies the channel.
_SOURCE_TYPE_DEFAULTS = {
    "ugc":       {"channel": "participate", "feasibility": "open",
                  "mechanism": "Participate authentically as a named QC presence (expert answers, AMAs)."},
    "review":    {"channel": "claim", "feasibility": "gated",
                  "mechanism": "Claim or request a QC profile/listing on the platform."},
    "reference": {"channel": "align", "feasibility": "closed",
                  "mechanism": "No direct channel. Publish the authoritative source such pages cite."},
    "editorial": {"channel": "pitch", "feasibility": "unknown",
                  "mechanism": "No verified channel found on the page."},
}


def outreach_feasibility(facts):
    """
    {channel, feasibility: open|gated|closed|unknown, mechanism, evidence}
    for one winning page. Registry override -> page-content affordance scan ->
    source-type default. Deterministic; "unknown" means we failed to classify
    the channel - the router triages that rather than forcing an action.
    """
    registry = _load_channels()
    domain = facts.get("domain", "")
    root = _root_domain(domain)
    entry = registry["domains"].get(root)
    if entry is None and domain.endswith(".gov"):
        entry = registry["gov_tld"]
    if entry:
        return {**{k: entry[k] for k in ("channel", "feasibility", "mechanism")},
                "evidence": f"registry: {root}"}

    if facts.get("status") == "ok":
        haystack = " ".join(filter(None, [
            facts.get("title") or "",
            " ".join(facts.get("headings") or []),
            facts.get("content_excerpt") or "",
        ]))
        m = _OUTREACH_AFFORDANCE.search(haystack)
        if m:
            return {"channel": "submit", "feasibility": "open",
                    "mechanism": f"Use the page's own channel ('{m.group(0)}').",
                    "evidence": f"page affordance: '{m.group(0)}'"}
        if _CONTACT_HINT.search(haystack):
            return {"channel": "pitch", "feasibility": "gated",
                    "mechanism": "Pitch via the site's contact/editorial route.",
                    "evidence": "page offers a contact route, no self-serve channel"}

    default = _SOURCE_TYPE_DEFAULTS.get(source_type(facts))
    if default:
        return {**default, "evidence": f"source-type default: {source_type(facts)}"}
    return {"channel": None, "feasibility": "unknown",
            "mechanism": "No channel could be determined.",
            "evidence": f"unclassified source: {domain or 'no domain'}"}


def _bucket_feasibility(facts_list, bucket):
    """
    Feasibility for a question's dominant bucket: walk that bucket's winners
    by citation weight and take the first conclusive (non-unknown) answer, so
    one unreadable page doesn't hide a reachable channel behind it.
    Returns (feasibility_dict, facts_of_target).
    """
    in_bucket = sorted((f for f in facts_list if source_type(f) == bucket),
                       key=lambda f: -(f.get("citation_count") or 0))
    first = None
    for f in in_bucket:
        feas = outreach_feasibility(f)
        if first is None:
            first = (feas, f)
        if feas["feasibility"] != "unknown":
            return feas, f
    return first if first else ({"channel": None, "feasibility": "unknown",
                                 "mechanism": "No winners in bucket.",
                                 "evidence": "empty bucket"}, None)


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
    Returns {"branch": "fix"|"build"|"reach_out"|"triage", "question": q,
    "winners": [...facts], "dominant": (bucket, share), "qc_url",
    "genre_mismatch", "feasibility", "reason", ...}.
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
    common = {"question": q, "winners": facts, "dominant": (bucket, share)}

    # ── no dominant winner type: a finding for a human, not an auto-build ──
    if bucket is None:
        return triage(q, "fragmented_field", build_candidate=buildable,
                      winners=facts, dominant=(bucket, share))

    # ── non-ownable winners: reach out if a channel exists ──
    if bucket in _NON_OWNABLE:
        feas, target = _bucket_feasibility(facts, bucket)
        if feas["feasibility"] in ("open", "gated"):
            return {"branch": "reach_out", "reason": "non_ownable_winners",
                    "feasibility": feas, "feasibility_target": target, **common}
        if feas["feasibility"] == "closed":   # wikipedia / .gov - KNOWN unownable
            return {"branch": "build", "reason": "earn_indirect",
                    "feasibility": feas, "feasibility_target": target,
                    "qc_url": None, "genre_mismatch": None, **common}
        return triage(q, "feasibility_unknown", winners=facts,
                      dominant=(bucket, share), feasibility=feas)

    # ── ownable winners (editorial / competitor): does QC have this page? ──
    cov = diagnose_text_coverage(q["question"], school=q["school"])
    qc_url = cov.get("qc_url") if cov.get("verdict") == "have_page" else None
    gm = None
    if qc_url:
        # Has a page - but is it the KIND engines reward? A mismatch SUPPRESSES
        # the feature-diff (the core bug fix); the build branch owns that case.
        gm = genre_gap(get_page_facts(qc_url), facts)
        if not gm:
            # ── FIX: same-kind vs same-kind, the feature-diff is legitimate ──
            return {"branch": "fix", "reason": "qc_page_same_kind_still_loses",
                    "qc_url": qc_url, "genre_mismatch": None, **common}

    # missing page, or the wrong kind of page -> BUILD, gated by topic
    if buildable:
        return {"branch": "build",
                "reason": "ownable_wrong_kind_page" if gm else "ownable_no_qc_page",
                "qc_url": qc_url, "genre_mismatch": gm, **common}

    # reputation topic: can't build credibility - pitch the winners or triage
    feas, target = _bucket_feasibility(facts, bucket)
    if feas["feasibility"] in ("open", "gated"):
        return {"branch": "reach_out", "reason": "reputation_reach_out",
                "feasibility": feas, "feasibility_target": target,
                "qc_url": qc_url, "genre_mismatch": gm, **common}
    return triage(q, "reputation_no_channel", winners=facts,
                  dominant=(bucket, share), qc_url=qc_url, genre_mismatch=gm)


# ─────────────────────────────────────────────────────────────────────────────
# Leaf builders: route -> recommendation dicts (existing shape untouched)
# ─────────────────────────────────────────────────────────────────────────────

def _segment_for(q):
    """Topic segment when there is one (R6 will move this to question grain);
    school as fallback so measurement never scopes to nothing."""
    if q.get("topic"):
        return {"dimension": "topic", "value": q["topic"]}
    if q.get("school"):
        return {"dimension": "school", "value": q["school"]}
    return {"dimension": "global", "value": None}


def _winner_summary(facts, limit=5):
    facts = sorted(facts or [], key=lambda f: -(f.get("citation_count") or 0))[:limit]
    return [{"url": f["url"], "page_type": f.get("page_type"),
             "source_type": source_type(f),
             "citation_count": f.get("citation_count") or 0} for f in facts]


def _winners_evidence(q, facts, limit=4):
    top = sorted(facts, key=lambda f: -(f.get("citation_count") or 0))[:limit]
    cited = "; ".join(f"{f.get('domain')} ({f.get('citation_count')}x)" for f in top)
    pct = round(q["qc_share"] * 100)
    return (f"For '{q['question']}' engines cite {cited} across {q['n_responses']} responses; "
            f"QC is cited in {pct}% of them.")


def _router_detail(route, group=None):
    q = route["question"]
    bucket, share = route.get("dominant") or (None, None)
    detail = {
        "branch": route["branch"],
        "reason": route.get("reason"),
        "question_id": q["question_id"],
        "question": q["question"],
        "qc_share": q["qc_share"],
        "dominant_source": bucket,
        "dominant_share": share,
        "winners": _winner_summary(route.get("winners")),
    }
    if group:
        detail["grouped_questions"] = [r["question"]["question"] for r in group]
    if route.get("feasibility"):
        detail["outreach_feasibility"] = route["feasibility"]
    if route.get("genre_mismatch"):
        detail["genre_mismatch"] = route["genre_mismatch"]
    return detail


def _build_rec(route, group):
    """One BUILD rec per dedup group. Singletons fire (a lone question can
    carry independent demand); group size is a priority booster, not a gate."""
    q = route["question"]
    gm = route.get("genre_mismatch")
    bucket = (route.get("dominant") or (None,))[0]
    evidence = _winners_evidence(q, route.get("winners") or [])
    benchmark = ", ".join(w["url"] for w in _winner_summary(route.get("winners"), limit=2))

    if route["reason"] == "earn_indirect":
        domain = (route.get("feasibility_target") or {}).get("domain") or "the citing sources"
        problem = (f"'{q['question']}' is answered from reference sources QC cannot own or pitch "
                   f"({domain}); QC is cited in {round(q['qc_share'] * 100)}% of responses.")
        action = (f"No direct channel to {domain} - publish the authoritative, citable QC content "
                  f"such sources reference, to earn the slot indirectly. Benchmark: {benchmark}.")
    elif gm:
        if gm["winner_genre"] == "informational":
            action = (f"Build a standalone informational asset answering '{q['question']}' - a "
                      f"how-to / career guide, not another course page - and link it to the "
                      f"existing page ({route['qc_url']}). Keep tuning that page separately.")
        else:
            action = (f"Build a dedicated course/program page for '{q['question']}' - the existing "
                      f"informational page ({route['qc_url']}) serves a different intent than the "
                      f"commercial pages engines cite here. Link the two.")
        problem = (f"QC's page for '{q['question']}' ({route['qc_url']}) is a {gm['qc_genre']} page, "
                   f"but {gm['winners_with_genre']}/{gm['winners_classified']} genre-classifiable "
                   f"cited pages are {gm['winner_genre']} - engines reward a kind of page QC "
                   f"doesn't have here.")
        evidence += (f" QC's covered page is {gm['qc_genre']}; {gm['winners_with_genre']} of "
                     f"{gm['winners_classified']} classifiable cited pages are {gm['winner_genre']}.")
    else:
        problem = f"QC has no page answering '{q['question']}', and engines cite {bucket} pages instead."
        if bucket == "competitor":
            action = (f"Create a QC page answering '{q['question']}' - rivals won this query with "
                      f"their own pages. Benchmark depth and coverage against: {benchmark}.")
        else:
            action = (f"Build educational content (a guide/hub, not a sales page) answering "
                      f"'{q['question']}' - editorial pages win this query, so a self-serving page "
                      f"won't take the neutral slot. Model it on: {benchmark}.")

    priority = "high" if len(group) >= 2 else "medium"
    school = q.get("school") or (school_for_url(route.get("qc_url")) if route.get("qc_url") else None)
    return {
        "problem": problem,
        "action": action,
        "priority": priority,
        "school": school,
        "evidence": evidence,
        "action_type": "content",
        "target": q["question"],
        "segment": _segment_for(q),
        "metric_impact": "citation_rate",
        "expected_direction": 1,
        "expected_magnitude": None,
        "effort": "L",
        "confidence": 0.55,
        "detail": {"router": _router_detail(route, group)},
    }


def _reach_out_rec(route, group):
    """One REACH-OUT rec per dedup group; the feasibility verdict shapes the
    card (open -> concrete action, gated -> application/partnership framing)."""
    q = route["question"]
    bucket = (route.get("dominant") or (None,))[0]
    feas = route["feasibility"]
    target = route.get("feasibility_target") or {}
    domain = target.get("domain") or "the cited platform"
    gated = feas["feasibility"] == "gated"

    problem = (f"AI engines answer '{q['question']}' from {bucket} sources QC can't own - "
               f"{domain} leads - and QC is cited in {round(q['qc_share'] * 100)}% of responses.")
    action = feas["mechanism"]
    if gated:
        action += " (Requires application/approval - budget lead time.)"
    evidence = _winners_evidence(q, route.get("winners") or []) + f" Channel: {feas['evidence']}."

    return {
        "problem": problem,
        "action": action,
        "priority": "medium",
        "school": q.get("school"),
        "evidence": evidence,
        "action_type": "community" if bucket == "ugc" else "outreach",
        "target": target.get("url") or domain,
        "segment": _segment_for(q),
        "metric_impact": "visibility_score" if bucket == "ugc" else "citation_rate",
        "expected_direction": 1,
        "expected_magnitude": None,
        "effort": "M" if gated else "S",
        "confidence": 0.5 if gated else 0.6,
        "detail": {"router": _router_detail(route, group)},
    }


def _inclusion_recs(routes):
    """
    Per-winner inclusion opportunities (§5.5): roundups/directories that
    provably list rivals and never QC, surfaced across ALL routed winners and
    feasibility-gated. A page that verifiably lists providers is pitchable by
    construction, so the editorial default here is gated (not unknown) -
    closed targets (e.g. a .gov directory) are skipped, the build branch
    already owns aligning to those.
    """
    seen, out = set(), []
    for route in routes:
        for f in route.get("winners") or []:
            url = f.get("url")
            if url in seen or not inclusion_opportunity(f):
                continue
            seen.add(url)
            feas = outreach_feasibility(f)
            if feas["feasibility"] == "closed":
                continue
            if feas["feasibility"] == "unknown":
                feas = {"channel": "pitch", "feasibility": "gated",
                        "mechanism": "Pitch QC for inclusion - the page provably lists rival providers.",
                        "evidence": "page verified to list competitors and not QC"}
            q = route["question"]
            rivals = ", ".join(sorted(f.get("brand_mentions", {}).keys())[:5])
            is_directory = f.get("page_type") == "directory"
            out.append({
                "problem": (f"{url} is cited {f.get('citation_count')}x for '{q['question']}' and "
                            f"lists {rivals} - but never mentions QC."),
                "action": (f"Submit a QC listing to this directory ({url})." if is_directory else
                           f"Pitch QC for inclusion in this comparison article ({url}) - it already "
                           f"lists {rivals}.") + (" (Requires approval.)" if feas["feasibility"] == "gated" else ""),
                "priority": "high" if (f.get("citation_count") or 0) >= 3 else "medium",
                "school": q.get("school"),
                "evidence": (f"{url} cited {f.get('citation_count')}x; page content verified to "
                             f"list {rivals} and never mention QC. Channel: {feas['evidence']}."),
                "action_type": "citation" if is_directory else "outreach",
                "target": url,
                "segment": _segment_for(q),
                "metric_impact": "citation_rate",
                "expected_direction": 1,
                "expected_magnitude": None,
                "effort": "S",
                "confidence": 0.8,   # the inclusion gate is verified page content
                "detail": {"router": {**_router_detail(route), "branch": "inclusion_opportunity"},
                           "outreach_feasibility": feas,
                           "opportunity": {"url": url, "lists_competitors": rivals.split(", ")}},
            })
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Dispatch + dedup (§5.6)
# ─────────────────────────────────────────────────────────────────────────────

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
        "winners":         _winner_summary(route.get("winners")),
    }


def _weakest(group):
    """Representative route: lowest QC share, then highest citation volume."""
    return min(group, key=lambda r: (r["question"]["qc_share"],
                                     -r["question"]["n_citations"]))


def _grouped(routes, key_fn):
    groups = {}
    for r in routes:
        groups.setdefault(key_fn(r), []).append(r)
    return groups.values()


def build_router_recommendations(days=None):
    """
    Route every losing question; returns (recommendations, triage).
    Dedup per §5.6 - near-duplicate questions converge on the same target:
      fix       one scorecard per unique QC page (bounds the LLM passes)
      build     one rec per (school, topic, page-kind, qc_url) group;
                group size boosts priority, singletons still fire
      reach_out one rec per (bucket, target root domain)
    Inclusion opportunities are surfaced across all routed winners, deduped
    by URL. The triage list is ranked weakest-first by construction.
    """
    routes = [route_question(q, days) for q in get_losing_questions(days)]
    by_branch = {}
    for r in routes:
        by_branch.setdefault(r["branch"], []).append(r)

    recommendations = []

    # fix: one scorecard per unique QC page
    for group in _grouped(by_branch.get("fix", []), lambda r: r["qc_url"]):
        rep = _weakest(group)
        q = rep["question"]
        try:
            sc = build_scorecard(q["topic"] or q["question"], rep["qc_url"],
                                 question=q["question"], days=days,
                                 winner_facts=rep["winners"])
            rec = scorecard_to_recommendation(sc)
        except Exception as e:
            logger.warning(f"Router fix branch failed for {rep['qc_url']}: {e}")
            rec = None
        if not rec:
            logger.info(f"Router fix: nothing to recommend for {rep['qc_url']} "
                        f"(question: {q['question'][:60]})")
            continue
        rec["detail"]["router"] = _router_detail(rep, group)
        recommendations.append(rec)

    # build: group by (school, topic, kind of page to build, existing qc page)
    def _build_key(r):
        gm = r.get("genre_mismatch")
        kind = gm["winner_genre"] if gm else (
            "commercial" if (r.get("dominant") or (None,))[0] == "competitor" else "informational")
        return (r["question"].get("school"), r["question"].get("topic"), kind, r.get("qc_url"))

    for group in _grouped(by_branch.get("build", []), _build_key):
        recommendations.append(_build_rec(_weakest(group), group))

    # reach out: group by (bucket, root domain of the channel target)
    def _reach_key(r):
        target = r.get("feasibility_target") or {}
        return ((r.get("dominant") or (None,))[0],
                _root_domain(target.get("domain") or ""))

    for group in _grouped(by_branch.get("reach_out", []), _reach_key):
        recommendations.append(_reach_out_rec(_weakest(group), group))

    # verified inclusion opportunities across every route's winners
    recommendations.extend(_inclusion_recs(routes))

    triage_list = [_triage_entry(r) for r in by_branch.get("triage", [])]
    return recommendations, triage_list


if __name__ == "__main__":
    import io, sys
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    recs, tri = build_router_recommendations()
    print(f"=== recommendations ({len(recs)}) ===")
    for r in recs:
        branch = (r.get("detail", {}).get("router") or {}).get("branch", "?")
        print(f"  [{branch}/{r['action_type']}] {r['target']}")
        print(f"      {r['action'][:150]}")
    print(f"\n=== triage ({len(tri)}) ===")
    for t in tri:
        print(f"  [{t['reason']:<24}] share={t['qc_share']:.2f} "
              f"dominant={t['dominant_source']} {t['question'][:70]}")
