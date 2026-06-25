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


def get_topics(days=None):
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

    # ── mention-type prompts ─────────────────────────────────────────────────
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
              + COUNT(DISTINCT comp)::float                               AS total_brand_slots,
            array_remove(array_agg(DISTINCT comp), NULL)                 AS competitors
        FROM mention_responses m
        JOIN questions q ON q.id = m.question_id
        CROSS JOIN LATERAL unnest(
            CASE WHEN m.competitors IS NULL OR array_length(m.competitors, 1) = 0
                 THEN ARRAY[NULL::text]
                 ELSE m.competitors
            END
        ) AS comp
        WHERE q.topic IS NOT NULL
          AND q.question_type IN ('course', 'general')
          {date_m}
        GROUP BY q.topic, q.id, q.question, m.engine
        ORDER BY q.topic, q.id, m.engine;
    """

    # ── sentiment-type prompts ───────────────────────────────────────────────
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
        WHERE q.topic IS NOT NULL
          AND q.question_type IN ('credibility', 'competition')
          {date_s}
        GROUP BY q.topic, q.id, q.question, s.engine
        ORDER BY q.topic, q.id, s.engine;
    """

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(mention_query)
            mention_rows = cur.fetchall()
            cur.execute(sentiment_query)
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


def get_prompt_detail(prompt_id: int, days=None):
    """
    Lazy-loaded detail for a single prompt (fetched when the row is expanded).
    Returns: { kind, timeseries, competitors, llms }

    kind="mention"  → timeseries has {day, visibility, mentionRate, citationRate}
                       competitors has [{name, count, sov, isQC}]
    kind="sentiment"→ timeseries has {day, positive, neutral, negative}
                       competitors has [{name, count, pct, isQC}] (from competitor_won)
    """
    date_m = _date_filter(days).replace("AND created_at", "AND m.created_at")
    date_s = _date_filter(days).replace("AND created_at", "AND s.created_at")

    # First determine question_type so we know which table to query
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
                        "day":         str(day),
                        "mentionRate": mr,
                        "citationRate": cr,
                        "visibility":  round((mr + cr) / 2, 1),
                    })

                # ── competitors ────────────────────────────────────────────
                cur.execute(f"""
                    SELECT comp, COUNT(*) AS cnt
                    FROM mention_responses m
                    CROSS JOIN LATERAL unnest(
                        CASE WHEN m.competitors IS NULL OR array_length(m.competitors, 1) = 0
                             THEN ARRAY[NULL::text]
                             ELSE m.competitors
                        END
                    ) AS comp
                    WHERE m.question_id = %s
                      AND comp IS NOT NULL
                      {date_m}
                    GROUP BY comp
                    ORDER BY cnt DESC;
                """, (prompt_id,))
                comp_rows = cur.fetchall()

                # Add QC row by counting qc_mentioned
                cur.execute(f"""
                    SELECT COUNT(*) FILTER (WHERE m.qc_mentioned) AS qc_cnt,
                           COUNT(*) AS total
                    FROM mention_responses m
                    WHERE m.question_id = %s {date_m};
                """, (prompt_id,))
                qc_row = cur.fetchone()
                qc_cnt   = int(qc_row[0] or 0)
                total_responses = int(qc_row[1] or 0)

                all_comps = [{"name": r[0], "count": int(r[1]), "isQC": False} for r in comp_rows]
                if qc_cnt > 0:
                    all_comps.insert(0, {"name": "QC", "count": qc_cnt, "isQC": True})

                max_count = max((c["count"] for c in all_comps), default=1)
                total_brand_slots = sum(c["count"] for c in all_comps)
                competitors = [{
                    **c,
                    "sov": round(c["count"] / total_brand_slots * 100, 1) if total_brand_slots else 0.0,
                    "pct": round(c["count"] / max_count * 100, 1),
                } for c in all_comps]

                # ── per-LLM metrics ────────────────────────────────────────
                cur.execute(f"""
                    SELECT
                        m.engine,
                        AVG(CASE WHEN m.qc_mentioned THEN 1.0 ELSE 0.0 END) * 100 AS mention_rate,
                        AVG(CASE WHEN m.qc_cited    THEN 1.0 ELSE 0.0 END) * 100  AS citation_rate,
                        SUM(CASE WHEN m.qc_mentioned THEN 1 ELSE 0 END)::float     AS qc_mentions,
                        COUNT(DISTINCT comp)::float                                 AS comp_count
                    FROM mention_responses m
                    CROSS JOIN LATERAL unnest(
                        CASE WHEN m.competitors IS NULL OR array_length(m.competitors, 1) = 0
                             THEN ARRAY[NULL::text]
                             ELSE m.competitors
                        END
                    ) AS comp
                    WHERE m.question_id = %s {date_m}
                    GROUP BY m.engine;
                """, (prompt_id,))
                engine_rows = cur.fetchall()

                # Latest raw response per engine
                cur.execute(f"""
                    SELECT DISTINCT ON (engine)
                        engine, raw_response, created_at
                    FROM mention_responses
                    WHERE question_id = %s {date_m}
                    ORDER BY engine, created_at DESC;
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
                        "latestResponse": latest_rows.get(engine, {}).get("response"),
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

                # ── competitors (from competitor_won) ──────────────────────
                cur.execute(f"""
                    SELECT
                        COALESCE(competitor_won, 'No clear winner') AS winner,
                        COUNT(*) AS cnt
                    FROM sentiment_responses s
                    WHERE s.question_id = %s
                      AND competitor_won IS NOT NULL
                      {date_s}
                    GROUP BY competitor_won
                    ORDER BY cnt DESC;
                """, (prompt_id,))
                comp_rows = cur.fetchall()
                total_comp = sum(int(r[1]) for r in comp_rows)
                competitors = [{
                    "name":  r[0],
                    "count": int(r[1]),
                    "pct":   round(int(r[1]) / total_comp * 100, 1) if total_comp else 0.0,
                    "sov":   None,
                    "isQC":  r[0] == "QC",
                } for r in comp_rows]

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

                cur.execute(f"""
                    SELECT DISTINCT ON (engine)
                        engine, raw_response, created_at
                    FROM sentiment_responses
                    WHERE question_id = %s {date_s}
                    ORDER BY engine, created_at DESC;
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
                        "latestResponse": latest_rows.get(engine, {}).get("response"),
                        "latestResponseDate": latest_rows.get(engine, {}).get("date"),
                    })

                kind = "sentiment"

    return {
        "kind":        kind,
        "timeseries":  timeseries,
        "competitors": competitors,
        "llms":        llms,
    }
