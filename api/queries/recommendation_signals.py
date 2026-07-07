"""
Phase 1 of the closed-loop recommendation system: richer evidence signals.

Groups the metrics already tracked across the dashboard into four buckets so
the recommendation LLM sees trends, weak segments, competitive "why we lose"
detail, and "what's already working" - not just a snapshot of negatives.

Bucket A - Momentum:        trend direction on the headline KPIs
Bucket B - Segment gaps:    weakest engine / category / school / topic
Bucket C - Competitive intel: existing losses/buried positions + win_reasons
Bucket D - Content leverage: positives, QC citations that work, top domains

Nothing here replaces api/queries/recommendations.py - those four functions
are reused as-is (Bucket C existing signals).
"""

from api.db import get_connection, _date_filter, _school_clause_params
from api.queries.summary import get_summary
from api.queries.visibility import (
    get_mention_rate_by_category,
    get_citation_rate_by_category,
    get_mention_rate_by_school,
    get_citation_rate_by_school,
)
from api.queries.sentiment import get_top_positives
from api.queries.citations import get_qc_citations, QC_ILIKE


# ─────────────────────────────────────────────────────────────────────────────
# Bucket A: Momentum - trend direction on the headline KPIs
# ─────────────────────────────────────────────────────────────────────────────

def get_momentum(days=None, school=None):
    """
    Trims get_summary() down to the fields relevant as recommendation
    evidence: current value + diff for each headline KPI, plus which
    competitor/engine currently leads.
    """
    s = get_summary(days=days, school=school)
    return {
        "mention_rate":            s["mention_rate"],
        "mention_rate_diff":       s["mention_rate_diff"],
        "citation_rate":           s["citation_rate"],
        "citation_rate_diff":      s["citation_rate_diff"],
        "positive_sentiment_rate": s["positive_sentiment_rate"],
        "positive_sentiment_diff": s["positive_sentiment_diff"],
        "avg_rank":                s["avg_rank"],
        "avg_rank_diff":           s["avg_rank_diff"],
        "sov":                     s["sov"],
        "sov_diff":                s["sov_diff"],
        "visibility_score":        s["visibility_score"],
        "visibility_score_diff":   s["visibility_score_diff"],
        "best_engine":             s["best_engine"],
        "top_competitors":         s["top_competitors"],
    }


# ─────────────────────────────────────────────────────────────────────────────
# Bucket B: Segment gaps - weakest engine / category / school / topic
# ─────────────────────────────────────────────────────────────────────────────

def _positive_rate_by(group_col, days=None, school=None):
    """Shared helper: AVG(positive sentiment) grouped by an arbitrary column."""
    filter_clause = _date_filter(days).replace('AND created_at', 'AND s.created_at')
    school_clause, params = _school_clause_params(school)
    query = f"""
        SELECT {group_col} as grp,
            AVG(CASE WHEN s.qc_sentiment = 'positive' THEN 1 ELSE 0 END) as positive_rate,
            COUNT(*) as sample_n
        FROM sentiment_responses s
        LEFT JOIN questions q ON q.id = s.question_id
        WHERE {group_col} IS NOT NULL {filter_clause} {school_clause}
        GROUP BY {group_col};
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            rows = cur.fetchall()
    return {r[0]: {"positive_sentiment_rate": round(float(r[1]) * 100, 1), "sample_n": r[2]} for r in rows}


def _segment_score(row):
    vals = [v for v in (
        row.get("mention_rate"), row.get("citation_rate"), row.get("positive_sentiment_rate")
    ) if v is not None]
    return sum(vals) / len(vals) if vals else 0


def get_weakest_engines(days=None, school=None, limit=10):
    """Per-engine mention/citation/positive-sentiment rates, weakest first."""
    filter_m = _date_filter(days).replace('AND created_at', 'AND m.created_at')
    school_clause, params = _school_clause_params(school)
    query = f"""
        SELECT m.engine,
            AVG(CASE WHEN m.qc_mentioned THEN 1 ELSE 0 END) as mention_rate,
            AVG(CASE WHEN m.qc_cited THEN 1 ELSE 0 END) as citation_rate,
            COUNT(*) as sample_n
        FROM mention_responses m
        LEFT JOIN questions q ON q.id = m.question_id
        WHERE 1=1 {filter_m} {school_clause}
        GROUP BY m.engine;
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            mention_rows = cur.fetchall()

    positive_by_engine = _positive_rate_by("s.engine", days, school)

    engines = {}
    for engine, mention_rate, citation_rate, n in mention_rows:
        engines[engine] = {
            "engine":         engine,
            "mention_rate":   round(float(mention_rate or 0) * 100, 1),
            "citation_rate":  round(float(citation_rate or 0) * 100, 1),
            "mention_sample_n": n,
        }
    for engine, data in positive_by_engine.items():
        engines.setdefault(engine, {"engine": engine})
        engines[engine]["positive_sentiment_rate"] = data["positive_sentiment_rate"]
        engines[engine]["sentiment_sample_n"] = data["sample_n"]

    rows = sorted(engines.values(), key=_segment_score)
    return rows[:limit]


