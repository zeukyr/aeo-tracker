from api.db import get_connection, _date_filter
from collections import defaultdict

# Topic order for deterministic display
TOPIC_ORDER = [
    "Career Exploration",
    "How to Become",
    "Starting a Business",
    "Course Discovery",
    "Brand Credibility",
    "Competitor Comparison",
]

def _topic_sort_key(topic_name):
    try:
        return TOPIC_ORDER.index(topic_name)
    except ValueError:
        return len(TOPIC_ORDER)  # unknown topics go last


MENTION_TYPES = ("course", "general")
SENTIMENT_TYPES = ("credibility", "competition")


def _topic_filter_plan(question_type=None, engine=None, school=None, qc_mentioned=None, sentiment=None):
    """
    Shared filter-resolution logic for get_topics / get_topics_over_time.

    Returns (include_mention, mention_types, mention_conditions, mention_params,
             include_sentiment, sentiment_types, sentiment_conditions, sentiment_params)
    where *_conditions/*_params are extra SQL condition strings (parameterized with %s)
    and their bound values, beyond the base topic/question_type/date filters.
    """
    mention_types = [t for t in MENTION_TYPES if question_type in (None, "All", t)]
    sentiment_types = [t for t in SENTIMENT_TYPES if question_type in (None, "All", t)]

    # qc_mentioned only exists on mention_responses; sentiment only on sentiment_responses.
    # Filtering by one implicitly excludes the other branch of the union.
    include_mention = sentiment is None and bool(mention_types)
    include_sentiment = qc_mentioned is None and bool(sentiment_types)

    if school == "General":
        school_cond, school_param = "q.school IS NULL", []
    elif school:
        school_cond, school_param = "q.school = %s", [school]
    else:
        school_cond, school_param = None, []

    mention_conditions, mention_params = [], []
    if engine:
        mention_conditions.append("m.engine = %s")
        mention_params.append(engine)
    if school_cond:
        mention_conditions.append(school_cond)
        mention_params.extend(school_param)
    if qc_mentioned is not None:
        mention_conditions.append("m.qc_mentioned = %s")
        mention_params.append(qc_mentioned)

    sentiment_conditions, sentiment_params = [], []
    if engine:
        sentiment_conditions.append("s.engine = %s")
        sentiment_params.append(engine)
    if school_cond:
        sentiment_conditions.append(school_cond)
        sentiment_params.extend(school_param)
    if sentiment:
        sentiment_conditions.append("s.qc_sentiment = %s")
        sentiment_params.append(sentiment)

    return (include_mention, mention_types, mention_conditions, mention_params,
            include_sentiment, sentiment_types, sentiment_conditions, sentiment_params)


