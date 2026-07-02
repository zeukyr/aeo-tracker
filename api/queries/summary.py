from api.db import get_connection, _date_filter, _prev_date_filter

def _school_clause_params(school):
    return ("AND q.school = %s" if school else ""), ([school] if school else [])

def fetch_avg_rank(cur, filter_clause, school=None):
    school_clause, params = _school_clause_params(school)
    cur.execute(f"""
        SELECT AVG(m.qc_mention_order)
        FROM mention_responses m
        LEFT JOIN questions q ON q.id = m.question_id
        WHERE m.qc_mentioned = TRUE
        AND m.qc_mention_order IS NOT NULL
        {filter_clause.replace("created_at", "m.created_at")} {school_clause};
    """, params)
    row = cur.fetchone()[0]
    return float(row) if row else None

def fetch_sov(cur, filter_clause, school=None):
    school_clause, params = _school_clause_params(school)
    cur.execute(f"""
        SELECT
            SUM(CASE WHEN b.brand_type = 'qc' THEN 1 ELSE 0 END) AS qc_mentions,
            SUM(CASE WHEN b.brand_type = 'competitor' THEN 1 ELSE 0 END) AS competitor_mentions
        FROM mention_response_brands b
        JOIN mention_responses m
            ON b.mention_response_id = m.id
        LEFT JOIN questions q ON q.id = m.question_id
        WHERE 1=1 {filter_clause.replace("created_at", "m.created_at")} {school_clause};
    """, params)
    row = cur.fetchone()
    qc_mentions = row[0] or 0
    competitor_mentions = row[1] or 0

    total = qc_mentions + competitor_mentions
    if total == 0:
        return None

    return round((qc_mentions / total) * 100, 1)

def fetch_visibility_score(cur, filter_clause, school=None):
    school_clause, params = _school_clause_params(school)
    cur.execute(f"""
        WITH link_scores AS (
            SELECT
                mention_response_id,
                MAX(
                    CASE
                        WHEN is_qc_internal AND is_inline THEN 100
                        WHEN is_qc AND NOT is_qc_internal AND is_inline THEN 70
                        WHEN is_qc_internal AND NOT is_inline THEN 30
                        WHEN is_qc AND NOT is_qc_internal AND NOT is_inline THEN 15
                        ELSE 0
                    END
                ) AS link_score
            FROM mention_response_links
            GROUP BY mention_response_id
        )
        SELECT AVG(
            (CASE WHEN m.qc_mentioned THEN 100 ELSE 0 END) * 0.40
            + (CASE
                WHEN m.qc_mention_order = 1 THEN 100
                WHEN m.qc_mention_order = 2 THEN 75
                WHEN m.qc_mention_order = 3 THEN 50
                WHEN m.qc_mention_order >= 4 THEN 25
                WHEN m.qc_mentioned THEN 25
                ELSE 0
              END) * 0.45
            + COALESCE(ls.link_score, 0) * 0.15
        )
        FROM mention_responses m
        LEFT JOIN questions q ON q.id = m.question_id
        LEFT JOIN link_scores ls ON ls.mention_response_id = m.id
        WHERE 1=1 {filter_clause.replace("created_at", "m.created_at")} {school_clause};
    """, params)
    row = cur.fetchone()[0]
    return round(float(row), 1) if row is not None else None

def fetch_competitor_mention_counts(cur, filter_clause, school=None):
    school_clause, params = _school_clause_params(school)
    cur.execute(f"""
        SELECT b.brand_name, COUNT(DISTINCT b.mention_response_id) as mentions
        FROM mention_response_brands b
        JOIN mention_responses m ON m.id = b.mention_response_id
        LEFT JOIN questions q ON q.id = m.question_id
        WHERE b.brand_type = 'competitor' {filter_clause.replace("created_at", "m.created_at")} {school_clause}
        GROUP BY b.brand_name;
    """, params)
    return {row[0]: row[1] for row in cur.fetchall()}

def fetch_total_responses(cur, filter_clause, school=None):
    school_clause, params = _school_clause_params(school)
    cur.execute(f"""
        SELECT COUNT(*)
        FROM mention_responses m
        LEFT JOIN questions q ON q.id = m.question_id
        WHERE 1=1 {filter_clause.replace("created_at", "m.created_at")} {school_clause};
    """, params)
    return cur.fetchone()[0] or 0

def fetch_top_competitors(cur, filter_curr, filter_prev, limit=5, school=None):
    curr_counts = fetch_competitor_mention_counts(cur, filter_curr, school)
    prev_counts = fetch_competitor_mention_counts(cur, filter_prev, school)
    total_curr = fetch_total_responses(cur, filter_curr, school)
    total_prev = fetch_total_responses(cur, filter_prev, school)

    top_names = sorted(curr_counts, key=curr_counts.get, reverse=True)[:limit]

    competitors = []
    for name in top_names:
        rate_curr = round(curr_counts[name] / total_curr * 100, 1) if total_curr else 0
        rate_prev = round(prev_counts.get(name, 0) / total_prev * 100, 1) if total_prev else None
        competitors.append({
            "name": name,
            "mention_rate": rate_curr,
            "diff": round(rate_curr - rate_prev, 1) if rate_prev is not None else None
        })
    return competitors