def get_weakest_categories(days=None, school=None, limit=10):
    """Per question_type (course/general/credibility/competition), weakest first."""
    mention  = {r["category"]: r["mention_rate"]  for r in get_mention_rate_by_category(days, school)}
    citation = {r["category"]: r["citation_rate"] for r in get_citation_rate_by_category(days, school)}
    positive = _positive_rate_by("q.question_type", days, school)

    categories = set(mention) | set(citation) | set(positive)
    rows = []
    for cat in categories:
        row = {
            "category":                cat,
            "mention_rate":            mention.get(cat),
            "citation_rate":           citation.get(cat),
            "positive_sentiment_rate": positive.get(cat, {}).get("positive_sentiment_rate"),
        }
        rows.append(row)

    rows.sort(key=_segment_score)
    return rows[:limit]


def get_weakest_schools(days=None, limit=10):
    """Per school/faculty, weakest first. school=None here means 'all schools', not a filter."""
    mention  = {r["school"]: r["mention_rate"]  for r in get_mention_rate_by_school(days)}
    citation = {r["school"]: r["citation_rate"] for r in get_citation_rate_by_school(days)}
    positive = _positive_rate_by("q.school", days, None)

    schools = set(mention) | set(citation) | set(positive)
    rows = []
    for sch in schools:
        row = {
            "school":                  sch,
            "mention_rate":            mention.get(sch),
            "citation_rate":           citation.get(sch),
            "positive_sentiment_rate": positive.get(sch, {}).get("positive_sentiment_rate"),
        }
        rows.append(row)

    rows.sort(key=_segment_score)
    return rows[:limit]