def get_topics(days=None, engine=None, question_type=None, school=None, qc_mentioned=None, sentiment=None):
    """
    Returns the lightweight topic/prompt list used by the accordion table.
    Groups by q.topic (new column, parallel to q.school).

    Each topic is tagged with kind="mention" or kind="sentiment" to tell
    the frontend which columns apply.
    - mention  → visibility + sov (from mention_responses, question_type in ('course','general'))
    - sentiment → sentiment / positive_rate (from sentiment_responses, question_type in ('credibility','competition'))
    """
    date_m = _date_filter(days).replace("AND created_at", "AND m.created_at")
    date_s = _date_filter(days).replace("AND created_at", "AND s.created_at")

    (include_mention, mention_types, mention_extra, mention_params,
     include_sentiment, sentiment_types, sentiment_extra, sentiment_params) = _topic_filter_plan(
        question_type, engine, school, qc_mentioned, sentiment
    )

    mention_rows, sentiment_rows = [], []

    with get_connection() as conn:
        with conn.cursor() as cur:
            if include_mention:
                mention_where = " AND ".join(
                    ["q.topic IS NOT NULL", "q.question_type = ANY(%s)"] + mention_extra
                )
                mention_query = f"""
                    SELECT
                        COALESCE(q.topic, 'Uncategorized') AS topic,
                        q.id                               AS question_id,
                        q.question,
                        m.engine,
                        AVG(CASE WHEN m.qc_mentioned THEN 1.0 ELSE 0.0 END) * 100  AS response_rate,
                        AVG(CASE WHEN m.qc_cited    THEN 1.0 ELSE 0.0 END) * 100   AS citation_rate,
                        -- SOV numerator: total rows where QC was mentioned
                        SUM(CASE WHEN m.qc_mentioned THEN 1 ELSE 0 END)::float      AS qc_mentions,
                        -- SOV denominator: QC mentions + total distinct competitor slots
                        SUM(CASE WHEN m.qc_mentioned THEN 1 ELSE 0 END)::float
                          + COUNT(DISTINCT b.brand_name)::float                       AS total_brand_slots,
                        array_remove(array_agg(DISTINCT b.brand_name), NULL)         AS competitors
                    FROM mention_responses m
                    JOIN questions q ON q.id = m.question_id
                    LEFT JOIN mention_response_brands b
                        ON b.mention_response_id = m.id AND b.brand_type = 'competitor'
                    WHERE {mention_where}
                      {date_m}
                    GROUP BY q.topic, q.id, q.question, m.engine
                    ORDER BY q.topic, q.id, m.engine;
                """
                cur.execute(mention_query, [mention_types] + mention_params)
                mention_rows = cur.fetchall()

            if include_sentiment:
                sentiment_where = " AND ".join(
                    ["q.topic IS NOT NULL", "q.question_type = ANY(%s)"] + sentiment_extra
                )
                sentiment_query = f"""
                    SELECT
                        COALESCE(q.topic, 'Uncategorized') AS topic,
                        q.id                               AS question_id,
                        q.question,
                        s.engine,
                        COUNT(*) FILTER (WHERE s.qc_sentiment = 'positive') AS pos_count,
                        COUNT(*) FILTER (WHERE s.qc_sentiment = 'neutral')  AS neu_count,
                        COUNT(*) FILTER (WHERE s.qc_sentiment = 'negative') AS neg_count,
                        COUNT(*)                                             AS total_count
                    FROM sentiment_responses s
                    JOIN questions q ON q.id = s.question_id
                    WHERE {sentiment_where}
                      {date_s}
                    GROUP BY q.topic, q.id, q.question, s.engine
                    ORDER BY q.topic, q.id, s.engine;
                """
                cur.execute(sentiment_query, [sentiment_types] + sentiment_params)
                sentiment_rows = cur.fetchall()

    # ── aggregate mention rows ───────────────────────────────────────────────
    mention_topics = {}  # topic → {prompts: {qid: {...}}}

    for (topic, qid, question, engine,
         res_rate, cit_rate, qc_mentions, total_brand_slots, competitors) in mention_rows:

        res_rate  = round(float(res_rate  or 0), 1)
        cit_rate  = round(float(cit_rate  or 0), 1)
        vis       = round((res_rate + cit_rate) / 2, 1)
        qc_m      = float(qc_mentions or 0)
        total_b   = float(total_brand_slots or 0)
        sov       = round(qc_m / total_b * 100, 1) if total_b > 0 else 0.0
        competitors = [c for c in (competitors or []) if c]

        if topic not in mention_topics:
            mention_topics[topic] = {"prompts": {}}

        if qid not in mention_topics[topic]["prompts"]:
            mention_topics[topic]["prompts"][qid] = {
                "id": qid,
                "text": question,
                "kind": "mention",
                "engines": {},
                "allCompetitors": [],
            }

        mention_topics[topic]["prompts"][qid]["engines"][engine] = {
            "visibility": vis,
            "sov": sov,
        }
        mention_topics[topic]["prompts"][qid]["allCompetitors"].extend(competitors)

    # ── aggregate sentiment rows ─────────────────────────────────────────────
    sentiment_topics = {}  # topic → {prompts: {qid: {...}}}

    for (topic, qid, question, engine,
         pos_count, neu_count, neg_count, total_count) in sentiment_rows:

        total_count = int(total_count or 0)
        pos_rate = round(int(pos_count or 0) / total_count * 100, 1) if total_count else 0.0
        neu_rate = round(int(neu_count or 0) / total_count * 100, 1) if total_count else 0.0
        neg_rate = round(int(neg_count or 0) / total_count * 100, 1) if total_count else 0.0

        if topic not in sentiment_topics:
            sentiment_topics[topic] = {"prompts": {}}

        if qid not in sentiment_topics[topic]["prompts"]:
            sentiment_topics[topic]["prompts"][qid] = {
                "id": qid,
                "text": question,
                "kind": "sentiment",
                "engines": {},
            }

        sentiment_topics[topic]["prompts"][qid]["engines"][engine] = {
            "sentiment": pos_rate,   # "sentiment" column = positive rate, consistent with summary.py
            "positive": pos_rate,
            "neutral":  neu_rate,
            "negative": neg_rate,
        }

    # ── build output list ────────────────────────────────────────────────────
    result = []

    # mention topics
    for topic, topic_data in mention_topics.items():
        prompts_out = []
        topic_vis_vals = []
        topic_sov_vals = []

        for qid, prompt in topic_data["prompts"].items():
            engines = prompt["engines"]
            if not engines:
                continue

            p_vis  = round(sum(e["visibility"] for e in engines.values()) / len(engines), 1)
            p_sov  = round(sum(e["sov"]        for e in engines.values()) / len(engines), 1)

            comp_counts = defaultdict(int)
            for c in prompt["allCompetitors"]:
                comp_counts[c] += 1
            top_rivals = [c for c, _ in sorted(comp_counts.items(), key=lambda x: -x[1])[:3]]

            prompts_out.append({
                "id":         qid,
                "text":       prompt["text"],
                "kind":       "mention",
                "visibility": p_vis,
                "sentiment":  None,
                "sov":        p_sov,
                "topRivals":  top_rivals,
            })
            topic_vis_vals.append(p_vis)
            topic_sov_vals.append(p_sov)

        if not prompts_out:
            continue

        result.append({
            "name":        topic,
            "kind":        "mention",
            "promptCount": len(prompts_out),
            "visibility":  round(sum(topic_vis_vals) / len(topic_vis_vals), 1),
            "sentiment":   None,
            "sov":         round(sum(topic_sov_vals) / len(topic_sov_vals), 1),
            "prompts":     prompts_out,
        })

    # sentiment topics
    for topic, topic_data in sentiment_topics.items():
        prompts_out = []
        topic_sent_vals = []

        for qid, prompt in topic_data["prompts"].items():
            engines = prompt["engines"]
            if not engines:
                continue

            p_sent = round(sum(e["sentiment"] for e in engines.values()) / len(engines), 1)

            prompts_out.append({
                "id":         qid,
                "text":       prompt["text"],
                "kind":       "sentiment",
                "visibility": None,
                "sentiment":  p_sent,
                "sov":        None,
                "topRivals":  [],
            })
            topic_sent_vals.append(p_sent)

        if not prompts_out:
            continue

        result.append({
            "name":        topic,
            "kind":        "sentiment",
            "promptCount": len(prompts_out),
            "visibility":  None,
            "sentiment":   round(sum(topic_sent_vals) / len(topic_sent_vals), 1),
            "sov":         None,
            "prompts":     prompts_out,
        })

    result.sort(key=lambda t: _topic_sort_key(t["name"]))
    return result


