"""
classify_run_citations.py

Post-processing step that runs once after a full ingestion run completes.
Classifies citation URLs to the specific competitor they were cited for and
stores the results in competitor_citation_map.

For sole-competitor responses (only one competitor mentioned), all citations
are attributed directly with no LLM call.

For multi-competitor responses, one LLM call per response classifies URLs
using the full response text as context — so third-party authoritative sites
are attributed correctly based on where in the response they appear, not just
their domain name.

Usage:
    # Called automatically from main.py after each run
    classify_and_store(run_id)

    # Backfill all historical runs
    python -m src.classify_run_citations --backfill
"""

import sys

from src.database import get_connection
from src.logger import logger
from api.queries.citation_classifier import classify_citations_for_response


_FETCH_RESPONSES_SQL = """
    SELECT
        m.id,
        m.raw_response,
        m.citations,
        array_agg(DISTINCT b.brand_name)
            FILTER (WHERE b.brand_type = 'competitor') AS competitors
    FROM mention_responses m
    LEFT JOIN mention_response_brands b ON b.mention_response_id = m.id
    WHERE m.run_id = %s
      AND m.citations IS NOT NULL
      AND array_length(m.citations, 1) > 0
    GROUP BY m.id, m.raw_response, m.citations
    HAVING count(DISTINCT b.brand_name) FILTER (WHERE b.brand_type = 'competitor') > 0;
"""

_INSERT_SQL = """
    INSERT INTO competitor_citation_map (run_id, mention_response_id, competitor_name, url)
    VALUES (%s, %s, %s, %s)
    ON CONFLICT DO NOTHING;
"""

_FETCH_ALL_RUNS_SQL = """
    SELECT id FROM runs WHERE status = 'success' ORDER BY started_at;
"""

_RUN_ALREADY_CLASSIFIED_SQL = """
    SELECT 1 FROM competitor_citation_map WHERE run_id = %s LIMIT 1;
"""


def classify_and_store(run_id: int) -> None:
    """Classify and persist competitor→citation mappings for a single run."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(_FETCH_RESPONSES_SQL, (run_id,))
            responses = cur.fetchall()

    if not responses:
        logger.info(f"[classify] No eligible responses for run {run_id}")
        return

    rows: list[tuple] = []

    for response_id, raw_response, citations, competitors in responses:
        if not competitors:
            continue

        urls = [u for u in (citations or []) if u]
        if not urls:
            continue

        if len(competitors) == 1:
            # Unambiguous — no LLM needed
            for url in urls:
                rows.append((run_id, response_id, competitors[0], url))
        else:
            # Multiple competitors: use LLM with full response text for context
            attribution = classify_citations_for_response(
                competitors=competitors,
                urls=urls,
                response_text=raw_response or "",
            )
            for competitor, attributed_urls in attribution.items():
                for url in attributed_urls:
                    rows.append((run_id, response_id, competitor, url))

    if not rows:
        logger.info(f"[classify] No citation rows to store for run {run_id}")
        return

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.executemany(_INSERT_SQL, rows)
        conn.commit()

    logger.info(f"[classify] Stored {len(rows)} competitor-citation rows for run {run_id}")


def backfill_all_runs() -> None:
    """Process all successful runs that haven't been classified yet."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(_FETCH_ALL_RUNS_SQL)
            run_ids = [r[0] for r in cur.fetchall()]

    logger.info(f"[classify] Backfilling {len(run_ids)} runs")
    for run_id in run_ids:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(_RUN_ALREADY_CLASSIFIED_SQL, (run_id,))
                already_done = cur.fetchone() is not None

        if already_done:
            logger.info(f"[classify] Run {run_id} already classified, skipping")
            continue

        logger.info(f"[classify] Processing run {run_id}")
        try:
            classify_and_store(run_id)
        except Exception as e:
            logger.error(f"[classify] Failed on run {run_id}: {e}")


if __name__ == "__main__":
    if "--backfill" in sys.argv:
        backfill_all_runs()
    else:
        print("Usage: python -m src.classify_run_citations --backfill")
        sys.exit(1)
