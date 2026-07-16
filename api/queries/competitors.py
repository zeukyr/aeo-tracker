from api.db import get_connection, _date_filter, _school_clause_params
from src.parsing.brands import canonicalize

def get_top_competitors_by_school(days=None, school=None):
    filter_clause = _date_filter(days).replace('AND created_at', 'AND m.created_at')
    school_clause, params = _school_clause_params(school)
    query = f"""
        SELECT
            COALESCE(b.canonical_name, b.brand_name) as competitor,
            q.school,
            COUNT(DISTINCT m.id) as count
        FROM mention_response_brands b
        JOIN mention_responses m ON m.id = b.mention_response_id
        LEFT JOIN questions q ON q.id = m.question_id
        WHERE b.brand_type = 'competitor' {filter_clause} {school_clause}
        GROUP BY competitor, q.school
        ORDER BY q.school, count DESC
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            rows = cur.fetchall()
    return [{"competitor": r[0], "school": r[1], "count": r[2]} for r in rows]


def get_competitor_win_rate(days=None, school=None):
    filter_clause = _date_filter(days).replace('AND created_at', 'AND s.created_at')
    school_clause, params = _school_clause_params(school)
    query = f"""
        SELECT s.competitor_won, COUNT(*) as wins
        FROM sentiment_responses s
        LEFT JOIN questions q ON q.id = s.question_id
        WHERE s.competitor_won IS NOT NULL
        AND s.competitor_won != 'QC'
        AND s.competitor_won != 'no_clear_winner'
        {filter_clause} {school_clause}
        GROUP BY s.competitor_won;
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            rows = cur.fetchall()
    # competitor_won is the LLM's free-form name; merge spelling variants
    # through the registry before computing shares.
    wins = {}
    for name, count in rows:
        canonical = canonicalize(name)
        wins[canonical] = wins.get(canonical, 0) + count
    total = sum(wins.values())
    ranked = sorted(wins.items(), key=lambda kv: kv[1], reverse=True)[:10]
    return [{"competitor": name, "win_rate": round(count * 100.0 / total, 1)} for name, count in ranked]
