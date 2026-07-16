"""
Cited-URL queries: which external pages AI engines reach for, and the
citation-evidence rollups built on them.

  - get_question_cited_urls: one question's top non-QC cited URLs - the
    "winners" the question router classifies before picking a branch.
  - get_topic_cited_urls: the topic-segment variant, used by the scorecard's
    standalone fallback path and by strategic_evidence.
  - strategic_evidence: truthful Tier-A citation evidence for a card (top
    external domains with counts vs QC's own citation count) - attached to
    generic recs by batch generation.

(Formerly the live remainder of tab1_strategy.py; the retired two-tab
"Strategic Growth" builders were deleted when the question router took over
their rec families at question grain.)
"""

import re
from collections import defaultdict

from src.parsing.urls import merge_url_counts, normalize_url
from api.db import get_connection, _date_filter, _school_clause_params
from api.queries.page_facts import QC_DOMAIN_TOKENS

# How many of the top cited URLs to consider per question/topic. Bounded:
# keeps the fetch/LLM cost per segment small and the evidence readable.
_TOP_N_URLS = 8


def get_topic_cited_urls(segment, days=None, limit=_TOP_N_URLS):
    """
    Top external (non-QC) URLs cited in this segment, ranked by citation count -
    the pages AI reaches for on this topic. QC-owned URLs are excluded here;
    the whole point is what's cited *instead of* QC.

    URLs are normalized (tracking params stripped etc.) and re-merged AFTER
    the SQL group-by, so ?utm_source variants of one page count as one page -
    hence no SQL LIMIT: the merge must see every variant.
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
        GROUP BY cited_url;
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, seg_params)
            rows = cur.fetchall()
    return merge_url_counts([{"url": r[0], "count": r[1]} for r in rows])[:limit]


def get_question_cited_urls(question_id, days=None, limit=_TOP_N_URLS):
    """
    Top external (non-QC) URLs cited for ONE question, ranked by citation
    count - the per-question mirror of get_topic_cited_urls, for the question
    router (plan §5.3). Question grain matters: winning domains barely overlap
    between questions in the same topic (Jaccard 0.05-0.19), so a topic-level
    winner set blends unrelated pages.

    Normalized + re-merged after the SQL group-by (see get_topic_cited_urls) -
    the dominance vote must not split one page across its tracking variants.
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
        GROUP BY cited_url;
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, [question_id])
            rows = cur.fetchall()
    return merge_url_counts([{"url": r[0], "count": r[1]} for r in rows])[:limit]


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
    Truthful citation evidence for a strategic card (no fetching, all Tier A):
    the top external domains AI cites for this segment with counts, plus QC's
    own citation count. Falls back to the rec's SCHOOL when the segment value
    isn't a real topic (the LLM sometimes puts a specific phrase there), so a
    card almost always has evidence. Returns None only when nothing matches.
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


_SUBREDDIT_RE = re.compile(r"reddit\.com/r/([^/]+)", re.I)


def _subreddit_of(url):
    m = _SUBREDDIT_RE.search(url)
    return m.group(1).lower() if m else None


def get_reddit_targets(days=None, school=None, limit=15):
    """
    Reddit-specific outreach targets for the Outreach & Earn tab's Reddit
    spotlight: every reddit.com URL cited across BOTH mention and sentiment
    responses, split into the two plays that actually differ on Reddit -

      - reputation: the thread surfaced answering a credibility/concern
        question (sentiment_responses) - QC's name is already in the
        conversation, so the play is reply/correct-the-record.
      - discovery: the thread only surfaced answering course/career
        questions (mention_responses) - QC isn't part of the conversation
        yet, so the play is answer-authentically-and-get-cited.

    A thread with any reputation citations is classed "reputation" even if
    it also has discovery ones - correcting the record outranks discovery
    once QC's name is already attached to the thread. Also rolls up by
    subreddit so the panel can lead with WHERE to show up, not just which
    threads already worked.
    """
    date_m = _date_filter(days).replace("AND created_at", "AND m.created_at")
    date_s = _date_filter(days).replace("AND created_at", "AND s.created_at")
    school_clause_m, params_m = _school_clause_params(school)
    school_clause_s, params_s = _school_clause_params(school)

    query = f"""
        WITH combined AS (
            SELECT unnest(m.citations) as cited_url, m.question_id, 'discovery' as source
            FROM mention_responses m
            JOIN questions q ON q.id = m.question_id
            WHERE 1=1 {date_m} {school_clause_m}
            UNION ALL
            SELECT unnest(s.citations) as cited_url, s.question_id, 'reputation' as source
            FROM sentiment_responses s
            JOIN questions q ON q.id = s.question_id
            WHERE 1=1 {date_s} {school_clause_s}
        )
        SELECT cited_url, source, question_id
        FROM combined
        WHERE cited_url ILIKE '%%reddit.com%%';
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params_m + params_s)
            rows = cur.fetchall()

    if not rows:
        return {"threads": [], "subreddits": []}

    threads = defaultdict(lambda: {"reputation_count": 0, "discovery_count": 0, "question_ids": set()})
    for cited_url, source, question_id in rows:
        t = threads[normalize_url(cited_url)]
        t[f"{source}_count"] += 1
        t["question_ids"].add(question_id)

    all_qids = {qid for t in threads.values() for qid in t["question_ids"]}
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, question FROM questions WHERE id = ANY(%s::uuid[])",
                ([str(q) for q in all_qids],),
            )
            qmap = {r[0]: r[1] for r in cur.fetchall()}

    thread_rows = []
    for url, t in threads.items():
        subreddit = _subreddit_of(url)
        thread_rows.append({
            "url": url,
            "subreddit": subreddit,
            "total_count": t["reputation_count"] + t["discovery_count"],
            "reputation_count": t["reputation_count"],
            "discovery_count": t["discovery_count"],
            "category": "reputation" if t["reputation_count"] > 0 else "discovery",
            "is_qc_subreddit": bool(subreddit and subreddit.startswith("qc")),
            "questions": sorted({qmap[q] for q in t["question_ids"] if q in qmap})[:4],
        })
    thread_rows.sort(key=lambda r: -r["total_count"])

    sub_rollup = defaultdict(lambda: {"total_count": 0, "reputation_count": 0, "discovery_count": 0, "thread_count": 0})
    for t in thread_rows:
        if not t["subreddit"]:
            continue
        s = sub_rollup[t["subreddit"]]
        s["total_count"] += t["total_count"]
        s["reputation_count"] += t["reputation_count"]
        s["discovery_count"] += t["discovery_count"]
        s["thread_count"] += 1
    subreddit_rows = sorted(
        ({"subreddit": k, **v} for k, v in sub_rollup.items()),
        key=lambda r: -r["total_count"],
    )

    return {"threads": thread_rows[:limit], "subreddits": subreddit_rows[:10]}
