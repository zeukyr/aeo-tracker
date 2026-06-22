from api.db import get_connection, _date_filter

def get_summary(days=None):
    filter_clause = _date_filter(days)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT AVG(CASE WHEN qc_mentioned THEN 1 ELSE 0 END)
                FROM mention_responses WHERE 1=1 {filter_clause};
            """)
            mention_rate = cur.fetchone()[0]

            cur.execute(f"""
                SELECT AVG(CASE WHEN qc_cited THEN 1 ELSE 0 END)
                FROM mention_responses WHERE 1=1 {filter_clause};
            """)
            citation_rate = cur.fetchone()[0]

            cur.execute(f"""
                SELECT AVG(CASE WHEN qc_sentiment = 'positive' THEN 1 ELSE 0 END)
                FROM sentiment_responses WHERE 1=1 {filter_clause};
            """)
            positive_rate = cur.fetchone()[0]

            cur.execute(f"""
                WITH combined AS (
                    SELECT unnest(competitors) as competitor
                    FROM mention_responses WHERE 1=1 {filter_clause}
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
                FROM mention_responses WHERE 1=1 {filter_clause}
                GROUP BY engine
                ORDER BY rate DESC
                LIMIT 1;
            """)
            best_engine_row = cur.fetchone()
            best_engine = best_engine_row[0] if best_engine_row else None

    return {
        "mention_rate": round(float(mention_rate) * 100, 1) if mention_rate else 0,
        "citation_rate": round(float(citation_rate) * 100, 1) if citation_rate else 0,
        "positive_sentiment_rate": round(float(positive_rate) * 100, 1) if positive_rate else 0,
        "top_competitor": top_competitor,
        "best_engine": best_engine
    }