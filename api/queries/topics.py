from api.db import get_connection, _date_filter
from collections import defaultdict

def get_topics(days=None):
    filter_clause = _date_filter(days)

    query = f"""
        WITH rates AS (
            SELECT
                q.school,
                q.id AS question_id,
                q.question,
                m.engine,
                AVG(CASE WHEN m.qc_mentioned THEN 1.0 ELSE 0.0 END) * 100 AS response_rate,
                AVG(CASE WHEN m.qc_cited    THEN 1.0 ELSE 0.0 END) * 100 AS citation_rate
            FROM mention_responses m
            JOIN questions q ON q.id = m.question_id
            WHERE q.school IS NOT NULL {filter_clause.replace('AND created_at', 'AND m.created_at')}
            GROUP BY q.school, q.id, q.question, m.engine
        ),
        brands AS (
            SELECT
                q.school,
                q.id AS question_id,
                m.engine,
                array_remove(array_agg(DISTINCT b.brand_name), NULL) AS competitors
            FROM mention_responses m
            JOIN questions q ON q.id = m.question_id
            LEFT JOIN mention_response_brands b
                ON b.mention_response_id = m.id AND b.brand_type = 'competitor'
            WHERE q.school IS NOT NULL {filter_clause.replace('AND created_at', 'AND m.created_at')}
            GROUP BY q.school, q.id, m.engine
        )
        SELECT
            r.school, r.question_id, r.question, r.engine,
            r.response_rate, r.citation_rate,
            COALESCE(br.competitors, ARRAY[]::text[]) AS competitors
        FROM rates r
        LEFT JOIN brands br
            ON br.school = r.school AND br.question_id = r.question_id AND br.engine = r.engine
        ORDER BY r.school, r.question_id, r.engine;
    """

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query)
            rows = cur.fetchall()

    topics = {}

    for school, qid, question, engine, res_rate, cit_rate, competitors in rows:
        res_rate = round(float(res_rate or 0), 1)
        cit_rate = round(float(cit_rate or 0), 1)
        visibility = round((res_rate + cit_rate) / 2, 1)
        competitors = [c for c in (competitors or []) if c]

        if school not in topics:
            topics[school] = {"prompts": {}}

        if qid not in topics[school]["prompts"]:
            topics[school]["prompts"][qid] = {
                "id": qid,
                "text": question,
                "results": {},
                "allCompetitors": [],
            }

        topics[school]["prompts"][qid]["results"][engine] = {
            "llm": engine,
            "responseRate": res_rate,
            "citationRate": cit_rate,
            "visibility": visibility,
            "competitorsMentioned": competitors,
            "queryFanouts": [],
        }
        topics[school]["prompts"][qid]["allCompetitors"].extend(competitors)

    result = []
    for school, topic_data in topics.items():
        prompts_out = []
        topic_vis_sum = defaultdict(list)

        for qid, prompt in topic_data["prompts"].items():
            results = prompt["results"]
            llm_vis = {engine: r["visibility"] for engine, r in results.items()}
            prompt_vis = round(sum(llm_vis.values()) / len(llm_vis), 1) if llm_vis else 0.0

            comp_counts = defaultdict(int)
            for c in prompt["allCompetitors"]:
                comp_counts[c] += 1
            top_rivals = [c for c, _ in sorted(comp_counts.items(), key=lambda x: -x[1])[:3]]

            prompts_out.append({
                "id": qid,
                "text": prompt["text"],
                "visibility": prompt_vis,
                "llms": llm_vis,
                "topRivals": top_rivals,
                "results": list(results.values()),
                "buyerProfile": None,
                "location": "Global",
                "tags": [],
            })

            for engine, vis in llm_vis.items():
                topic_vis_sum[engine].append(vis)

        topic_llms = {
            engine: round(sum(vals) / len(vals), 1)
            for engine, vals in topic_vis_sum.items()
        }
        all_vis = [v for vals in topic_vis_sum.values() for v in vals]
        topic_vis = round(sum(all_vis) / len(all_vis), 1) if all_vis else 0.0

        topic_comp_counts = defaultdict(int)
        for p in prompts_out:
            for c in p["topRivals"]:
                topic_comp_counts[c] += 1
        topic_rivals = [c for c, _ in sorted(topic_comp_counts.items(), key=lambda x: -x[1])[:3]]

        result.append({
            "name": school,
            "promptCount": len(prompts_out),
            "visibility": topic_vis,
            "llms": topic_llms,
            "topRivals": topic_rivals,
            "prompts": prompts_out,
        })

    result.sort(key=lambda t: t["name"])
    return result