from api.db import get_connection, _date_filter

def get_sentiment_distribution(days=None):
    filter_clause = _date_filter(days)
    query = f"""
        SELECT DATE(created_at) as day, qc_sentiment, COUNT(*) as count
        FROM sentiment_responses
        WHERE 1=1 {filter_clause}
        GROUP BY day, qc_sentiment
        ORDER BY day;
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query)
            rows = cur.fetchall()
    pivoted = {}
    for day, sentiment, count in rows:
        day_str = str(day)
        if day_str not in pivoted:
            pivoted[day_str] = {"day": day_str, "positive": 0, "neutral": 0, "negative": 0}
        if sentiment:
            pivoted[day_str][sentiment] = count
    return sorted(pivoted.values(), key=lambda x: x["day"])

def get_top_concerns(days=None):
    filter_clause = _date_filter(days)
    query = f"""
        WITH expanded AS (
            SELECT unnest(concerns_raised) as concern
            FROM sentiment_responses
            WHERE 1=1 {filter_clause}
        )
        SELECT concern, COUNT(*) as count
        FROM expanded
        GROUP BY concern
        ORDER BY count DESC
        LIMIT 10;
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query)
            rows = cur.fetchall()
    return [{"concern": r[0], "count": r[1]} for r in rows]

def get_top_positives(days=None):
    filter_clause = _date_filter(days)
    query = f"""
        WITH expanded AS (
            SELECT unnest(positives_raised) as positive
            FROM sentiment_responses
            WHERE 1=1 {filter_clause}
        )
        SELECT positive, COUNT(*) as count
        FROM expanded
        GROUP BY positive
        ORDER BY count DESC
        LIMIT 10;
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query)
            rows = cur.fetchall()
    return [{"positive": r[0], "count": r[1]} for r in rows]