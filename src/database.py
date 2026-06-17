import os
import psycopg2
from dotenv import load_dotenv
from src.logger import logger

load_dotenv()

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
            cur.execute("""
                INSERT INTO mention_responses (
                    run_id, question_id, engine, raw_response, citations,
                    qc_mentioned, qc_mention_order, qc_recommendation,
                    competitors, competitor_count, competitor_won, win_reasons
                ) VALUES (
                    %s, %s, %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s, %s
                )
            """, (
                run_id, question_id, engine, raw_response, citations,
                parsed.get("qc_mentioned"), parsed.get("qc_mention_order"), parsed.get("qc_recommendation"),
                parsed.get("competitors"), parsed.get("competitor_count"), parsed.get("competitor_won"), parsed.get("win_reasons")
            ))
        conn.commit()

def save_sentiment_response(run_id, question_id, engine, raw_response, citations, parsed):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO sentiment_responses (
                    run_id, question_id, engine, raw_response, citations,
                    qc_sentiment, qc_verdict, concerns_raised, positives_raised,
                    competitors, competitor_count, competitor_won, win_reasons
                ) VALUES (
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, %s
                )
            """, (
                run_id, question_id, engine, raw_response, citations,
                parsed.get("qc_sentiment"), parsed.get("qc_verdict"), parsed.get("concerns_raised"), parsed.get("positives_raised"),
                parsed.get("competitors"), parsed.get("competitor_count"), parsed.get("competitor_won"), parsed.get("win_reasons")
            ))
        conn.commit()

def get_questions():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, question, question_type FROM questions WHERE active = true LIMIT 3")
            return cur.fetchall()