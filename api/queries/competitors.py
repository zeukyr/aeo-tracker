from api.db import get_connection, _date_filter

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

def get_competitor_win_rate(days=None):
    filter_clause = _date_filter(days)
    query = f"""
        SELECT competitor_won,
            COUNT(*) as wins,
            ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 1) as win_rate
        FROM sentiment_responses
        WHERE competitor_won IS NOT NULL
        AND competitor_won != 'QC'
        AND competitor_won != 'no_clear_winner'
        {filter_clause}
        GROUP BY competitor_won
        ORDER BY wins DESC
        LIMIT 10;
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query)
            rows = cur.fetchall()
    return [{"competitor": r[0], "win_rate": float(r[2])} for r in rows]