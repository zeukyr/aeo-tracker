"""
Tab 1 "Strategic Growth" engine (Phase 3 of docs/ai/recommendation-two-tab-plan.md).

For a weak topic where QC has no page, one generic "pursue inclusion" action
can't fit every cited URL - the cited URLs aren't the same kind of thing. This
module classifies what AI actually cites for the topic (via page_facts) and
turns the mix into structured, page-type-aware evidence:

  1. specific opportunities - roundups/directories that provably list rivals but
     not QC  -> "seek inclusion" / "submit listing" (gated on real page content).
  2. authority patterns    - associations, government, editorial guides
                             -> "benchmark & align content", never "pitch them".
  3. ecosystem patterns    - the aggregate composition of what's cited
                             (community-heavy? guides over sales pages?)
                             -> broad strategy signals that need no single URL.

And the build-vs-earn verdict: did competitors win this topic with their OWN
pages (Gap A - build an equivalent page) or did impartial third parties win
(Gap B - earn placement / build educational content)? Decided from the
composition of cited pages, not left to the model.

Phase 6 additions:
  - genre_check / coverage_genre_mismatches: the "have a page, wrong page"
    gray area. A covered intent whose QC page is the wrong GENRE for what
    engines reward (course sales page where winners are how-to guides) routes
    to Tab 1 as "build the missing genre", not Tab 2 "tune the page".
  - strategy_to_recommendations / build_tab1_recommendations: Tab 1 recs are
    now TEMPLATED from this analysis (the mirror of tab2's
    scorecard_to_recommendation) - the LLM no longer authors strategic recs
    for analyzed topics, so every claim in them traces to a verified fact.
"""

from src.logger import logger
from api.db import get_connection, _date_filter
from api.queries.page_facts import (
    get_page_facts,
    get_pages_facts,
    inclusion_opportunity,
    genre_gap,
    school_for_url,
    QC_DOMAIN_TOKENS,
)

# How many of the topic's top cited URLs to fetch + classify. Bounded: keeps
# the LLM/fetch cost per segment small and the evidence readable.
_TOP_N_URLS = 8

# page_types that are third-party impartial sources (Gap B signal) vs
# competitor-owned commercial pages (Gap A signal). Community/video are their
# own ecosystem signal and don't vote in build-vs-earn.
_IMPARTIAL_TYPES  = {"roundup", "directory", "association", "government", "guide", "editorial"}
_COMMERCIAL_TYPES = {"competitor"}

# Templated action per page type - the model picks details, not the strategy.
PAGE_TYPE_ACTIONS = {
    "roundup":     "seek inclusion — request consideration in this comparison article",
    "directory":   "submit a listing to this directory",
    "association": "benchmark the guidance; align QC's content (do not pitch — they list no providers)",
    "government":  "cite as an authoritative source; align QC's content (do not pitch)",
    "guide":       "benchmark the coverage; answer what this guide answers (do not pitch)",
    "competitor":  "build an equivalent QC page — a rival won this query with their own page",
    "editorial":   "benchmark the coverage (page genre unconfirmed — do not assert its contents)",
    "community":   "authentic community presence only — no manufactured or anonymous posts",
    "video":       "consider video content if strategically relevant",
}


def get_topic_cited_urls(segment, days=None, limit=_TOP_N_URLS):
    """
    Top external (non-QC) URLs cited in this segment, ranked by citation count -
    the pages AI reaches for on this topic. QC-owned URLs are excluded here;
    the whole point of Tab 1 is what's cited *instead of* QC.
    """
    date_m = _date_filter(days).replace("AND created_at", "AND m.created_at")
    from api.queries.recommendation_signals import _segment_clause_params
    seg_clause, seg_params = _segment_clause_params(segment)

    qc_not_ilike = " AND ".join(
        f"cited_url NOT ILIKE '%%{tok}%%'" for tok in QC_DOMAIN_TOKENS
    )
    query = f"""
        WITH expanded AS (
            SELECT unnest(m.citations) as cited_url
            FROM mention_responses m
            JOIN questions q ON q.id = m.question_id
            WHERE 1=1 {date_m} {seg_clause}
        )
        SELECT cited_url, COUNT(*) as count
        FROM expanded
        WHERE {qc_not_ilike}
        GROUP BY cited_url
        ORDER BY count DESC
        LIMIT %s;
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, seg_params + [limit])
            rows = cur.fetchall()
    return [{"url": r[0], "count": r[1]} for r in rows]


def get_question_cited_urls(question_id, days=None, limit=_TOP_N_URLS):
    """
    Top external (non-QC) URLs cited for ONE question, ranked by citation
    count - the per-question mirror of get_topic_cited_urls, for the question
    router (plan §5.3). Question grain matters: winning domains barely overlap
    between questions in the same topic (Jaccard 0.05-0.19), so a topic-level
    winner set blends unrelated pages.
    """
    date_m = _date_filter(days).replace("AND created_at", "AND m.created_at")
    qc_not_ilike = " AND ".join(
        f"cited_url NOT ILIKE '%%{tok}%%'" for tok in QC_DOMAIN_TOKENS
    )
    query = f"""
        WITH expanded AS (
            SELECT unnest(m.citations) as cited_url
            FROM mention_responses m
            WHERE m.question_id = %s {date_m}
        )
        SELECT cited_url, COUNT(*) as count
        FROM expanded
        WHERE {qc_not_ilike}
        GROUP BY cited_url
        ORDER BY count DESC
        LIMIT %s;
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, [question_id, limit])
            rows = cur.fetchall()
    return [{"url": r[0], "count": r[1]} for r in rows]


