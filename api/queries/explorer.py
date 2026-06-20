from api.db import get_connection

def get_responses(
    days=None,
    engine=None,
    question_type=None,
    school=None,
    qc_mentioned=None,
    sentiment=None,
    page=1,
    page_size=20
):
    offset = (page - 1) * page_size
    conditions_mention = ["1=1"]
    conditions_sentiment = ["1=1"]

    if days:
        conditions_mention.append(f"m.created_at >= now() - interval '{int(days)} days'")
        conditions_sentiment.append(f"s.created_at >= now() - interval '{int(days)} days'")
    if engine:
        conditions_mention.append(f"m.engine = '{engine}'")
        conditions_sentiment.append(f"s.engine = '{engine}'")
    if question_type:
        conditions_mention.append(f"q.question_type = '{question_type}'")
        conditions_sentiment.append(f"q.question_type = '{question_type}'")
    if school:
        conditions_mention.append(f"q.school = '{school}'")
        conditions_sentiment.append(f"q.school = '{school}'")
    if qc_mentioned is not None:
        conditions_mention.append(f"m.qc_mentioned = {str(qc_mentioned).lower()}")
    if sentiment:
        conditions_sentiment.append(f"s.qc_sentiment = '{sentiment}'")

    where_mention = " AND ".join(conditions_mention)
    where_sentiment = " AND ".join(conditions_sentiment)

    # only include mention_responses if not filtering by sentiment
    # only include sentiment_responses if not filtering by qc_mentioned
    parts = []

    if qc_mentioned is None and question_type not in ("credibility", "competition"):
        parts.append(f"""
            SELECT
                m.id,
                q.question,
                m.engine,
                q.school,
                q.question_type,
                m.qc_mentioned::text as qc_mentioned,
                NULL as qc_sentiment,
                m.raw_response,
                m.created_at
            FROM mention_responses m
            JOIN questions q ON q.id = m.question_id
            WHERE {where_mention}
        """)

    if sentiment is None and question_type not in ("course", "general"):
        parts.append(f"""
            SELECT
                s.id,
                q.question,
                s.engine,
                q.school,
                q.question_type,
                NULL as qc_mentioned,
                s.qc_sentiment::text as qc_sentiment,
                s.raw_response,
                s.created_at
            FROM sentiment_responses s
            JOIN questions q ON q.id = s.question_id
            WHERE {where_sentiment}
        """)

    if not parts:
        return {"results": [], "total": 0, "page": page, "page_size": page_size}

    union_query = " UNION ALL ".join(parts)

    count_query = f"SELECT COUNT(*) FROM ({union_query}) combined"
    data_query = f"""
        SELECT * FROM ({union_query}) combined
        ORDER BY created_at DESC
        LIMIT {page_size} OFFSET {offset}
    """

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(count_query)
            total = cur.fetchone()[0]
            cur.execute(data_query)
            rows = cur.fetchall()

    results = [
        {
            "id": str(r[0]),
            "question": r[1],
            "engine": r[2],
            "school": r[3],
            "question_type": r[4],
            "qc_mentioned": r[5],
            "qc_sentiment": r[6],
            "raw_response": r[7],
            "created_at": str(r[8])
        }
        for r in rows
    ]

    return {
        "results": results,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": -(-total // page_size)
    }