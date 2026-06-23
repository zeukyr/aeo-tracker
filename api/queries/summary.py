from api.db import get_connection, _date_filter, _prev_date_filter

def get_summary(days=None):
    filter_curr = _date_filter(days)
    filter_prev = _prev_date_filter(days)

    def fetch_rate(cur, column, table, filter_clause):
        cur.execute(f"""
            SELECT AVG(CASE WHEN {column} THEN 1 ELSE 0 END)
            FROM {table} WHERE 1=1 {filter_clause};
        """)
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

            cur.execute(f"""
                WITH combined AS (
                    SELECT unnest(competitors) as competitor
                    FROM mention_responses WHERE 1=1 {filter_curr}
                )
                SELECT competitor, COUNT(*) as count
                FROM combined
                GROUP BY competitor
                ORDER BY count DESC
                LIMIT 1;
            """)
            top_competitor_row = cur.fetchone()
            top_competitor = top_competitor_row[0] if top_competitor_row else None

            cur.execute(f"""
                SELECT engine, AVG(CASE WHEN qc_mentioned THEN 1 ELSE 0 END) as rate
                FROM mention_responses WHERE 1=1 {filter_curr}
                GROUP BY engine
                ORDER BY rate DESC
                LIMIT 1;
            """)
            best_engine_row = cur.fetchone()
            best_engine = best_engine_row[0] if best_engine_row else None

    return {
        "mention_rate": round(mention_curr * 100, 1) if mention_curr else 0,
        "mention_rate_diff": diff(mention_curr, mention_prev),
        "citation_rate": round(citation_curr * 100, 1) if citation_curr else 0,
        "citation_rate_diff": diff(citation_curr, citation_prev),
        "positive_sentiment_rate": round(sentiment_curr * 100, 1) if sentiment_curr else 0,
        "positive_sentiment_diff": diff(sentiment_curr, sentiment_prev),
        "top_competitor": top_competitor,
        "best_engine": best_engine
    }