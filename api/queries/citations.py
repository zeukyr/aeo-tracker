from api.db import get_connection, _date_filter

QC_ILIKE = """
    cited_url ILIKE '%qccareerschool%'
    OR cited_url ILIKE '%qcpetstudies%'
    OR cited_url ILIKE '%qceventplanning%'
    OR cited_url ILIKE '%qcdesignschool%'
    OR cited_url ILIKE '%qcmakeupacademy%'
"""

SOURCE_TYPE_CASE = f"""
    CASE WHEN {QC_ILIKE} THEN 'QC owned' ELSE 'external' END
"""

def get_citations(days=None):
    filter_clause = _date_filter(days)
    query = f"""
        WITH expanded AS (
            SELECT unnest(citations) as cited_url
            FROM mention_responses
            WHERE 1=1 {filter_clause}
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
            cur.execute(query)
            rows = cur.fetchall()
    return [{"url": r[0], "count": r[1], "source_type": r[2]} for r in rows]

def get_qc_citations(days=None):
    filter_clause = _date_filter(days)
    query = f"""
        WITH expanded AS (
            SELECT unnest(citations) as cited_url
            FROM mention_responses
            WHERE 1=1 {filter_clause}
        )
        SELECT cited_url, COUNT(*) as count
        FROM expanded
        WHERE {QC_ILIKE}
        GROUP BY cited_url
        ORDER BY count DESC;
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query)
            rows = cur.fetchall()
    return [{"url": r[0], "count": r[1]} for r in rows]

def get_citations_by_school(days=None):
    filter_clause = _date_filter(days)
    query = f"""
        WITH expanded AS (
            SELECT unnest(m.citations) as cited_url, q.school
            FROM mention_responses m
            JOIN questions q ON q.id = m.question_id
            WHERE q.school IS NOT NULL
            {filter_clause.replace('AND created_at', 'AND m.created_at')}
        )
        SELECT school, cited_url, COUNT(*) as count,
            {SOURCE_TYPE_CASE} as source_type
        FROM expanded
        GROUP BY school, cited_url
        ORDER BY school, count DESC;
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query)
            rows = cur.fetchall()
    return [{"school": r[0], "url": r[1], "count": r[2], "source_type": r[3]} for r in rows]

def get_sentiment_citations(days=None):
    filter_clause = _date_filter(days)
    query = f"""
        WITH expanded AS (
            SELECT unnest(s.citations) as cited_url, q.school, q.question_type
            FROM sentiment_responses s
            JOIN questions q ON q.id = s.question_id
            WHERE 1=1 {filter_clause.replace('AND created_at', 'AND s.created_at')}
        )
        SELECT cited_url, school, question_type, COUNT(*) as count,
            {SOURCE_TYPE_CASE} as source_type
        FROM expanded
        GROUP BY cited_url, school, question_type
        ORDER BY count DESC;
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query)
            rows = cur.fetchall()
    return [{"url": r[0], "school": r[1], "question_type": r[2], "count": r[3], "source_type": r[4]} for r in rows]