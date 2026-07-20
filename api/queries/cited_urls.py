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

import os
import re
import json
from collections import defaultdict
from datetime import datetime, timezone

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


_CHANNELS_PATH = os.path.join(os.path.dirname(__file__), "..", "knowledge", "outreach_channels.json")
_participation_strategy_cache = None


def _load_participation_strategy():
    """The reddit.com "how to participate" playbook (reputation/discovery
    step lists) from the outreach-channels knowledge artifact - {} if the
    file or the field is missing."""
    global _participation_strategy_cache
    if _participation_strategy_cache is None:
        try:
            with open(_CHANNELS_PATH, "r", encoding="utf-8") as f:
                channels = json.load(f)
            _participation_strategy_cache = (
                channels.get("domains", {}).get("reddit.com", {}).get("participation_strategy") or {}
            )
        except (OSError, ValueError):
            _participation_strategy_cache = {}
    return _participation_strategy_cache


_restricted_subreddits_cache = None


def _load_restricted_subreddits():
    """Subreddits with a confirmed self-promotion ban (rule text + the actual
    mechanism, e.g. a weekly promo thread) from outreach_channels.json's
    reddit.com entry - {} if the file/field is missing. Found by outreach
    attempts hitting the rule, not guessed - see the _comment in
    outreach_channels.json for how to add one."""
    global _restricted_subreddits_cache
    if _restricted_subreddits_cache is None:
        try:
            with open(_CHANNELS_PATH, "r", encoding="utf-8") as f:
                channels = json.load(f)
            raw = channels.get("domains", {}).get("reddit.com", {}).get("restricted_subreddits") or {}
        except (OSError, ValueError):
            raw = {}
        _restricted_subreddits_cache = {k.lower(): v for k, v in raw.items()}
    return _restricted_subreddits_cache


_POST_ID_RE = re.compile(r"reddit\.com/(?:r/[^/]+/)?comments/([a-z0-9]+)", re.I)


def _post_id_of(url):
    m = _POST_ID_RE.search(url)
    return m.group(1).lower() if m else None


def _load_thread_statuses(post_ids):
    """User-marked status ('dead'/'open' + a reason) for these Reddit post
    IDs, from the reddit_thread_status table (migration 007) - {} entries
    mean unmarked. DB-backed (not a JSON knowledge artifact) so a mark made
    in the dashboard's "Archived / against rules" control feeds back into
    get_reddit_targets()'s ranking on the very next request - Reddit blocks
    this server's anonymous .json lookups (403 even with a browser UA), so
    archived/rule-blocked status can only come from a human confirming it."""
    post_ids = [p for p in dict.fromkeys(post_ids) if p]
    if not post_ids:
        return {}
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT post_id, status, reason FROM reddit_thread_status WHERE post_id = ANY(%s)",
                (post_ids,),
            )
            return {r[0]: {"status": r[1], "reason": r[2]} for r in cur.fetchall()}