def get_weakest_topics(days=None, school=None, limit=10):
    """
    Per-topic rollup across both mention-kind topics (course/general -> visibility)
    and sentiment-kind topics (credibility/competition -> positive rate).
    Mirrors the split in topics.py but flattened to one aggregate score per topic.
    """
    date_m = _date_filter(days).replace("AND created_at", "AND m.created_at")
    date_s = _date_filter(days).replace("AND created_at", "AND s.created_at")
    school_clause, params = _school_clause_params(school)

    mention_query = f"""
        SELECT COALESCE(q.topic, 'Uncategorized') as topic,
            AVG(CASE WHEN m.qc_mentioned THEN 1 ELSE 0 END) as mention_rate,
            AVG(CASE WHEN m.qc_cited THEN 1 ELSE 0 END) as citation_rate,
            COUNT(*) as sample_n
        FROM mention_responses m
        JOIN questions q ON q.id = m.question_id
        WHERE q.topic IS NOT NULL AND q.question_type IN ('course', 'general')
        {date_m} {school_clause}
        GROUP BY q.topic;
    """
    sentiment_query = f"""
        SELECT COALESCE(q.topic, 'Uncategorized') as topic,
            AVG(CASE WHEN s.qc_sentiment = 'positive' THEN 1 ELSE 0 END) as positive_rate,
            COUNT(*) as sample_n
        FROM sentiment_responses s
        JOIN questions q ON q.id = s.question_id
        WHERE q.topic IS NOT NULL AND q.question_type IN ('credibility', 'competition')
        {date_s} {school_clause}
        GROUP BY q.topic;
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(mention_query, params)
            mention_rows = cur.fetchall()
            cur.execute(sentiment_query, params)
            sentiment_rows = cur.fetchall()

    rows = []
    for topic, mention_rate, citation_rate, n in mention_rows:
        score = round((float(mention_rate or 0) + float(citation_rate or 0)) / 2 * 100, 1)
        rows.append({"topic": topic, "kind": "mention", "score": score, "sample_n": n})

    for topic, positive_rate, n in sentiment_rows:
        rows.append({
            "topic": topic, "kind": "sentiment",
            "score": round(float(positive_rate or 0) * 100, 1), "sample_n": n,
        })

    rows.sort(key=lambda r: r["score"])
    return rows[:limit]


# ─────────────────────────────────────────────────────────────────────────────
# Bucket C: Competitive intel - why we lose, beyond the existing 4 signals
# ─────────────────────────────────────────────────────────────────────────────

def get_win_reasons(days=None, school=None, limit=15):
    """
    Why competitors win head-to-head, aggregated from sentiment_responses.win_reasons.
    Complements get_competitor_wins/get_qc_buried_positions (which show *that* QC
    loses) with *why* - previously-unused column.
    """
    filter_clause = _date_filter(days).replace('AND created_at', 'AND s.created_at')
    school_clause, params = _school_clause_params(school)
    query = f"""
        WITH expanded AS (
            SELECT s.competitor_won, unnest(s.win_reasons) as reason
            FROM sentiment_responses s
            LEFT JOIN questions q ON q.id = s.question_id
            WHERE s.competitor_won IS NOT NULL
            AND s.competitor_won != 'QC'
            AND s.competitor_won != 'no_clear_winner'
            {filter_clause} {school_clause}
        )
        SELECT competitor_won, reason, COUNT(*) as count
        FROM expanded
        GROUP BY competitor_won, reason
        ORDER BY count DESC
        LIMIT %s;
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params + [limit])
            rows = cur.fetchall()
    return [{"competitor": r[0], "reason": r[1], "count": r[2]} for r in rows]


def get_competitive_loss_topics(days=None, min_losses=1):
    """
    {topic: {"losses": n, "competitors": [names]}} - topics where competitors
    appear while QC is invisible. Phase 7 item 3: competitive intel is a
    PRIORITY/ROUTING input for the existing topic recs (boost + targets),
    not its own rec family.
    """
    date_f = _date_filter(days).replace("AND created_at", "AND mr.created_at")
    query = f"""
        SELECT q.topic, COUNT(*) AS losses,
               array_agg(DISTINCT b.brand_name) AS competitors
        FROM mention_response_brands b
        JOIN mention_responses mr ON mr.id = b.mention_response_id
        JOIN questions q ON q.id = mr.question_id
        WHERE b.brand_type = 'competitor' AND mr.qc_mentioned = false
          AND q.topic IS NOT NULL {date_f}
        GROUP BY q.topic
        HAVING COUNT(*) >= %s;
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, [min_losses])
            rows = cur.fetchall()
    return {r[0]: {"losses": r[1], "competitors": r[2][:4]} for r in rows}


def get_qc_verdict_distribution(days=None, school=None):
    """
    Distribution of the qc_verdict column - captured on every sentiment
    response but never surfaced anywhere on the dashboard or in recommendations.
    """
    filter_clause = _date_filter(days).replace('AND created_at', 'AND s.created_at')
    school_clause, params = _school_clause_params(school)
    query = f"""
        SELECT s.qc_verdict, COUNT(*) as count
        FROM sentiment_responses s
        LEFT JOIN questions q ON q.id = s.question_id
        WHERE s.qc_verdict IS NOT NULL {filter_clause} {school_clause}
        GROUP BY s.qc_verdict
        ORDER BY count DESC;
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            rows = cur.fetchall()
    return [{"verdict": r[0], "count": r[1]} for r in rows]


