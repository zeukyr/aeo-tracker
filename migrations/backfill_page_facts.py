"""
One-time backfill: load the legacy api/knowledge/page_facts.json cache into the
page_facts table (migrations/004_page_facts_cache.sql).

Idempotent - upserts by url, so re-running is safe. Run AFTER applying 004:

    python -m migrations.backfill_page_facts

Once the row count matches and generation runs clean off the table, the JSON
file can be deleted.
"""
import os
import json

from api.db import get_connection
from api.queries.page_facts import _upsert_fact

_JSON_PATH = os.path.join(os.path.dirname(__file__), "..", "api", "knowledge", "page_facts.json")


def backfill():
    with open(_JSON_PATH, "r", encoding="utf-8") as f:
        pages = json.load(f).get("pages", {})

    ok = 0
    conn = get_connection()                   # one connection for the whole load
    try:
        for url, facts in pages.items():
            facts.setdefault("url", url)      # legacy entries all carry it, but be safe
            try:
                _upsert_fact(facts, conn=conn)
                ok += 1
            except Exception as e:            # one bad row shouldn't abort the load
                conn.rollback()
                print(f"  skip {url}: {e}")
    finally:
        conn.close()
    print(f"backfilled {ok}/{len(pages)} page-facts rows from {os.path.abspath(_JSON_PATH)}")
    return ok


if __name__ == "__main__":
    backfill()
