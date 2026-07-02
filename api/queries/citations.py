from api.db import get_connection, _date_filter, _school_clause_params

QC_ILIKE = """
    cited_url ILIKE '%%qccareerschool%%'
    OR cited_url ILIKE '%%qcpetstudies%%'
    OR cited_url ILIKE '%%qceventplanning%%'
    OR cited_url ILIKE '%%qcdesignschool%%'
    OR cited_url ILIKE '%%qcmakeupacademy%%'
"""

SOURCE_TYPE_CASE = f"""
    CASE WHEN {QC_ILIKE} THEN 'QC owned' ELSE 'external' END
"""

def get_citations(days=None, school=None):
    filter_clause = _date_filter(days).replace('AND created_at', 'AND m.created_at')
    school_clause, params = _school_clause_params(school)
    query = f"""
        WITH expanded AS (
            SELECT unnest(m.citations) as cited_url
            FROM mention_responses m
            LEFT JOIN questions q ON q.id = m.question_id
            WHERE 1=1 {filter_clause} {school_clause}
        )
        SELECT cited_url, COUNT(*) as count,
            {SOURCE_TYPE_CASE} as source_type
        FROM expanded
        GROUP BY cited_url
        ORDER BY count DESC
        LIMIT 20;
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            rows = cur.fetchall()
    return [{"url": r[0], "count": r[1], "source_type": r[2]} for r in rows]

def get_qc_citations(days=None, school=None):
    filter_clause = _date_filter(days).replace('AND created_at', 'AND m.created_at')
    school_clause, params = _school_clause_params(school)
    query = f"""
        WITH expanded AS (
            SELECT unnest(m.citations) as cited_url
            FROM mention_responses m
            LEFT JOIN questions q ON q.id = m.question_id
            WHERE 1=1 {filter_clause} {school_clause}
        )
        SELECT cited_url, COUNT(*) as count
        FROM expanded
        WHERE {QC_ILIKE}
        GROUP BY cited_url
        ORDER BY count DESC;
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            rows = cur.fetchall()
    return [{"url": r[0], "count": r[1]} for r in rows]

def get_citations_by_school(days=None, school=None):
    filter_clause = _date_filter(days).replace('AND created_at', 'AND m.created_at')
    school_clause, params = _school_clause_params(school)
    query = f"""
        WITH expanded AS (
            SELECT unnest(m.citations) as cited_url, q.school
            FROM mention_responses m
            LEFT JOIN questions q ON q.id = m.question_id
            WHERE q.school IS NOT NULL
            {filter_clause} {school_clause}
        )
        SELECT school, cited_url, COUNT(*) as count,
            {SOURCE_TYPE_CASE} as source_type
        FROM expanded
        GROUP BY school, cited_url
        ORDER BY school, count DESC;
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            rows = cur.fetchall()
    return [{"school": r[0], "url": r[1], "count": r[2], "source_type": r[3]} for r in rows]

def get_sentiment_citations(days=None, school=None):
    filter_clause = _date_filter(days).replace('AND created_at', 'AND s.created_at')
    school_clause, params = _school_clause_params(school)
    query = f"""
        WITH expanded AS (
            SELECT unnest(s.citations) as cited_url, q.school, q.question_type
            FROM sentiment_responses s
            LEFT JOIN questions q ON q.id = s.question_id
            WHERE 1=1 {filter_clause} {school_clause}
        )
        SELECT cited_url, school, question_type, COUNT(*) as count,
            {SOURCE_TYPE_CASE} as source_type
        FROM expanded
        GROUP BY cited_url, school, question_type
        ORDER BY count DESC;
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            rows = cur.fetchall()
    return [{"url": r[0], "school": r[1], "question_type": r[2], "count": r[3], "source_type": r[4]} for r in rows]
