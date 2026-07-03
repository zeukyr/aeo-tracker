from api.db import get_connection, _date_filter, _school_clause_params

def get_top_competitors_by_school(days=None, school=None):
    filter_clause = _date_filter(days).replace('AND created_at', 'AND m.created_at')
    school_clause, params = _school_clause_params(school)
    query = f"""
        SELECT
            b.brand_name as competitor,
            q.school,
            COUNT(*) as count
        FROM mention_response_brands b
        JOIN mention_responses m ON m.id = b.mention_response_id
        LEFT JOIN questions q ON q.id = m.question_id
        WHERE b.brand_type = 'competitor' {filter_clause} {school_clause}
        GROUP BY b.brand_name, q.school
        ORDER BY q.school, count DESC
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            rows = cur.fetchall()
    return [{"competitor": r[0], "school": r[1], "count": r[2]} for r in rows]


def get_competitor_citations(competitor, days=None, school=None):
    filter_clause = _date_filter(days).replace('AND created_at', 'AND m.created_at')
    school_clause, school_params = _school_clause_params(school)

    # Primary: read from pre-classified table populated at run time.
    classified_query = f"""
        SELECT ccm.url, COUNT(*) AS count
        FROM competitor_citation_map ccm
        JOIN mention_responses m ON m.id = ccm.mention_response_id
        LEFT JOIN questions q ON q.id = m.question_id
        WHERE ccm.competitor_name = %s
          {filter_clause} {school_clause}
        GROUP BY ccm.url
        ORDER BY count DESC
        LIMIT 10;
    """

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(classified_query, [competitor] + school_params)
            rows = cur.fetchall()

    if rows:
        return [{"url": r[0], "count": r[1]} for r in rows]

    # Fallback for data predating the migration: sole-competitor responses only.
    fallback_query = f"""
        WITH competitor_responses AS (
            SELECT DISTINCT m.id
            FROM mention_responses m
            JOIN mention_response_brands b ON b.mention_response_id = m.id
            LEFT JOIN questions q ON q.id = m.question_id
            WHERE b.brand_name = %s
              AND b.brand_type = 'competitor'
              {filter_clause} {school_clause}
        ),
        expanded AS (
            SELECT unnest(m.citations) AS cited_url
            FROM mention_responses m
            WHERE m.id IN (
                SELECT cr.id FROM competitor_responses cr
                WHERE NOT EXISTS (
                    SELECT 1 FROM mention_response_brands b2
                    WHERE b2.mention_response_id = cr.id
                      AND b2.brand_type = 'competitor'
                      AND b2.brand_name <> %s
                )
            )
            AND m.citations IS NOT NULL
        )
        SELECT cited_url, COUNT(*) AS count
        FROM expanded
        WHERE cited_url IS NOT NULL AND cited_url <> ''
        GROUP BY cited_url
        ORDER BY count DESC
        LIMIT 10;
    """

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(fallback_query, [competitor, competitor] + school_params)
            rows = cur.fetchall()

    return [{"url": r[0], "count": r[1]} for r in rows]


def get_competitor_win_rate(days=None, school=None):
    filter_clause = _date_filter(days).replace('AND created_at', 'AND s.created_at')
    school_clause, params = _school_clause_params(school)
    query = f"""
        SELECT s.competitor_won,
            COUNT(*) as wins,
            ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 1) as win_rate
        FROM sentiment_responses s
        LEFT JOIN questions q ON q.id = s.question_id
        WHERE s.competitor_won IS NOT NULL
        AND s.competitor_won != 'QC'
        AND s.competitor_won != 'no_clear_winner'
        {filter_clause} {school_clause}
        GROUP BY s.competitor_won
        ORDER BY wins DESC
        LIMIT 10;
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            rows = cur.fetchall()
    return [{"competitor": r[0], "win_rate": float(r[2])} for r in rows]
