from api.db import get_connection, _date_filter, _school_clause_params
from src.parsing.brands import canonicalize

def get_top_competitors_by_school(days=None, school=None):
    filter_clause = _date_filter(days).replace('AND created_at', 'AND m.created_at')
    school_clause, params = _school_clause_params(school)
    query = f"""
        SELECT
            COALESCE(b.canonical_name, b.brand_name) as competitor,
            q.school,
            COUNT(*) as count,
            SUM(b.rank_position) as sum_rank
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
    return [{"competitor": r[0], "school": r[1], "count": r[2], "sum_rank": r[3]} for r in rows]


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


def get_competitor_stats(competitor, days=None, school=None):
    filter_clause = _date_filter(days).replace('AND created_at', 'AND m.created_at')
    school_clause, school_params = _school_clause_params(school)

    with get_connection() as conn:
        with conn.cursor() as cur:
            # Total responses (denominator for rates)
            cur.execute(f"""
                SELECT COUNT(*)
                FROM mention_responses m
                LEFT JOIN questions q ON q.id = m.question_id
                WHERE 1=1 {filter_clause} {school_clause};
            """, school_params)
            total_responses = cur.fetchone()[0] or 0

            # Mention count and avg rank
            cur.execute(f"""
                SELECT COUNT(DISTINCT m.id), AVG(b.rank_position)
                FROM mention_response_brands b
                JOIN mention_responses m ON m.id = b.mention_response_id
                LEFT JOIN questions q ON q.id = m.question_id
                WHERE b.brand_name = %s AND b.brand_type = 'competitor'
                {filter_clause} {school_clause};
            """, [competitor] + school_params)
            row = cur.fetchone()
            mention_count = row[0] or 0
            avg_rank = round(float(row[1]), 2) if row[1] else None

            # Responses where this competitor has at least one citation URL
            cur.execute(f"""
                SELECT COUNT(DISTINCT ccm.mention_response_id)
                FROM competitor_citation_map ccm
                JOIN mention_responses m ON m.id = ccm.mention_response_id
                LEFT JOIN questions q ON q.id = m.question_id
                WHERE ccm.competitor_name = %s
                {filter_clause} {school_clause};
            """, [competitor] + school_params)
            cited_responses = cur.fetchone()[0] or 0

            # Total citation count (individual URLs)
            cur.execute(f"""
                SELECT COUNT(*)
                FROM competitor_citation_map ccm
                JOIN mention_responses m ON m.id = ccm.mention_response_id
                LEFT JOIN questions q ON q.id = m.question_id
                WHERE ccm.competitor_name = %s
                {filter_clause} {school_clause};
            """, [competitor] + school_params)
            citation_count = cur.fetchone()[0] or 0

            # SoV: competitor mentions vs all brand mentions
            cur.execute(f"""
                SELECT
                    SUM(CASE WHEN b.brand_name = %s THEN 1 ELSE 0 END) AS comp_mentions,
                    COUNT(*) AS total_mentions
                FROM mention_response_brands b
                JOIN mention_responses m ON m.id = b.mention_response_id
                LEFT JOIN questions q ON q.id = m.question_id
                WHERE 1=1 {filter_clause} {school_clause};
            """, [competitor] + school_params)
            sov_row = cur.fetchone()
            comp_mentions = sov_row[0] or 0
            total_mentions = sov_row[1] or 0

    mention_rate = round(mention_count / total_responses * 100, 1) if total_responses else 0
    citation_rate = round(cited_responses / total_responses * 100, 1) if total_responses else 0
    sov = round(comp_mentions / total_mentions * 100, 1) if total_mentions else None

    # Visibility score: mirrors QC composite formula (mention 40%, rank 45%, citation 15%)
    if avg_rank is not None:
        rank_val = avg_rank
        rank_score = 100 if rank_val <= 1 else 75 if rank_val <= 2 else 50 if rank_val <= 3 else 25
    else:
        rank_score = 0
    visibility_score = round(
        (mention_rate / 100) * 100 * 0.40 + rank_score * 0.45 + citation_rate * 0.15, 1
    )

    return {
        "mention_rate": mention_rate,
        "citation_count": citation_count,
        "citation_rate": citation_rate,
        "sov": sov,
        "avg_rank": avg_rank,
        "visibility_score": visibility_score,
    }


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
