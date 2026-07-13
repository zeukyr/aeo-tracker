"""
One-time cleanup: rekey page_facts rows to their normalized URL
(src/parsing/urls.normalize_url) so ?utm_source=... variants of one page share
one cache row - the read layer now normalizes before every lookup, so
raw-keyed rows would be permanent cache misses.

When several rows collapse onto one normalized key, the best row wins:
status == "ok" beats a failure, then the most recent fetched_at. Losing rows
are deleted. Idempotent - already-normalized rows map to themselves.

    python -m migrations.normalize_page_facts_urls
"""
from api.db import get_connection
from api.queries.page_facts import _upsert_fact
from src.parsing.urls import normalize_url


def _better(a, b):
    """The row worth keeping: readable content first, then freshest."""
    a_ok = a.get("status") == "ok"
    b_ok = b.get("status") == "ok"
    if a_ok != b_ok:
        return a if a_ok else b
    return a if (a.get("fetched_at") or "") >= (b.get("fetched_at") or "") else b


def migrate():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT url, facts FROM page_facts")
            rows = cur.fetchall()

        keep = {}
        for url, facts in rows:
            key = normalize_url(url)
            facts["url"] = key
            keep[key] = _better(keep[key], facts) if key in keep else facts

        stale = [url for url, _f in rows if url not in keep]
        with conn.cursor() as cur:
            for url in stale:
                cur.execute("DELETE FROM page_facts WHERE url = %s", (url,))
        for facts in keep.values():
            _upsert_fact(facts, conn=conn)
        conn.commit()

    print(f"page_facts: {len(rows)} rows -> {len(keep)} normalized keys "
          f"({len(stale)} raw-keyed rows removed)")
    return len(rows), len(keep)


if __name__ == "__main__":
    migrate()
