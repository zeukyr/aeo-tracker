"""
One-time cleanup after the competitor-classification fix in page_facts:
cached pages stamped page_type='competitor' by a brand-token DOMAIN match
(page_type_source='domain') despite having been successfully read get their
content classified properly - the noisy LLM-extracted brand list ("Purdue",
"unity.edu", "Pet Care Ins") had labeled job boards, universities and
insurers' editorial pages as rivals.

Reuses the cached title/headings/content_excerpt - no refetching. Rows whose
content genuinely reads as a rival provider's own page ("provider") keep
page_type='competitor', now with page_type_source='llm'. Idempotent: after
one pass no ('competitor', 'domain', 'ok') rows remain.

    python -m migrations.reclassify_competitor_pages
"""
from api.db import get_connection
from api.queries.page_facts import _classify_editorial_llm, _upsert_fact


def reclassify():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT facts FROM page_facts
                WHERE page_type = 'competitor'
                  AND page_type_source = 'domain'
                  AND status = 'ok'
            """)
            rows = [r[0] for r in cur.fetchall()]

        changed = 0
        for facts in rows:
            page_type, source = _classify_editorial_llm(
                facts["url"], facts.get("title"),
                facts.get("headings") or [], facts.get("content_excerpt") or "",
            )
            if source == "fallback":
                print(f"  LLM unavailable for {facts['url']} - left as competitor")
                continue
            if page_type != facts["page_type"]:
                changed += 1
                print(f"  {facts['url']}: competitor -> {page_type}")
            facts["page_type"], facts["page_type_source"] = page_type, source
            _upsert_fact(facts, conn=conn)
        conn.commit()

    print(f"reclassified {len(rows)} fetched competitor-by-domain rows; {changed} changed type")


if __name__ == "__main__":
    reclassify()
