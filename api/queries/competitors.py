from api.db import get_connection, _date_filter

def get_top_competitors_by_school(days=None):
    filter_clause = _date_filter(days)
    query = f"""
        SELECT
            b.brand_name as competitor,
            q.school,
            COUNT(*) as count
        FROM mention_response_brands b
        JOIN mention_responses m ON m.id = b.mention_response_id
        JOIN questions q ON q.id = m.question_id
        WHERE b.brand_type = 'competitor' {filter_clause.replace('AND created_at', 'AND m.created_at')}
        GROUP BY b.brand_name, q.school
        ORDER BY q.school, count DESC
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query)
            rows = cur.fetchall()
    return [{"competitor": r[0], "school": r[1], "count": r[2]} for r in rows]


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