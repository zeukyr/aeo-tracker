import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

def get_connection():
    return psycopg2.connect(os.getenv("SUPABASE_DB_URL"))

def _date_filter(days):
    if days:
        return f"AND created_at >= now() - interval '{int(days)} days'"
    return ""

def get_mention_rate_by_engine(days=None):
    filter_clause = _date_filter(days)
    query = f"""
        SELECT 
            DATE(created_at) as day,
            engine,
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
    return [{"day": str(r[0]), "engine": r[1], "mention_rate": float(r[2])} for r in rows]

def get_sentiment_distribution(days=None):
    filter_clause = _date_filter(days)
    query = f"""
        SELECT 
            DATE(created_at) as day,
            qc_sentiment,
            COUNT(*) as count
        FROM sentiment_responses
        WHERE 1=1 {filter_clause}
        GROUP BY day, qc_sentiment
        ORDER BY day;
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query)
            rows = cur.fetchall()
    return [{"day": str(r[0]), "sentiment": r[1], "count": r[2]} for r in rows]

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

def get_top_competitors(days=None):
    filter_clause_mention = _date_filter(days)
    filter_clause_sentiment = _date_filter(days)
    query = f"""
        WITH combined AS (
            SELECT unnest(competitors) as competitor
            FROM mention_responses
            WHERE 1=1 {filter_clause_mention}
            UNION ALL
            SELECT unnest(competitors) as competitor
            FROM sentiment_responses
            WHERE 1=1 {filter_clause_sentiment}
        )
        SELECT competitor, COUNT(*) as count
        FROM combined
        GROUP BY competitor
        ORDER BY count DESC
        LIMIT 10;
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query)
            rows = cur.fetchall()
    return [{"competitor": r[0], "count": r[1]} for r in rows]

def get_citations(days=None):
    filter_clause = _date_filter(days)
    query = f"""
        WITH expanded AS (
            SELECT unnest(citations) as cited_url
            FROM mention_responses
            WHERE 1=1 {filter_clause}
        )
        SELECT 
            cited_url,
            COUNT(*) as count,
            CASE 
                WHEN cited_url ILIKE '%qccareerschool%' 
                  OR cited_url ILIKE '%qcpetstudies%' 
                  OR cited_url ILIKE '%qceventplanning%' 
                THEN 'QC owned'
                ELSE 'external'
            END as source_type
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