def _qc_citation_count(segment, days=None):
    """How many times QC's own domains are cited in this segment (usually low)."""
    date_m = _date_filter(days).replace("AND created_at", "AND m.created_at")
    from api.queries.recommendation_signals import _segment_clause_params
    seg_clause, seg_params = _segment_clause_params(segment)
    qc_ilike = " OR ".join(f"cited_url ILIKE '%%{t}%%'" for t in QC_DOMAIN_TOKENS)
    query = f"""
        WITH expanded AS (
            SELECT unnest(m.citations) as cited_url
            FROM mention_responses m
            JOIN questions q ON q.id = m.question_id
            WHERE 1=1 {date_m} {seg_clause}
        )
        SELECT COUNT(*) FROM expanded WHERE {qc_ilike};
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, seg_params)
            return cur.fetchone()[0]


def strategic_evidence(segment, days=None, school=None, limit=5):
    """
    Truthful citation evidence for a Tab 1 card (no fetching, all Tier A): the
    top external domains AI cites for this segment with counts, plus QC's own
    citation count. Falls back to the rec's SCHOOL when the segment value isn't
    a real topic (the LLM sometimes puts a specific phrase there), so a card
    almost always has evidence. Returns None only when nothing matches.
    """
    from collections import Counter
    from api.queries.page_facts import _domain_of

    scope_label = (segment or {}).get("value")
    urls = get_topic_cited_urls(segment, days, limit=60)
    if not urls and school and school not in ("both", "Both", "All", "General"):
        segment = {"dimension": "school", "value": school}
        scope_label = school
        urls = get_topic_cited_urls(segment, days, limit=60)
    if not urls:
        return None

    dom = Counter()
    for u in urls:
        dom[_domain_of(u["url"])] += u["count"]
    cited = [{"domain": d, "count": c} for d, c in dom.most_common(limit)]
    return {
        "cited": cited,
        "qc_citations": _qc_citation_count(segment, days),
        "max_count": cited[0]["count"] if cited else 0,
        "scope_label": scope_label,
    }


def _coarse(count, total):
    """Coarse prevalence label — avoids false precision on small N."""
    if total == 0:
        return "none"
    frac = count / total
    if frac >= 0.6:
        return "most"
    if frac >= 0.3:
        return "some"
    return "few"


def analyze_strategic_topic(segment, days=None, min_pages=3):
    """
    Full Tab 1 analysis for one topic segment: classify the cited pages and
    roll them into the three evidence types + a build-vs-earn verdict.

    Returns a dict shaped for the evidence bundle. `sufficient` is False when
    too few pages could be fetched/classified to trust the composition — the
    caller should fall back to a generic strategic rec rather than assert a mix.
    """
    cited = get_topic_cited_urls(segment, days)
    counts = {c["url"]: c["count"] for c in cited}
    facts = get_pages_facts([c["url"] for c in cited])

    # Attach citation counts; split fetched-with-content from domain-only.
    for f in facts:
        f["citation_count"] = counts.get(f["url"], 0)
    classified = [f for f in facts if f.get("page_type")]

    # ── evidence type 1: specific opportunities (verified inclusion gates) ──
    opportunities = [
        {
            "url": f["url"],
            "page_type": f["page_type"],
            "citation_count": f["citation_count"],
            "lists_competitors": sorted(f.get("brand_mentions", {}).keys()),
            "action": PAGE_TYPE_ACTIONS.get(f["page_type"]),
        }
        for f in classified if inclusion_opportunity(f)
    ]
    opportunities.sort(key=lambda o: -o["citation_count"])

    # ── evidence type 2: authority patterns (benchmark, don't pitch) ──
    authorities = [
        {
            "url": f["url"],
            "page_type": f["page_type"],
            "citation_count": f["citation_count"],
            "title": f.get("title"),
            "action": PAGE_TYPE_ACTIONS.get(f["page_type"]),
        }
        for f in classified
        if f["page_type"] in ("association", "government", "guide")
    ]
    authorities.sort(key=lambda a: -a["citation_count"])

    # ── evidence type 3: ecosystem composition (no single URL) ──
    total = len(classified)
    type_counts = {}
    for f in classified:
        type_counts[f["page_type"]] = type_counts.get(f["page_type"], 0) + 1
    commercial = sum(type_counts.get(t, 0) for t in _COMMERCIAL_TYPES)
    impartial  = sum(type_counts.get(t, 0) for t in _IMPARTIAL_TYPES)
    community  = type_counts.get("community", 0)
    ecosystem = {
        "pages_classified":   total,
        "type_breakdown":     type_counts,
        "community_share":    _coarse(community, total),
        "impartial_share":    _coarse(impartial, total),
        "commercial_share":   _coarse(commercial, total),
    }

    # ── build vs earn (Gap A vs Gap B) ──
    if commercial == 0 and impartial == 0:
        gap, gap_reason = "unknown", "no competitor or third-party pages classified"
    elif commercial >= impartial:
        gap = "build"
        gap_reason = ("competitors won this topic with their own pages "
                      f"({commercial} competitor-owned vs {impartial} impartial third-party) — "
                      "an owned QC page can win")
    else:
        gap = "earn"
        gap_reason = ("impartial third-party pages dominate "
                      f"({impartial} impartial vs {commercial} competitor-owned) — earn placement / "
                      "build educational (not sales) content rather than a self-serving page")

    return {
        "segment":                segment,
        "sufficient":             total >= min_pages,
        "pages_considered":       len(cited),
        "pages_classified":       total,
        "gap":                    gap,
        "gap_reason":             gap_reason,
        "specific_opportunities": opportunities,
        "authority_patterns":     authorities,
        "ecosystem":              ecosystem,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Phase 6a: the wrong-genre gray area
# ─────────────────────────────────────────────────────────────────────────────

def genre_check(segment, qc_url, days=None):
    """
    QC HAS a page for this intent - but is it the KIND of page engines reward?
    Compares the genre of QC's covered page (course/sales vs how-to/guide)
    against the dominant genre of the pages AI actually cites for the topic.
    Returns a mismatch dict (see page_facts.genre_gap) or None. All inputs are
    cached page_facts; ambiguity returns None, never a guessed mismatch.
    """
    if not qc_url:
        return None
    cited = get_topic_cited_urls(segment, days)
    if not cited:
        return None
    winner_facts = get_pages_facts([c["url"] for c in cited])
    qc_facts = get_page_facts(qc_url)
    return genre_gap(qc_facts, winner_facts)


def coverage_genre_mismatches(segment, coverage, days=None):
    """
    genre_check over every covered intent of a coverage diagnosis. A covered
    intent with a mismatch effectively upgrades its verdict from `have_page`
    to `have_wrong_genre`: the existing page can still be tuned (Tab 2), but
    the leveraged move is building the genre engines reward (Tab 1).
    """
    mismatches = []
    for cov in (coverage or {}).get("covered", []):
        try:
            gm = genre_check(segment, cov.get("qc_url"), days)
        except Exception as e:
            logger.warning(f"genre_check failed for {cov.get('qc_url')}: {e}")
            continue
        if gm:
            mismatches.append({
                "intent": cov.get("intent"),
                "school": cov.get("school"),
                "qc_url": cov.get("qc_url"),
                **gm,
            })
    return mismatches


# ─────────────────────────────────────────────────────────────────────────────
# Phase 6b: analysis -> recommendations (deterministic; the LLM authors none
# of this - the mirror of tab2_scorecard.scorecard_to_recommendation)
# ─────────────────────────────────────────────────────────────────────────────

def _evidence_text(topic, ev):
    """Truthful Tier-A citation summary: exactly which domains, how often, vs QC."""
    if not ev:
        return f"QC earns few or no citations for '{topic}'."
    domains = ", ".join(f"{c['domain']} ({c['count']}x)" for c in ev["cited"][:5])
    return (f"Engines cite {domains} for '{topic}'; "
            f"QC's own pages earn {ev['qc_citations']} citation(s) there.")


def strategy_to_recommendations(analysis, days=None, max_per_topic=3, rival_gap=None):
    """
    Turn one topic's strategic analysis into Tab 1 recommendations. Every field
    is derived from verified analysis facts - inclusion gates, build-vs-earn
    composition, genre mismatches, per-intent coverage - so a Tab 1 rec cannot
    assert anything page_facts didn't verify. Ordered most-specific-first:
    verified opportunities > wrong-genre builds > gap builds > ecosystem.

    rival_gap (optional, Phase 7 item 3): {"competitor", "domains": [{domain,
    count}]} - domains vouching for the lead rival in this topic but never for
    QC. Enriches the build/earn rec with concrete citation targets, so
    competitive intel becomes the WHERE of an existing rec, not its own card.
    """
    segment = analysis["segment"]
    topic = segment.get("value")
    coverage = analysis.get("coverage") or {}
    try:
        ev = strategic_evidence(segment, days)
    except Exception as e:
        logger.warning(f"strategic_evidence failed for {segment}: {e}")
        ev = None
    ev_text = _evidence_text(topic, ev)
    recs = []

    def _rec(**kw):
        base = {
            "priority": "medium", "school": None, "segment": segment,
            "metric_impact": "mention_rate", "expected_direction": 1,
            "expected_magnitude": None, "effort": "M", "confidence": 0.6,
            "detail": {"evidence": ev} if ev else None,
        }
        base.update(kw)
        return base

    # 1. Verified inclusion opportunities - page read, provably lists rivals, no QC.
    for opp in analysis["specific_opportunities"][:2]:
        rivals = ", ".join(opp["lists_competitors"][:5])
        is_directory = opp["page_type"] == "directory"
        recs.append(_rec(
            problem=(f"{opp['url']} is cited {opp['citation_count']}x by engines for '{topic}', "
                     f"and the page lists {rivals} - but never mentions QC."),
            action=(f"Submit a QC listing to this directory ({opp['url']})." if is_directory else
                    f"Pitch QC for inclusion in this comparison article ({opp['url']}) - "
                    f"it already lists {rivals}."),
            priority="high" if opp["citation_count"] >= 3 else "medium",
            evidence=(f"{opp['url']} cited {opp['citation_count']}x for '{topic}'; page content "
                      f"verified to list {rivals} and never mention QC. {ev_text}"),
            action_type="citation" if is_directory else "outreach",
            target=opp["url"],
            metric_impact="citation_rate",
            effort="S",
            confidence=0.8,
            detail={"evidence": ev, "opportunity": opp} if ev else {"opportunity": opp},
        ))

    # 2. Wrong-genre builds - QC has a page for the intent, but not the KIND
    #    engines reward (the course-page-vs-how-to-guide gray area).
    for gm in (analysis.get("genre_mismatches") or [])[:1]:
        if gm["winner_genre"] == "informational":
            action = (f"Build a standalone informational asset answering '{gm['intent']}' - a "
                      f"how-to / career guide, not another course page - and link it to the "
                      f"existing page ({gm['qc_url']}). Keep tuning that page separately.")
        else:
            action = (f"Build a dedicated course/program page for '{gm['intent']}' - the existing "
                      f"informational page ({gm['qc_url']}) serves a different intent than the "
                      f"commercial pages engines cite here. Link the two.")
        recs.append(_rec(
            problem=(f"QC's page for '{gm['intent']}' ({gm['qc_url']}) is a {gm['qc_genre']} page, "
                     f"but {gm['winners_with_genre']}/{gm['winners_classified']} genre-classifiable "
                     f"pages engines cite for '{topic}' are {gm['winner_genre']} - engines reward a "
                     f"kind of page QC doesn't have here."),
            action=action,
            priority="high",
            school=gm.get("school") or school_for_url(gm["qc_url"]),
            evidence=(f"{ev_text} QC's covered page is {gm['qc_genre']} (from its schema/pricing/"
                      f"heading signals); {gm['winners_with_genre']} of {gm['winners_classified']} "
                      f"classifiable cited pages are {gm['winner_genre']}."),
            action_type="content",
            target=gm["intent"],
            effort="L",
            detail={"evidence": ev, "genre_mismatch": gm} if ev else {"genre_mismatch": gm},
        ))

    # 3. Missing-page build/earn, from the composition verdict. Only when the
    #    composition is trustworthy (enough classified pages).
    if analysis["sufficient"] and coverage.get("uncovered"):
        intent0 = coverage["uncovered"][0]
        benchmark = ", ".join(a["url"] for a in analysis["authority_patterns"][:2])
        if analysis["gap"] == "build":
            action = f"Create a QC page answering '{intent0['intent']}'."
            if benchmark:
                action += f" Benchmark depth and coverage against the cited authorities: {benchmark}."
            confidence = 0.6
        else:  # earn - or unknown composition, which still supports educational content
            action = (f"Build educational content (a guide/hub, not a sales page) answering "
                      f"'{intent0['intent']}' - impartial third-party pages win this topic, so a "
                      f"self-serving page won't take the neutral slot.")
            if benchmark:
                action += f" Model it on what engines already cite: {benchmark}."
            confidence = 0.55
        evidence = ev_text + f" {analysis['gap_reason'][:1].upper()}{analysis['gap_reason'][1:]}."
        detail = {"evidence": ev} if ev else {}
        if rival_gap and rival_gap.get("domains"):
            gap_names = ", ".join(f"{d['domain']} ({d['count']}x)" for d in rival_gap["domains"][:5])
            evidence += (f" Domains vouching for {rival_gap['competitor']} on this topic but never "
                         f"for QC: {gap_names} - priority targets for citations once the page exists.")
            detail["rival_backed_domains"] = rival_gap
        recs.append(_rec(
            problem=(f"QC has no page for '{intent0['intent']}' (topic '{topic}'), and "
                     f"{analysis['gap_reason']}."),
            action=action,
            priority="high" if (ev and ev.get("max_count", 0) >= 3) else "medium",
            school=intent0.get("school"),
            evidence=evidence,
            action_type="content",
            target=intent0["intent"],
            effort="L",
            confidence=confidence,
            detail=detail or None,
        ))

    # 4. Ecosystem strategy - only when community dominates what's cited.
    eco = analysis["ecosystem"]
    if analysis["sufficient"] and eco.get("community_share") == "most":
        recs.append(_rec(
            problem=(f"Community sources dominate what engines cite for '{topic}' "
                     f"({eco['type_breakdown'].get('community', 0)} of "
                     f"{eco['pages_classified']} classified pages)."),
            action=("Establish an authentic, named QC presence in the communities engines cite "
                    "(expert answers, AMAs) - no manufactured or anonymous posts."),
            evidence=(f"{ev_text} {eco['type_breakdown'].get('community', 0)}/"
                      f"{eco['pages_classified']} classified cited pages are community threads."),
            action_type="strategy",
            target=topic,
            metric_impact="visibility_score",
            confidence=0.5,
        ))

    return recs[:max_per_topic]


def build_tab1_recommendations(days=None, max_topics=2):
    """
    Deterministic Tab 1 recs for the weakest topics with a strategic gap - the
    mirror of tab2_scorecard.build_tab2_recommendations: same weak-topic
    selection, opposite coverage branch (uncovered intents, or covered intents
    whose page is the wrong genre). Bounded to keep fetch/LLM cost small.
    """
    from api.queries.recommendation_signals import (
        get_weakest_topics, get_momentum, get_citation_contrast,
    )
    from api.queries.sitemap_coverage import diagnose_coverage

    lead = None
    try:
        top_competitors = get_momentum(days).get("top_competitors") or []
        lead = top_competitors[0]["name"] if top_competitors else None
    except Exception as e:
        logger.warning(f"Lead-competitor lookup failed: {e}")

    out, topics_used = [], 0
    topics = [t for t in get_weakest_topics(days, limit=20)
              if t.get("kind") == "mention" and (t.get("sample_n") or 0) >= 5]
    for t in topics:
        if topics_used >= max_topics:
            break
        seg = {"dimension": "topic", "value": t["topic"]}
        coverage = diagnose_coverage(seg)
        mismatches = coverage_genre_mismatches(seg, coverage, days)
        if not coverage.get("uncovered") and not mismatches:
            continue
        rival_gap = None
        if lead:
            try:
                contrast = get_citation_contrast(seg, lead, days)
                domains = contrast.get("domains_citing_rival_not_qc") or []
                if domains:
                    rival_gap = {"competitor": lead, "domains": domains[:5]}
            except Exception as e:
                logger.warning(f"Citation contrast failed for {t['topic']}: {e}")
        try:
            analysis = analyze_strategic_topic(seg, days)
            analysis["coverage"] = coverage
            analysis["genre_mismatches"] = mismatches
            recs = strategy_to_recommendations(analysis, days, rival_gap=rival_gap)
        except Exception as e:
            logger.warning(f"Tab 1 strategy failed for {t['topic']}: {e}")
            recs = []
        if recs:
            out.extend(recs)
            topics_used += 1
    return out


if __name__ == "__main__":
    import json, sys
    seg = {"dimension": "topic", "value": sys.argv[1] if len(sys.argv) > 1 else "How to Become"}
    print(json.dumps(analyze_strategic_topic(seg), indent=2, default=str))
