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

The LLM downstream fills in details within these templates; it does not invent
the action or assert page contents it hasn't been shown.
"""

from api.db import get_connection, _date_filter
from api.queries.page_facts import (
    get_pages_facts,
    inclusion_opportunity,
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
                      f"({commercial} commercial vs {impartial} impartial) — an owned QC page can win")
    else:
        gap = "earn"
        gap_reason = ("impartial third-party pages dominate "
                      f"({impartial} impartial vs {commercial} commercial) — earn placement / build "
                      "educational (not sales) content rather than a self-serving page")

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


if __name__ == "__main__":
    import json, sys
    seg = {"dimension": "topic", "value": sys.argv[1] if len(sys.argv) > 1 else "How to Become"}
    print(json.dumps(analyze_strategic_topic(seg), indent=2, default=str))
