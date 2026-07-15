import os
import psycopg2
from dotenv import load_dotenv
from src.logger import logger

load_dotenv()

QC_DOMAINS = [
    "qccareerschool",
    "qcpetstudies",
    "qceventplanning",
    "qcdesignschool",
    "qcmakeupacademy",
    "qcwellnessstudies",
]

def is_qc_domain(url):
    url_lower = (url or "").lower()
    return any(domain in url_lower for domain in QC_DOMAINS)

def get_connection():
    return psycopg2.connect(os.getenv("SUPABASE_DB_URL"))

def start_run():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO runs (started_at, status) VALUES (now(), 'running') RETURNING id"
            )
            run_id = cur.fetchone()[0]
        conn.commit()
    return run_id

def finish_run(run_id, status="success", error=None):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE runs SET finished_at = now(), status = %s, error = %s WHERE id = %s",
                (status, error, run_id)
            )
        conn.commit()

def save_mention_response(run_id, question_id, engine, raw_response, citations, parsed):
    with get_connection() as conn:
        with conn.cursor() as cur:
            # 1. Insert into mention_responses
            cur.execute("""
                INSERT INTO mention_responses (
                    run_id, question_id, engine, raw_response, citations,
                    qc_mentioned, qc_mention_order, qc_cited
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                run_id, question_id, engine, raw_response, citations,
                parsed.get("qc_mentioned"),
                parsed.get("qc_mention_order"),
                parsed.get("qc_cited")
            ))

            mention_response_id = cur.fetchone()[0]

            if parsed.get("qc_mentioned") and parsed.get("qc_mention_order") is None:
                logger.error(f"qc_mentioned=true but qc_mention_order is null for mention_response {mention_response_id}")

            # 2. Insert brand rows into mention_response_brands
            brands = parsed.get("brands", [])
            for b in brands:
                name = b.get("name")
                brand_type = b.get("brand_type")
                rank_position = b.get("rank_position")
                if not name or not brand_type or rank_position is None:
                    logger.error(f"Skipping malformed brand entry for mention_response {mention_response_id}: {b}")
                    continue

                cur.execute("""
                    INSERT INTO mention_response_brands (
                        mention_response_id, brand_name, brand_type, rank_position
                    ) VALUES (%s, %s, %s, %s)
                """, (
                    mention_response_id,
                    name,
                    brand_type,
                    rank_position
                ))

            # 3. Insert link rows into mention_response_links
            links = parsed.get("links", [])
            for l in links:
                url = l.get("url")
                is_qc = l.get("is_qc")
                is_inline = l.get("is_inline")
                if not url or is_qc is None or is_inline is None:
                    logger.error(f"Skipping malformed link entry for mention_response {mention_response_id}: {l}")
                    continue

                is_qc_internal = is_qc_domain(url)

                cur.execute("""
                    INSERT INTO mention_response_links (
                        mention_response_id, url, is_qc, is_qc_internal, is_inline
                    ) VALUES (%s, %s, %s, %s, %s)
                """, (
                    mention_response_id,
                    url,
                    bool(is_qc) or is_qc_internal,
                    is_qc_internal,
                    bool(is_inline)
                ))

        conn.commit()

def save_sentiment_response(run_id, question_id, engine, raw_response, citations, parsed):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO sentiment_responses (
                    run_id, question_id, engine, raw_response, citations,
                    qc_sentiment, qc_verdict, concerns_raised, positives_raised,
                    competitor_won, win_reasons, qc_cited
                ) VALUES (
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s
                )
            """, (
                run_id, question_id, engine, raw_response, citations,
                parsed.get("qc_sentiment"), parsed.get("qc_verdict"), parsed.get("concerns_raised"), parsed.get("positives_raised"),
                parsed.get("competitor_won"), parsed.get("win_reasons"), parsed.get("qc_cited")
            ))
        
        conn.commit()

def save_fanout_queries(run_id, question_id, engine, queries):
    if not queries:
        return
    with get_connection() as conn:
        with conn.cursor() as cur:
            for i, query in enumerate(queries):
                cur.execute(
                    "INSERT INTO fanout_queries (question_id, run_id, engine, query, query_order) VALUES (%s, %s, %s, %s, %s)",
                    (question_id, run_id, engine, query, i)
                )
        conn.commit()


def get_processed_question_ids(run_id):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT DISTINCT question_id FROM mention_responses WHERE run_id = %s
                UNION
                SELECT DISTINCT question_id FROM sentiment_responses WHERE run_id = %s
            """, (run_id, run_id))
            return {row[0] for row in cur.fetchall()}


def get_questions():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, question, question_type
                FROM questions
                WHERE active = true
            """)
            return cur.fetchall()