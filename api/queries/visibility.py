from api.db import get_connection, _date_filter, _school_clause_params

def get_citation_rate_by_engine(days=None, school=None):
    filter_clause = _date_filter(days).replace('AND created_at', 'AND m.created_at')
    school_clause, params = _school_clause_params(school)
    query = f"""
        SELECT DATE(m.created_at) as day, m.engine,
            AVG(CASE WHEN m.qc_cited THEN 1 ELSE 0 END) as citation_rate
        FROM mention_responses m
        LEFT JOIN questions q ON q.id = m.question_id
        WHERE 1=1 {filter_clause} {school_clause}
        GROUP BY day, m.engine
        ORDER BY day;
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            rows = cur.fetchall()
    pivoted = {}
    for day, engine, rate in rows:
        day_str = str(day)
        if day_str not in pivoted:
            pivoted[day_str] = {"day": day_str}
        pivoted[day_str][engine] = round(float(rate) * 100, 1)
    return sorted(pivoted.values(), key=lambda x: x["day"])

def get_citation_rate_by_category(days=None, school=None):
    filter_clause = _date_filter(days).replace('AND created_at', 'AND m.created_at')
    school_clause, params = _school_clause_params(school)
    query = f"""
        SELECT q.question_type as category,
            AVG(CASE WHEN m.qc_cited THEN 1 ELSE 0 END) as citation_rate
        FROM mention_responses m
        LEFT JOIN questions q ON q.id = m.question_id
        WHERE 1=1 {filter_clause} {school_clause}
        GROUP BY q.question_type
        ORDER BY citation_rate DESC;
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            rows = cur.fetchall()
    return [{"category": r[0], "citation_rate": round(float(r[1]) * 100, 1)} for r in rows]

def get_citation_rate_by_school(days=None, school=None):
    filter_clause = _date_filter(days).replace('AND created_at', 'AND m.created_at')
    school_clause, params = _school_clause_params(school)
    query = f"""
        SELECT q.school,
            AVG(CASE WHEN m.qc_cited THEN 1 ELSE 0 END) as citation_rate
        FROM mention_responses m
        LEFT JOIN questions q ON q.id = m.question_id
        WHERE q.school IS NOT NULL
        {filter_clause} {school_clause}
        GROUP BY q.school
        ORDER BY citation_rate DESC;
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            rows = cur.fetchall()
    return [{"school": r[0], "citation_rate": round(float(r[1]) * 100, 1)} for r in rows]

def get_mention_rate_by_engine(days=None, school=None):
    filter_clause = _date_filter(days).replace('AND created_at', 'AND m.created_at')
    school_clause, params = _school_clause_params(school)
    query = f"""
        SELECT DATE(m.created_at) as day, m.engine,
            AVG(CASE WHEN m.qc_mentioned THEN 1 ELSE 0 END) as mention_rate
        FROM mention_responses m
        LEFT JOIN questions q ON q.id = m.question_id
        WHERE 1=1 {filter_clause} {school_clause}
        GROUP BY day, m.engine
        ORDER BY day;
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            rows = cur.fetchall()
    pivoted = {}
    for day, engine, rate in rows:
        day_str = str(day)
        if day_str not in pivoted:
            pivoted[day_str] = {"day": day_str}
        pivoted[day_str][engine] = round(float(rate) * 100, 1)
    return sorted(pivoted.values(), key=lambda x: x["day"])

def get_mention_rate_by_category(days=None, school=None):
    filter_clause = _date_filter(days).replace('AND created_at', 'AND m.created_at')
    school_clause, params = _school_clause_params(school)
    query = f"""
        SELECT q.question_type as category,
            AVG(CASE WHEN m.qc_mentioned THEN 1 ELSE 0 END) as mention_rate
        FROM mention_responses m
        LEFT JOIN questions q ON q.id = m.question_id
        WHERE 1=1 {filter_clause} {school_clause}
        GROUP BY q.question_type
        ORDER BY mention_rate DESC;
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            rows = cur.fetchall()
    return [{"category": r[0], "mention_rate": round(float(r[1]) * 100, 1)} for r in rows]

def get_mention_rate_by_school(days=None, school=None):
    filter_clause = _date_filter(days).replace('AND created_at', 'AND m.created_at')
    school_clause, params = _school_clause_params(school)
    query = f"""
        SELECT q.school,
            AVG(CASE WHEN m.qc_mentioned THEN 1 ELSE 0 END) as mention_rate
        FROM mention_responses m
        LEFT JOIN questions q ON q.id = m.question_id
        WHERE q.school IS NOT NULL
        {filter_clause} {school_clause}
        GROUP BY q.school
        ORDER BY mention_rate DESC;
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            rows = cur.fetchall()
    return [{"school": r[0], "mention_rate": round(float(r[1]) * 100, 1)} for r in rows]
