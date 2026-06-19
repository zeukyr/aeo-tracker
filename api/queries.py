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
        SELECT 
            q.question_type as category,
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
        SELECT 
            q.school,
            AVG(CASE WHEN m.qc_mentioned THEN 1 ELSE 0 END) as mention_rate
        FROM mention_responses m
        JOIN questions q ON q.id = m.question_id
        WHERE q.school IS NOT NULL {filter_clause.replace('AND created_at', 'AND m.created_at')}
        GROUP BY q.school
        ORDER BY mention_rate DESC;
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query)
            rows = cur.fetchall()
    return [{"school": r[0], "mention_rate": round(float(r[1]) * 100, 1)} for r in rows]

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

def get_top_competitors(days=None):
    filter_clause = _date_filter(days)
    query = f"""
        WITH combined AS (
            SELECT unnest(competitors) as competitor
            FROM mention_responses
            WHERE 1=1 {filter_clause}
        )
        SELECT competitor, COUNT(*) as count
        FROM combined
        WHERE competitor IS NOT NULL
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

def get_summary(days=None):
    filter_clause_mention = _date_filter(days)
    filter_clause_sentiment = _date_filter(days)

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT AVG(CASE WHEN qc_mentioned THEN 1 ELSE 0 END)
                FROM mention_responses WHERE 1=1 {filter_clause_mention};
            """)
            mention_rate = cur.fetchone()[0]

            cur.execute(f"""
                SELECT 
                    AVG(CASE WHEN qc_sentiment = 'positive' THEN 1 ELSE 0 END)
                FROM sentiment_responses WHERE 1=1 {filter_clause_sentiment};
            """)
            positive_rate = cur.fetchone()[0]

            cur.execute(f"""
                WITH combined AS (
                    SELECT unnest(competitors) as competitor
                    FROM mention_responses WHERE 1=1 {filter_clause_mention}
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
                FROM mention_responses WHERE 1=1 {filter_clause_mention}
                GROUP BY engine
                ORDER BY rate DESC
                LIMIT 1;
            """)
            best_engine_row = cur.fetchone()
            best_engine = best_engine_row[0] if best_engine_row else None

    return {
        "mention_rate": round(float(mention_rate) * 100, 1) if mention_rate else 0,
        "positive_sentiment_rate": round(float(positive_rate) * 100, 1) if positive_rate else 0,
        "top_competitor": top_competitor,
        "best_engine": best_engine
    }

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
    
def get_competitor_win_rate(days=None):
    filter_clause = _date_filter(days)
    query = f"""
        WITH wins AS (
            SELECT 
                competitor_won,
                COUNT(*) as win_count
            FROM sentiment_responses
            WHERE competitor_won IS NOT NULL
            AND competitor_won != 'QC'
            AND competitor_won != 'no_clear_winner'
            {filter_clause}
            GROUP BY competitor_won
        ),
        totals AS (
            SELECT COUNT(*) as total
            FROM sentiment_responses
            WHERE competitor_won IS NOT NULL
            AND competitor_won != 'no_clear_winner'
            {filter_clause}
        )
        SELECT w.competitor_won, ROUND(w.win_count * 100.0 / t.total, 1) as win_rate
        FROM wins w, totals t
        ORDER BY win_rate DESC
        LIMIT 10;
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query)
            rows = cur.fetchall()
    return [{"competitor": r[0], "win_rate": float(r[1])} for r in rows]