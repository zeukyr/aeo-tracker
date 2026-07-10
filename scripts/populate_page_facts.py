"""
Bulk pre-populate the page_facts cache for every distinct cited URL - fetch,
extract, and classify deterministically, WITHOUT paying an LLM completion per
page. Pages the domain rules and heuristics can't classify are stored
provisionally (page_type_source "deferred"); the LLM tiebreak runs lazily
later, from the cached fetch, the first time a normal get_page_facts read
touches the row - i.e. only for URLs that actually become router winners.

Usage:
    python -m scripts.populate_page_facts            # fill gaps + retry stale failures
    python -m scripts.populate_page_facts --force    # refetch everything
"""

import sys
from collections import Counter

from api.db import get_connection
from api.queries.page_facts import get_pages_facts


def cited_urls():
    """Every distinct URL any engine has cited, from both response tables."""
    query = """
        SELECT DISTINCT u FROM (
            SELECT unnest(citations) AS u FROM mention_responses
            UNION ALL
            SELECT unnest(citations) AS u FROM sentiment_responses
        ) x WHERE u IS NOT NULL AND u <> '';
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query)
            return sorted(r[0] for r in cur.fetchall())


def main():
    force = "--force" in sys.argv
    urls = cited_urls()
    print(f"populating page_facts for {len(urls)} cited URLs "
          f"(force={force}, LLM tiebreak deferred)")

    facts = get_pages_facts(urls, force=force, defer_llm=True)

    by_source = Counter(f.get("page_type_source") for f in facts)
    by_type = Counter(f.get("page_type") for f in facts)
    by_status = Counter(f.get("status") for f in facts)
    print(f"\npage_type_source: {dict(by_source.most_common())}")
    print(f"page_type:        {dict(by_type.most_common())}")
    print(f"status:           {dict(by_status.most_common())}")
    deferred = by_source.get("deferred", 0)
    print(f"\n{deferred} rows deferred - they upgrade lazily (one LLM call each, "
          f"no refetch) when the router first reads them.")


if __name__ == "__main__":
    main()
