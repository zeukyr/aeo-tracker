import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

def get_connection():
    return psycopg2.connect(os.getenv("SUPABASE_DB_URL"))

def _date_filter(days):
    if days:
        return f"AND created_at >= now() - interval '{int(days)} days'"
    return ""
    
def _prev_date_filter(days, alias=None):
    prefix = f"{alias}." if alias else ""
    if days:
        return f"AND {prefix}created_at >= now() - interval '{int(days) * 2} days' AND {prefix}created_at < now() - interval '{int(days)} days'"
    return ""

def _school_clause_params(school):
    if school == "General":
        return "AND q.school IS NULL", []
    if school:
        return "AND q.school = %s", [school]
    return "", []

def _rank_score_cte(alias="rt"):
    return f"{alias} AS (SELECT mention_response_id, COUNT(*) AS total_brands FROM mention_response_brands GROUP BY mention_response_id)"

def _rank_score_expr(rank_col, total_col="rt.total_brands"):
    # Percentile-style rank score: (total - rank) / (total + 1), 0 when unranked/not mentioned.
    return f"(CASE WHEN {rank_col} IS NOT NULL AND {total_col} IS NOT NULL THEN ({total_col} - {rank_col})::numeric / ({total_col} + 1) ELSE 0 END)"