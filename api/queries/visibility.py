from api.db import get_connection, _date_filter

def get_mention_rate_by_engine(days=None):
    filter_clause = _date_filter(days)
    query = f"""
        SELECT DATE(created_at) as day, engine,
            AVG(CASE WHEN qc_mentioned THEN 1 ELSE 0 END) as mention_rate
        FROM mention_responses
        WHERE 1=1 {filter_clause}
        GROUP BY day, engine
        ORDER BY day;
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query)
            rows = cur.fetchall()
    pivoted = {}
    for day, engine, rate in rows:
        day_str = str(day)
        if day_str not in pivoted:
            pivoted[day_str] = {"day": day_str}
        pivoted[day_str][engine] = round(float(rate) * 100, 1)
    return sorted(pivoted.values(), key=lambda x: x["day"])

def get_mention_rate_by_category(days=None):
    filter_clause = _date_filter(days)
    query = f"""
        SELECT q.question_type as category,
            AVG(CASE WHEN m.qc_mentioned THEN 1 ELSE 0 END) as mention_rate
        FROM mention_responses m
        JOIN questions q ON q.id = m.question_id
        WHERE 1=1 {filter_clause.replace('AND created_at', 'AND m.created_at')}
        GROUP BY q.question_type
        ORDER BY mention_rate DESC;
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query)
            rows = cur.fetchall()
    return [{"category": r[0], "mention_rate": round(float(r[1]) * 100, 1)} for r in rows]

def get_mention_rate_by_school(days=None):
    filter_clause = _date_filter(days)
    query = f"""
        SELECT q.school,
            AVG(CASE WHEN m.qc_mentioned THEN 1 ELSE 0 END) as mention_rate
        FROM mention_responses m
        JOIN questions q ON q.id = m.question_id
        WHERE q.school IS NOT NULL
        {filter_clause.replace('AND created_at', 'AND m.created_at')}
        GROUP BY q.school
        ORDER BY mention_rate DESC;
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query)
            rows = cur.fetchall()
    return [{"school": r[0], "mention_rate": round(float(r[1]) * 100, 1)} for r in rows]