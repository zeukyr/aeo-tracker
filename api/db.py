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