def get_topics_over_time(days=None, engine=None, question_type=None, school=None, qc_mentioned=None, sentiment=None):
    """
    Returns time-series data for the top-level topics chart.
    One data point per (topic, day); score = visibility % for mention topics,
    positive-sentiment % for sentiment topics.

    Returns: { topics: [{name, kind}], series: [{day, "<topic>": value, ...}] }
    """
    date_m = _date_filter(days).replace("AND created_at", "AND m.created_at")
    date_s = _date_filter(days).replace("AND created_at", "AND s.created_at")

    (include_mention, mention_types, mention_extra, mention_params,
     include_sentiment, sentiment_types, sentiment_extra, sentiment_params) = _topic_filter_plan(
        question_type, engine, school, qc_mentioned, sentiment
    )

    mention_rows, sentiment_rows = [], []

    with get_connection() as conn:
        with conn.cursor() as cur:
            if include_mention:
                mention_where = " AND ".join(
                    ["q.topic IS NOT NULL", "q.question_type = ANY(%s)"] + mention_extra
                )
                mention_q = f"""
                    SELECT
                        COALESCE(q.topic, 'Uncategorized') AS topic,
                        date(m.created_at)                 AS day,
                        AVG(
                            (CASE WHEN m.qc_mentioned THEN 1.0 ELSE 0.0 END +
                             CASE WHEN m.qc_cited    THEN 1.0 ELSE 0.0 END) / 2.0
                        ) * 100 AS score
                    FROM mention_responses m
                    JOIN questions q ON q.id = m.question_id
                    WHERE {mention_where}
                      {date_m}
                    GROUP BY q.topic, date(m.created_at)
                    ORDER BY day, q.topic;
                """
                cur.execute(mention_q, [mention_types] + mention_params)
                mention_rows = cur.fetchall()

            if include_sentiment:
                sentiment_where = " AND ".join(
                    ["q.topic IS NOT NULL", "q.question_type = ANY(%s)"] + sentiment_extra
                )
                sentiment_q = f"""
                    SELECT
                        COALESCE(q.topic, 'Uncategorized') AS topic,
                        date(s.created_at)                 AS day,
                        COUNT(*) FILTER (WHERE s.qc_sentiment = 'positive') * 100.0
                            / NULLIF(COUNT(*), 0)           AS score
                    FROM sentiment_responses s
                    JOIN questions q ON q.id = s.question_id
                    WHERE {sentiment_where}
                      {date_s}
                    GROUP BY q.topic, date(s.created_at)
                    ORDER BY day, q.topic;
                """
                cur.execute(sentiment_q, [sentiment_types] + sentiment_params)
                sentiment_rows = cur.fetchall()

    topics_seen = {}   # name → kind
    days_data   = {}   # day_str → {topic: score}

    for topic, day, score in mention_rows:
        day_str = str(day)
        score   = round(float(score or 0), 1)
        days_data.setdefault(day_str, {})[topic] = score
        topics_seen.setdefault(topic, "mention")

    for topic, day, score in sentiment_rows:
        day_str = str(day)
        score   = round(float(score or 0), 1)
        days_data.setdefault(day_str, {})[topic] = score
        topics_seen.setdefault(topic, "sentiment")

    series = [
        {"day": day, **scores}
        for day, scores in sorted(days_data.items())
    ]

    # Return topics in canonical display order
    topics_list = [
        {"name": name, "kind": topics_seen[name]}
        for name in TOPIC_ORDER
        if name in topics_seen
    ]
    for name, kind in topics_seen.items():
        if name not in TOPIC_ORDER:
            topics_list.append({"name": name, "kind": kind})

    return {"topics": topics_list, "series": series}