# ─────────────────────────────────────────────────────────────────────────────
# Bucket D: Content leverage - what's already working, worth reinforcing
# ─────────────────────────────────────────────────────────────────────────────
# get_top_positives (sentiment.py) and get_qc_citations (citations.py) are
# reused as-is in build_evidence(); only the domain rollup below is new.

def get_competitor_profile(competitor, days=None, limit=10):
    """
    For a named competitor, surfaces (a) which domains get cited in responses
    where that competitor appears (a proxy for the authority sources backing
    their visibility) and (b) any qualitative win_reasons attributed to them
    in head-to-head sentiment responses. Turns "competitor X wins" into
    "competitor X wins because of Y, backed by these sources" - reverse-
    engineering the gap instead of guessing at it.
    """
    filter_m = _date_filter(days).replace('AND created_at', 'AND m.created_at')
    filter_s = _date_filter(days).replace('AND created_at', 'AND s.created_at')

    domains_query = rf"""
        WITH comp_responses AS (
            SELECT DISTINCT m.id, m.citations
            FROM mention_responses m
            JOIN mention_response_brands b ON b.mention_response_id = m.id
            WHERE b.brand_type = 'competitor' AND b.brand_name = %s
            {filter_m}
        ),
        expanded AS (
            SELECT unnest(citations) as cited_url FROM comp_responses
        ),
        domains AS (
            SELECT regexp_replace(regexp_replace(cited_url, '^https?://(www\.)?', ''), '/.*$', '') as domain
            FROM expanded
        )
        SELECT domain, COUNT(*) as count
        FROM domains
        GROUP BY domain
        ORDER BY count DESC
        LIMIT %s;
    """
    reasons_query = """
        SELECT unnest(s.win_reasons) as reason, COUNT(*) as count
        FROM sentiment_responses s
        WHERE s.competitor_won = %s
        {filter_s}
        GROUP BY reason
        ORDER BY count DESC
        LIMIT %s;
    """.replace("{filter_s}", filter_s)

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(domains_query, [competitor, limit])
            domain_rows = cur.fetchall()
            cur.execute(reasons_query, [competitor, limit])
            reason_rows = cur.fetchall()

    return {
        "competitor":      competitor,
        "cited_domains":   [{"domain": r[0], "count": r[1]} for r in domain_rows],
        "win_reasons":     [{"reason": r[0], "count": r[1]} for r in reason_rows],
    }