def set_reddit_thread_status(post_id, url, subreddit, status, reason=None):
    """Upsert one thread's user-marked status - called by the dashboard's
    per-thread "mark as dead/open" control. `status` must be 'dead' or
    'open' (matches the table's CHECK constraint); 'open' un-marks a thread
    previously marked dead."""
    if status not in ("dead", "open"):
        raise ValueError(f"invalid reddit thread status: {status!r}")
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO reddit_thread_status (post_id, url, subreddit, status, reason, marked_at)
                VALUES (%s, %s, %s, %s, %s, now())
                ON CONFLICT (post_id) DO UPDATE SET
                    url = EXCLUDED.url, subreddit = EXCLUDED.subreddit,
                    status = EXCLUDED.status, reason = EXCLUDED.reason, marked_at = now()
                """,
                (post_id, url, subreddit, status, reason),
            )
        conn.commit()
    finally:
        conn.close()


_RECENCY_HALF_LIFE_DAYS = 90


def _recency_score(total_count, last_cited_at):
    """Citation count decayed by how long it's been since AI last cited this
    thread (half-life 90 days) - so a thread cited heavily only in the
    distant past no longer automatically outranks one cited less but
    recently. Raw total_count rewards age (citations accumulate forever),
    which is exactly why the highest-ranked "discover" threads kept turning
    out archived - the ranking itself was biased toward old threads."""
    if not last_cited_at:
        return 0.0
    if last_cited_at.tzinfo is None:
        last_cited_at = last_cited_at.replace(tzinfo=timezone.utc)
    age_days = (datetime.now(timezone.utc) - last_cited_at).total_seconds() / 86400
    return total_count * (0.5 ** (max(age_days, 0) / _RECENCY_HALF_LIFE_DAYS))


def get_reddit_targets(days=None, school=None, limit=None):
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

    Two actionability checks run before ranking, both learned from real
    outreach attempts turning up dead leads (see _load_restricted_subreddits
    / _load_thread_statuses): a thread in a subreddit with a confirmed
    self-promo ban is flagged `restricted` (static registry); a thread the
    dashboard's "mark as dead" control was used on is flagged `dead`
    (user-marked, DB-backed - reddit_thread_status table, migration 007).
    Neither is dropped (this panel is
    deliberately comprehensive/unfiltered - see RedditSpotlight.jsx), but
    actionable threads are ranked first via `_recency_score` (see there for
    why raw total_count isn't used for the primary sort).

    `limit=None` (the default) returns every matching thread - "comprehensive"
    per the panel's own design intent means no hidden top-N cutoff. Pass a
    limit explicitly for callers that want one.
    """
    date_m = _date_filter(days).replace("AND created_at", "AND m.created_at")
    date_s = _date_filter(days).replace("AND created_at", "AND s.created_at")
    school_clause_m, params_m = _school_clause_params(school)
    school_clause_s, params_s = _school_clause_params(school)

    query = f"""
        WITH combined AS (
            SELECT unnest(m.citations) as cited_url, m.question_id, 'discovery' as source, m.created_at as cited_at
            FROM mention_responses m
            JOIN questions q ON q.id = m.question_id
            WHERE 1=1 {date_m} {school_clause_m}
            UNION ALL
            SELECT unnest(s.citations) as cited_url, s.question_id, 'reputation' as source, s.created_at as cited_at
            FROM sentiment_responses s
            JOIN questions q ON q.id = s.question_id
            WHERE 1=1 {date_s} {school_clause_s}
        )
        SELECT cited_url, source, question_id, cited_at
        FROM combined
        WHERE cited_url ILIKE '%%reddit.com%%';
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params_m + params_s)
            rows = cur.fetchall()

    if not rows:
        return {"threads": [], "subreddits": []}

    threads = defaultdict(lambda: {
        "reputation_count": 0, "discovery_count": 0, "question_ids": set(), "last_cited_at": None,
    })
    for cited_url, source, question_id, cited_at in rows:
        t = threads[normalize_url(cited_url)]
        t[f"{source}_count"] += 1
        t["question_ids"].add(question_id)
        if cited_at and (t["last_cited_at"] is None or cited_at > t["last_cited_at"]):
            t["last_cited_at"] = cited_at

    all_qids = {qid for t in threads.values() for qid in t["question_ids"]}
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, question FROM questions WHERE id = ANY(%s::uuid[])",
                ([str(q) for q in all_qids],),
            )
            qmap = {r[0]: r[1] for r in cur.fetchall()}

    restricted_subs = _load_restricted_subreddits()
    post_ids_by_url = {url: _post_id_of(url) for url in threads}
    thread_statuses = _load_thread_statuses(post_ids_by_url.values())

    thread_rows = []
    for url, t in threads.items():
        subreddit = _subreddit_of(url)
        post_id = post_ids_by_url[url]
        total_count = t["reputation_count"] + t["discovery_count"]
        restriction = restricted_subs.get(subreddit) if subreddit else None
        marked = thread_statuses.get(post_id) if post_id else None
        is_dead = bool(marked and marked["status"] == "dead")
        thread_rows.append({
            "url": url,
            "post_id": post_id,
            "subreddit": subreddit,
            "total_count": total_count,
            "reputation_count": t["reputation_count"],
            "discovery_count": t["discovery_count"],
            "category": "reputation" if t["reputation_count"] > 0 else "discovery",
            "is_qc_subreddit": bool(subreddit and subreddit.startswith("qc")),
            "questions": sorted({qmap[q] for q in t["question_ids"] if q in qmap})[:4],
            "last_cited_at": t["last_cited_at"].isoformat() if t["last_cited_at"] else None,
            "restricted": restriction is not None,
            "restriction_note": restriction.get("rule") if restriction else None,
            "restriction_mechanism": restriction.get("mechanism") if restriction else None,
            "dead": is_dead,
            "dead_reason": marked.get("reason") if is_dead else None,
            "actionable": restriction is None and not is_dead,
            "_recency_score": _recency_score(total_count, t["last_cited_at"]),
        })
    thread_rows.sort(key=lambda r: (not r["actionable"], -r["_recency_score"]))
    for r in thread_rows:
        del r["_recency_score"]

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

    return {
        "threads": thread_rows if limit is None else thread_rows[:limit],
        "subreddits": subreddit_rows[:10],
        "strategy": _load_participation_strategy(),
    }
