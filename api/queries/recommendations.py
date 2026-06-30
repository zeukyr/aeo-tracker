from api.db import get_connection, _date_filter

def get_competitor_wins(days=None):
    filter_clause = _date_filter(days)
    query = f"""
        SELECT 
            q.question,
            q.school,
            b.brand_name as competitor,
            b.rank_position,
            COUNT(*) as times_seen
        FROM mention_response_brands b
        JOIN mention_responses mr ON mr.id = b.mention_response_id
        JOIN questions q ON q.id = mr.question_id
        WHERE b.brand_type = 'competitor'
        AND mr.qc_mentioned = false
        {filter_clause.replace('AND created_at', 'AND mr.created_at')}
        GROUP BY q.question, q.school, b.brand_name, b.rank_position
        ORDER BY times_seen DESC, b.rank_position ASC
        LIMIT 30;
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query)
            rows = cur.fetchall()
    return [
        {
            "question": r[0],
            "school": r[1],
            "competitor": r[2],
            "rank_position": r[3],
            "times_seen": r[4]
        }
        for r in rows
    ]


def get_qc_buried_positions(days=None):
    filter_clause = _date_filter(days)
    query = f"""
        SELECT 
            q.question,
            q.school,
            mr.engine,
            qcb.rank_position as qc_position,
            COUNT(DISTINCT cb.brand_name) as competitors_ahead
        FROM mention_responses mr
        JOIN questions q ON q.id = mr.question_id
        JOIN mention_response_brands qcb ON qcb.mention_response_id = mr.id AND qcb.brand_type = 'qc'
        LEFT JOIN mention_response_brands cb ON cb.mention_response_id = mr.id 
            AND cb.brand_type = 'competitor' 
            AND cb.rank_position < qcb.rank_position
        WHERE mr.qc_mentioned = true
        {filter_clause.replace('AND created_at', 'AND mr.created_at')}
        GROUP BY q.question, q.school, mr.engine, qcb.rank_position
        HAVING qcb.rank_position > 1
        ORDER BY qcb.rank_position DESC;
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query)
            rows = cur.fetchall()
    return [
        {
            "question": r[0],
            "school": r[1],
            "engine": r[2],
            "qc_position": r[3],
            "competitors_ahead": r[4]
        }
        for r in rows
    ]


def get_citation_gaps(days=None):
    filter_clause = _date_filter(days)
    query = f"""
        SELECT 
            q.school,
            unnest(mr.citations) as cited_url,
            COUNT(*) as citation_count
        FROM mention_responses mr
        JOIN questions q ON q.id = mr.question_id
        WHERE mr.qc_cited = false
        {filter_clause.replace('AND created_at', 'AND mr.created_at')}
        GROUP BY q.school, cited_url
        HAVING COUNT(*) >= 3
        ORDER BY q.school, citation_count DESC;
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query)
            rows = cur.fetchall()
    return [
        {
            "school": r[0],
            "cited_url": r[1],
            "citation_count": r[2]
        }
        for r in rows
    ]


def get_recurring_concerns(days=None):
    filter_clause = _date_filter(days)
    query = f"""
        SELECT 
            q.school,
            unnest(sr.concerns_raised) as concern,
            COUNT(*) as times_raised
        FROM sentiment_responses sr
        JOIN questions q ON q.id = sr.question_id
        WHERE 1=1
        {filter_clause.replace('AND created_at', 'AND sr.created_at')}
        GROUP BY q.school, concern
        ORDER BY times_raised DESC
        LIMIT 20;
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query)
            rows = cur.fetchall()
    return [
        {
            "school": r[0],
            "concern": r[1],
            "times_raised": r[2]
        }
        for r in rows
    ]