def get_top_citation_domains(days=None, school=None, limit=15):
    """
    Rolls up cited URLs to domains (instead of raw URLs) so the LLM sees
    authority *sources* to pursue - review sites, directories, listicles -
    rather than one-off pages.
    """
    filter_clause = _date_filter(days).replace('AND created_at', 'AND m.created_at')
    school_clause, params = _school_clause_params(school)
    query = rf"""
        WITH expanded AS (
            SELECT unnest(m.citations) as cited_url
            FROM mention_responses m
            LEFT JOIN questions q ON q.id = m.question_id
            WHERE 1=1 {filter_clause} {school_clause}
        ),
        domains AS (
            SELECT regexp_replace(regexp_replace(cited_url, '^https?://(www\.)?', ''), '/.*$', '') as domain
            FROM expanded
        )
        SELECT domain, COUNT(*) as count,
            CASE WHEN {QC_ILIKE.replace('cited_url', 'domain')} THEN 'QC owned' ELSE 'external' END as source_type
        FROM domains
        GROUP BY domain
        ORDER BY count DESC
        LIMIT %s;
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params + [limit])
            rows = cur.fetchall()
    return [{"domain": r[0], "count": r[1], "source_type": r[2]} for r in rows]


def _segment_clause_params(segment):
    """
    WHERE fragment scoping a query to one recommendation segment
    ({dimension, value}). Assumes `questions q` and `mention_responses m`
    are in scope. dimension 'global' (or None) means no extra filter.
    """
    dimension = (segment or {}).get("dimension")
    value = (segment or {}).get("value")
    if dimension == "topic":
        return "AND q.topic = %s", [value]
    if dimension == "category":
        return "AND q.question_type = %s", [value]
    if dimension == "school":
        if value == "General":
            return "AND q.school IS NULL", []
        return "AND q.school = %s", [value]
    if dimension == "engine":
        return "AND m.engine = %s", [value]
    return "", []


_DOMAIN_QC_ILIKE = QC_ILIKE.replace("cited_url", "domain")


def get_citation_contrast(segment, competitor=None, days=None, limit=10):
    """
    Per-segment citation contrast: who engines actually cite in this segment,
    split into (a) domains backing responses that mention QC — QC-owned vs
    third-party — and (b) domains backing responses where `competitor`
    appears. The difference is the actionable gap list: domains that vouch
    for the rival here but never for QC.

    This is the concrete, quotable evidence the recommendation LLM needs
    ("engines cite eventbrite.com 5x, QC has 2 owned citations and zero
    third-party") instead of "competitors' citations are higher".
    """
    date_m = _date_filter(days).replace("AND created_at", "AND m.created_at")
    seg_clause, seg_params = _segment_clause_params(segment)

    qc_query = rf"""
        WITH expanded AS (
            SELECT unnest(m.citations) as cited_url
            FROM mention_responses m
            JOIN questions q ON q.id = m.question_id
            WHERE m.qc_mentioned = true {date_m} {seg_clause}
        ),
        domains AS (
            SELECT regexp_replace(regexp_replace(cited_url, '^https?://(www\.)?', ''), '/.*$', '') as domain
            FROM expanded
        )
        SELECT domain, COUNT(*) as count,
            CASE WHEN {_DOMAIN_QC_ILIKE} THEN 'QC owned' ELSE 'external' END as source_type
        FROM domains
        GROUP BY domain
        ORDER BY count DESC;
    """

    competitor_query = rf"""
        WITH comp_responses AS (
            SELECT DISTINCT m.id, m.citations
            FROM mention_responses m
            JOIN questions q ON q.id = m.question_id
            JOIN mention_response_brands b ON b.mention_response_id = m.id
            WHERE b.brand_type = 'competitor' AND b.brand_name = %s
            {date_m} {seg_clause}
        ),
        expanded AS (
            SELECT unnest(citations) as cited_url FROM comp_responses
        ),
        domains AS (
            SELECT regexp_replace(regexp_replace(cited_url, '^https?://(www\.)?', ''), '/.*$', '') as domain
            FROM expanded
        )
        SELECT domain, COUNT(*) as count
        FROM domains
        GROUP BY domain
        ORDER BY count DESC;
    """

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(qc_query, seg_params)
            qc_rows = cur.fetchall()
            competitor_rows = []
            if competitor:
                cur.execute(competitor_query, [competitor] + seg_params)
                competitor_rows = cur.fetchall()

    qc_owned    = [{"domain": r[0], "count": r[1]} for r in qc_rows if r[2] == "QC owned"]
    qc_external = [{"domain": r[0], "count": r[1]} for r in qc_rows if r[2] == "external"]
    qc_domains  = {r[0] for r in qc_rows}

    competitor_citations = [{"domain": r[0], "count": r[1]} for r in competitor_rows]
    gap = [
        c for c in competitor_citations
        if c["domain"] not in qc_domains
        and not any(qc in c["domain"] for qc in (
            "qccareerschool", "qcpetstudies", "qceventplanning",
            "qcdesignschool", "qcmakeupacademy",
        ))
    ]

    # Totals/flags are computed over the full sets; the lists themselves are
    # capped so the evidence bundle stays token-bounded.
    return {
        "segment":                     segment,
        "competitor":                  competitor,
        "qc_external_citations":       qc_external[:limit],
        "qc_owned_citations":          qc_owned[:limit],
        "qc_owned_only":               bool(qc_owned) and not qc_external,
        "qc_third_party_count":        sum(c["count"] for c in qc_external),
        "competitor_citations":        competitor_citations[:limit],
        "domains_citing_rival_not_qc": gap[:limit],
    }


# ─────────────────────────────────────────────────────────────────────────────
# Health summary - deterministic "what's going well / needs work" bullets
# for the Recommendations page header. No LLM call: built purely from the
# signals above so it always matches the live KPI numbers and updates
# instantly with the period/school filter.
# ─────────────────────────────────────────────────────────────────────────────

_MIN_SEGMENT_SAMPLE = 5  # ignore segments too small to be a meaningful signal

_KPI_LABELS = {
    "mention_rate":            ("Mention rate", "%"),
    "citation_rate":           ("Citation rate", "%"),
    "positive_sentiment_rate": ("Positive sentiment", "%"),
    "sov":                     ("Share of voice", "%"),
    "visibility_score":        ("Visibility score", ""),
}


def _segment_sample_n(row):
    return row.get("mention_sample_n") or row.get("sentiment_sample_n") or row.get("sample_n") or 0


def _weakest_segment_bullet(rows, key, label):
    """rows are already sorted weakest-first; skip low-sample noise."""
    eligible = [r for r in rows if _segment_sample_n(r) >= _MIN_SEGMENT_SAMPLE]
    if not eligible:
        return None
    row = eligible[0]
    score = row.get("score")
    if score is None:
        vals = [v for v in (row.get("mention_rate"), row.get("citation_rate"), row.get("positive_sentiment_rate")) if v is not None]
        score = round(sum(vals) / len(vals), 1) if vals else 0
    n = _segment_sample_n(row)
    return {
        "text": f"{row[key]} is your weakest {label} — {score} avg score over {n} responses",
        "magnitude": 100 - score,
    }


def get_health_summary(days=None, school=None, limit=4):
    """
    Returns {"going_well": [{"text": ...}], "needs_work": [{"text": ...}]},
    each capped at `limit` and ranked by magnitude of the underlying signal.
    """
    momentum           = get_momentum(days, school)
    weakest_engines    = get_weakest_engines(days, school, limit=5)
    weakest_categories = get_weakest_categories(days, school, limit=5)
    weakest_schools    = get_weakest_schools(days, limit=5)
    weakest_topics     = get_weakest_topics(days, school, limit=5)
    qc_citations       = get_qc_citations(days, school)

    good, bad = [], []

    for metric, (label, unit) in _KPI_LABELS.items():
        value = momentum.get(metric)
        diff = momentum.get(f"{metric}_diff")
        if value is None or not diff:
            continue
        arrow = "↑" if diff > 0 else "↓"
        text = f"{label} {value}{unit} {arrow}{abs(diff)}pts vs previous period"
        (good if diff > 0 else bad).append({"text": text, "magnitude": abs(diff)})

    # avg_rank is inverted: a lower number is better.
    avg_rank, avg_rank_diff = momentum.get("avg_rank"), momentum.get("avg_rank_diff")
    if avg_rank is not None and avg_rank_diff:
        improved = avg_rank_diff < 0
        arrow = "↓" if improved else "↑"
        text = f"Average rank {avg_rank} {arrow}{abs(avg_rank_diff)} vs previous period"
        (good if improved else bad).append({"text": text, "magnitude": abs(avg_rank_diff)})

    if momentum.get("best_engine"):
        good.append({"text": f"{momentum['best_engine'].title()} is your strongest engine", "magnitude": 0.5})

    if qc_citations:
        top = qc_citations[0]
        good.append({
            "text": f"QC already earns citations on {top['url']} ({top['count']}x)",
            "magnitude": 0.5,
        })

    for rows, key, label in (
        (weakest_engines,    "engine",   "engine"),
        (weakest_topics,     "topic",    "topic"),
        (weakest_schools,    "school",   "school"),
        (weakest_categories, "category", "category"),
    ):
        bullet = _weakest_segment_bullet(rows, key, label)
        if bullet:
            bad.append(bullet)

    top_competitors = momentum.get("top_competitors") or []
    if top_competitors:
        c = top_competitors[0]
        bad.append({
            "text": f"{c['name']} leads share of voice at {c['mention_rate']}%",
            "magnitude": c["mention_rate"],
        })

    good.sort(key=lambda x: -x["magnitude"])
    bad.sort(key=lambda x: -x["magnitude"])

    return {
        "going_well": [{"text": g["text"]} for g in good[:limit]],
        "needs_work": [{"text": b["text"]} for b in bad[:limit]],
    }
