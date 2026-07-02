from api.db import get_connection, _date_filter, _school_clause_params

def get_sentiment_distribution(days=None, school=None):
    filter_clause = _date_filter(days).replace('AND created_at', 'AND s.created_at')
    school_clause, params = _school_clause_params(school)
    query = f"""
        SELECT DATE(s.created_at) as day, s.qc_sentiment, COUNT(*) as count
        FROM sentiment_responses s
        LEFT JOIN questions q ON q.id = s.question_id
        WHERE 1=1 {filter_clause} {school_clause}
        GROUP BY day, s.qc_sentiment
        ORDER BY day;
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            rows = cur.fetchall()
    pivoted = {}
    for day, sentiment, count in rows:
        day_str = str(day)
        if day_str not in pivoted:
            pivoted[day_str] = {"day": day_str, "positive": 0, "neutral": 0, "negative": 0}
        if sentiment:
            pivoted[day_str][sentiment] = count
    return sorted(pivoted.values(), key=lambda x: x["day"])

def get_top_concerns(days=None, school=None):
    filter_clause = _date_filter(days).replace('AND created_at', 'AND s.created_at')
    school_clause, params = _school_clause_params(school)
    query = f"""
        WITH expanded AS (
            SELECT unnest(s.concerns_raised) as concern
            FROM sentiment_responses s
            LEFT JOIN questions q ON q.id = s.question_id
            WHERE 1=1 {filter_clause} {school_clause}
        )
        SELECT concern, COUNT(*) as count
        FROM expanded
        GROUP BY concern
        ORDER BY count DESC
        LIMIT 10;
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            rows = cur.fetchall()
    return [{"concern": r[0], "count": r[1]} for r in rows]

def get_top_positives(days=None, school=None):
    filter_clause = _date_filter(days).replace('AND created_at', 'AND s.created_at')
    school_clause, params = _school_clause_params(school)
    query = f"""
        WITH expanded AS (
            SELECT unnest(s.positives_raised) as positive
            FROM sentiment_responses s
            LEFT JOIN questions q ON q.id = s.question_id
            WHERE 1=1 {filter_clause} {school_clause}
        )
        SELECT positive, COUNT(*) as count
        FROM expanded
        GROUP BY positive
        ORDER BY count DESC
        LIMIT 10;
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            rows = cur.fetchall()
    return [{"positive": r[0], "count": r[1]} for r in rows]