def rank_diff(curr, prev):
    if curr is None or prev is None:
        return None
    return round((prev - curr) * 100, 1)

def sov_diff(curr, prev):
    if curr is None or prev is None:
        return None
    return round(curr - prev, 1)

def visibility_score_diff(curr, prev):
    if curr is None or prev is None:
        return None
    return round(curr - prev, 1)

def get_summary(days=None, school=None):
    filter_curr = _date_filter(days)
    filter_prev = _prev_date_filter(days)
    school_clause, school_params = _school_clause_params(school)

    def fetch_rate(cur, column, table, filter_clause):
        cur.execute(f"""
            SELECT AVG(CASE WHEN {column} THEN 1 ELSE 0 END)
            FROM {table} t
            LEFT JOIN questions q ON q.id = t.question_id
            WHERE 1=1 {filter_clause.replace("created_at", "t.created_at")} {school_clause};
        """, school_params)
        row = cur.fetchone()[0]
        return float(row) if row else None

    def diff(curr, prev):
        if curr is None or prev is None:
            return None
        return round((curr - prev) * 100, 1)

    with get_connection() as conn:
        with conn.cursor() as cur:
            mention_curr = fetch_rate(cur, "qc_mentioned", "mention_responses", filter_curr)
            mention_prev = fetch_rate(cur, "qc_mentioned", "mention_responses", filter_prev)

            citation_curr = fetch_rate(cur, "qc_cited", "mention_responses", filter_curr)
            citation_prev = fetch_rate(cur, "qc_cited", "mention_responses", filter_prev)

            sentiment_curr = fetch_rate(cur, "qc_sentiment = 'positive'", "sentiment_responses", filter_curr)
            sentiment_prev = fetch_rate(cur, "qc_sentiment = 'positive'", "sentiment_responses", filter_prev)

            rank_curr = fetch_avg_rank(cur, filter_curr, school)
            rank_prev = fetch_avg_rank(cur, filter_prev, school)

            sov_curr = fetch_sov(cur, filter_curr, school)
            sov_prev = fetch_sov(cur, filter_prev, school)

            visibility_curr = fetch_visibility_score(cur, filter_curr, school)
            visibility_prev = fetch_visibility_score(cur, filter_prev, school)

            cur.execute(f"""
                SELECT b.brand_name, COUNT(*) as count
                FROM mention_response_brands b
                JOIN mention_responses m ON m.id = b.mention_response_id
                LEFT JOIN questions q ON q.id = m.question_id
                WHERE b.brand_type = 'competitor' {filter_curr.replace("created_at", "m.created_at")} {school_clause}
                GROUP BY b.brand_name
                ORDER BY count DESC
                LIMIT 1;
            """, school_params)
            top_competitor_row = cur.fetchone()
            top_competitor = top_competitor_row[0] if top_competitor_row else None

            cur.execute(f"""
                SELECT m.engine, AVG(CASE WHEN m.qc_mentioned THEN 1 ELSE 0 END) as rate
                FROM mention_responses m
                LEFT JOIN questions q ON q.id = m.question_id
                WHERE 1=1 {filter_curr.replace("created_at", "m.created_at")} {school_clause}
                GROUP BY m.engine
                ORDER BY rate DESC
                LIMIT 1;
            """, school_params)
            best_engine_row = cur.fetchone()
            best_engine = best_engine_row[0] if best_engine_row else None

            top_competitors = fetch_top_competitors(cur, filter_curr, filter_prev, school=school)

    return {
        "mention_rate": round(mention_curr * 100, 1) if mention_curr else 0,
        "mention_rate_diff": diff(mention_curr, mention_prev),
        "citation_rate": round(citation_curr * 100, 1) if citation_curr else 0,
        "citation_rate_diff": diff(citation_curr, citation_prev),
        "positive_sentiment_rate": round(sentiment_curr * 100, 1) if sentiment_curr else 0,
        "positive_sentiment_diff": diff(sentiment_curr, sentiment_prev),
        "avg_rank": round(rank_curr, 2) if rank_curr else None,
        "avg_rank_diff": rank_diff(rank_curr, rank_prev),
        "sov": sov_curr,
        "sov_diff": sov_diff(sov_curr, sov_prev),
        "visibility_score": visibility_curr,
        "visibility_score_diff": visibility_score_diff(visibility_curr, visibility_prev),
        "top_competitor": top_competitor,
        "top_competitors": top_competitors,
        "best_engine": best_engine
    }