def get_prompt_detail(prompt_id: str, days=None):
    """
    Lazy-loaded detail for a single prompt (fetched when the row is expanded).
    Returns: { kind, timeseries, competitors, llms }

    kind="mention"  → timeseries has {day, visibility, mentionRate, citationRate}
                       competitors has [{name, visibility (mention rate %), isQC}]
    kind="sentiment"→ timeseries has {day, positive, neutral, negative}
                       competitors has [{name, visibility: null, isQC}] (plain name list)
    """
    date_m = _date_filter(days).replace("AND created_at", "AND m.created_at")
    date_s = _date_filter(days).replace("AND created_at", "AND s.created_at")

    # Determine question_type to pick the right table
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT question_type FROM questions WHERE id = %s", (prompt_id,))
            row = cur.fetchone()
            if not row:
                return None
            question_type = row[0]

    is_mention = question_type in ("course", "general")

    with get_connection() as conn:
        with conn.cursor() as cur:

            if is_mention:
                # ── timeseries ─────────────────────────────────────────────
                cur.execute(f"""
                    SELECT
                        date(m.created_at)                                          AS day,
                        AVG(CASE WHEN m.qc_mentioned THEN 1.0 ELSE 0.0 END) * 100  AS mention_rate,
                        AVG(CASE WHEN m.qc_cited    THEN 1.0 ELSE 0.0 END) * 100   AS citation_rate
                    FROM mention_responses m
                    WHERE m.question_id = %s {date_m}
                    GROUP BY date(m.created_at)
                    ORDER BY day;
                """, (prompt_id,))
                ts_rows = cur.fetchall()
                timeseries = []
                for (day, mr, cr) in ts_rows:
                    mr = round(float(mr or 0), 1)
                    cr = round(float(cr or 0), 1)
                    timeseries.append({
                        "day":          str(day),
                        "mentionRate":  mr,
                        "citationRate": cr,
                        "visibility":   round((mr + cr) / 2, 1),
                    })

                # ── QC stats + total responses ─────────────────────────────
                cur.execute(f"""
                    SELECT
                        COUNT(*) FILTER (WHERE m.qc_mentioned) AS qc_cnt,
                        COUNT(*)                                AS total
                    FROM mention_responses m
                    WHERE m.question_id = %s {date_m};
                """, (prompt_id,))
                qc_row = cur.fetchone()
                qc_cnt          = int(qc_row[0] or 0)
                total_responses = max(int(qc_row[1] or 0), 1)  # guard div-by-zero

                # ── competitors ranked by mention rate % ───────────────────
                # cnt = number of responses (rows) that mention this competitor
                cur.execute(f"""
                    SELECT b.brand_name, COUNT(*) AS cnt
                    FROM mention_responses m
                    JOIN mention_response_brands b
                        ON b.mention_response_id = m.id AND b.brand_type = 'competitor'
                    WHERE m.question_id = %s
                      {date_m}
                    GROUP BY b.brand_name
                    ORDER BY cnt DESC;
                """, (prompt_id,))
                comp_rows = cur.fetchall()

                all_comps = [
                    {
                        "name":       r[0],
                        "visibility": round(int(r[1]) / total_responses * 100, 1),
                        "isQC":       False,
                    }
                    for r in comp_rows
                ]
                if qc_cnt > 0:
                    all_comps.append({
                        "name":       "QC",
                        "visibility": round(qc_cnt / total_responses * 100, 1),
                        "isQC":       True,
                    })

                all_comps.sort(key=lambda c: -c["visibility"])
                competitors = all_comps

                # ── per-LLM metrics ────────────────────────────────────────
                cur.execute(f"""
                    SELECT
                        m.engine,
                        AVG(CASE WHEN m.qc_mentioned THEN 1.0 ELSE 0.0 END) * 100 AS mention_rate,
                        AVG(CASE WHEN m.qc_cited    THEN 1.0 ELSE 0.0 END) * 100  AS citation_rate,
                        SUM(CASE WHEN m.qc_mentioned THEN 1 ELSE 0 END)::float     AS qc_mentions,
                        COUNT(DISTINCT b.brand_name)::float                         AS comp_count
                    FROM mention_responses m
                    LEFT JOIN mention_response_brands b
                        ON b.mention_response_id = m.id AND b.brand_type = 'competitor'
                    WHERE m.question_id = %s {date_m}
                    GROUP BY m.engine;
                """, (prompt_id,))
                engine_rows = cur.fetchall()

                # Bug fix: alias table so {date_m} resolves m.created_at correctly
                cur.execute(f"""
                    SELECT DISTINCT ON (m.engine)
                        m.engine, m.raw_response, m.created_at
                    FROM mention_responses m
                    WHERE m.question_id = %s {date_m}
                    ORDER BY m.engine, m.created_at DESC;
                """, (prompt_id,))
                latest_rows = {r[0]: {"response": r[1], "date": str(r[2])} for r in cur.fetchall()}

                llms = []
                for (engine, mr, cr, qc_m, comp_c) in engine_rows:
                    mr    = round(float(mr  or 0), 1)
                    cr    = round(float(cr  or 0), 1)
                    qc_m  = float(qc_m  or 0)
                    comp_c = float(comp_c or 0)
                    total_b = qc_m + comp_c
                    llms.append({
                        "engine":       engine,
                        "kind":         "mention",
                        "mentionRate":  mr,
                        "citationRate": cr,
                        "visibility":   round((mr + cr) / 2, 1),
                        "sentiment":    None,
                        "sov":          round(qc_m / total_b * 100, 1) if total_b else 0.0,
                        "latestResponse":     latest_rows.get(engine, {}).get("response"),
                        "latestResponseDate": latest_rows.get(engine, {}).get("date"),
                    })

                kind = "mention"

            else:
                # ── timeseries ─────────────────────────────────────────────
                cur.execute(f"""
                    SELECT
                        date(s.created_at)                                              AS day,
                        COUNT(*) FILTER (WHERE s.qc_sentiment = 'positive') * 100.0
                            / NULLIF(COUNT(*), 0)                                       AS positive,
                        COUNT(*) FILTER (WHERE s.qc_sentiment = 'neutral')  * 100.0
                            / NULLIF(COUNT(*), 0)                                       AS neutral,
                        COUNT(*) FILTER (WHERE s.qc_sentiment = 'negative') * 100.0
                            / NULLIF(COUNT(*), 0)                                       AS negative
                    FROM sentiment_responses s
                    WHERE s.question_id = %s {date_s}
                    GROUP BY date(s.created_at)
                    ORDER BY day;
                """, (prompt_id,))
                ts_rows = cur.fetchall()
                timeseries = [{
                    "day":      str(r[0]),
                    "positive": round(float(r[1] or 0), 1),
                    "neutral":  round(float(r[2] or 0), 1),
                    "negative": round(float(r[3] or 0), 1),
                } for r in ts_rows]

                # ── competitors: plain name list from competitor_won ────────
                # No mention data exists for sentiment prompts, so we just list
                # distinct competitor names that appeared as "winner", no bar data.
                cur.execute(f"""
                    SELECT DISTINCT s.competitor_won AS name
                    FROM sentiment_responses s
                    WHERE s.question_id = %s
                      AND s.competitor_won IS NOT NULL
                      AND s.competitor_won != 'no_clear_winner'
                      {date_s}
                    ORDER BY name;
                """, (prompt_id,))
                comp_rows = cur.fetchall()
                competitors = [
                    {"name": r[0], "visibility": None, "isQC": r[0] == "QC"}
                    for r in comp_rows
                ]

                # ── per-LLM metrics ────────────────────────────────────────
                cur.execute(f"""
                    SELECT
                        s.engine,
                        COUNT(*) FILTER (WHERE s.qc_sentiment = 'positive') * 100.0
                            / NULLIF(COUNT(*), 0) AS pos_rate,
                        COUNT(*) FILTER (WHERE s.qc_sentiment = 'neutral')  * 100.0
                            / NULLIF(COUNT(*), 0) AS neu_rate,
                        COUNT(*) FILTER (WHERE s.qc_sentiment = 'negative') * 100.0
                            / NULLIF(COUNT(*), 0) AS neg_rate
                    FROM sentiment_responses s
                    WHERE s.question_id = %s {date_s}
                    GROUP BY s.engine;
                """, (prompt_id,))
                engine_rows = cur.fetchall()

                # Bug fix: alias table so {date_s} resolves s.created_at correctly
                cur.execute(f"""
                    SELECT DISTINCT ON (s.engine)
                        s.engine, s.raw_response, s.created_at
                    FROM sentiment_responses s
                    WHERE s.question_id = %s {date_s}
                    ORDER BY s.engine, s.created_at DESC;
                """, (prompt_id,))
                latest_rows = {r[0]: {"response": r[1], "date": str(r[2])} for r in cur.fetchall()}

                llms = []
                for (engine, pos, neu, neg) in engine_rows:
                    llms.append({
                        "engine":       engine,
                        "kind":         "sentiment",
                        "mentionRate":  None,
                        "citationRate": None,
                        "visibility":   None,
                        "sentiment":    round(float(pos or 0), 1),
                        "positive":     round(float(pos or 0), 1),
                        "neutral":      round(float(neu or 0), 1),
                        "negative":     round(float(neg or 0), 1),
                        "sov":          None,
                        "latestResponse":     latest_rows.get(engine, {}).get("response"),
                        "latestResponseDate": latest_rows.get(engine, {}).get("date"),
                    })

                kind = "sentiment"

    return {
        "kind":        kind,
        "timeseries":  timeseries,
        "competitors": competitors,
        "llms":        llms,
    }


def get_prompt_responses(prompt_id: str, engine: str, days=None):
    """
    Full response history for one (prompt, engine) pair, newest first.
    Powers the response-drawer's prev/next navigation.

    Returns: [{response, date}, ...] or None if the prompt doesn't exist.
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT question_type FROM questions WHERE id = %s", (prompt_id,))
            row = cur.fetchone()
            if not row:
                return None
            question_type = row[0]

            is_mention = question_type in MENTION_TYPES
            table = "mention_responses" if is_mention else "sentiment_responses"
            date_filter = _date_filter(days)

            cur.execute(f"""
                SELECT raw_response, created_at
                FROM {table}
                WHERE question_id = %s AND engine = %s {date_filter}
                ORDER BY created_at DESC;
            """, (prompt_id, engine))
            rows = cur.fetchall()

    return [{"response": r[0], "date": str(r[1])} for r in rows]
