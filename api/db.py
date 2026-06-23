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