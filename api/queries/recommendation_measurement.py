"""
Per-recommendation lift measurement (question-router plan §8; the closed-loop
fields shipped in migrations/001 but were never computed until now).

Lifecycle:
  status -> implemented   record_baseline(): the metric in the rec's segment
                          over the trailing window UP TO implemented_at, plus
                          sample size. Called from update_recommendation_status.
  window elapses          measure_due_recommendations(): the same metric over
                          the window AFTER implemented_at -> lift = post -
                          baseline, written to `outcome` and appended to
                          recommendation_outcomes (history), status advanced to
                          validated / failed / inconclusive.

Lift is target-only (post minus baseline in the rec's own segment) - the
honest first cut; a control-segment diff-in-diff can replace the verdict rule
later without touching the stored history. Surfaced PER RECOMMENDATION - this
is the only signal that says whether a rec actually worked, so it is never
aggregated away.

Scheduling: the daily tracker workflow runs
`python -m api.queries.recommendation_measurement` after the snapshot.
"""

from psycopg2.extras import Json

from src.logger import logger
from api.db import get_connection
from api.queries.recommendation_signals import _segment_clause_params

# Which recommendations metrics we can measure from mention_responses. Recs
# with other metrics (e.g. positive_sentiment_rate) keep outcome = NULL until
# a sentiment measurement lands.
_METRIC_EXPRS = {
    "mention_rate":  "AVG(CASE WHEN m.qc_mentioned THEN 1 ELSE 0 END)",
    "citation_rate": "AVG(CASE WHEN m.qc_cited THEN 1 ELSE 0 END)",
}

# Below this many responses on either side of the window the verdict is
# inconclusive regardless of the lift's sign.
MIN_SAMPLE_N = 5

# |lift| below this (in rate points) is noise, not a verdict.
LIFT_DEADBAND = 0.05


def _segment_metric(cur, segment, metric, start_expr, end_expr, params_prefix):
    """(value, n) for one metric in one segment over [start, end)."""
    expr = _METRIC_EXPRS.get(metric)
    if expr is None:
        return None, 0
    seg_clause, seg_params = _segment_clause_params(segment)
    cur.execute(f"""
        SELECT {expr}, COUNT(*)
        FROM mention_responses m
        JOIN questions q ON q.id = m.question_id
        WHERE m.created_at >= {start_expr} AND m.created_at < {end_expr}
        {seg_clause}
    """, params_prefix + seg_params)
    value, n = cur.fetchone()
    return (float(value) if value is not None else None), n


def record_baseline(rec_id):
    """
    Snapshot the trailing-window metric for one rec at implementation time.
    Idempotent - re-running overwrites with the same-window value.
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT segment, metric_impact, implemented_at,
                       COALESCE(measurement_window_days, 30)
                FROM recommendations WHERE id = %s
            """, (rec_id,))
            row = cur.fetchone()
            if not row:
                return None
            segment, metric, implemented_at, window = row
            if implemented_at is None:
                return None
            value, n = _segment_metric(
                cur, segment, metric,
                "%s::timestamptz - make_interval(days => %s)", "%s::timestamptz",
                [implemented_at, window, implemented_at])
            cur.execute("""
                UPDATE recommendations
                SET baseline_value = %s, baseline_sample_n = %s
                WHERE id = %s
            """, (value, n, rec_id))
        conn.commit()
    logger.info(f"Baseline for rec {rec_id}: {metric}={value} (n={n})")
    return {"baseline_value": value, "baseline_sample_n": n}


def _verdict(baseline, post, expected_direction, baseline_n, post_n):
    if baseline is None or post is None or baseline_n < MIN_SAMPLE_N or post_n < MIN_SAMPLE_N:
        return "inconclusive"
    lift = post - baseline
    if abs(lift) < LIFT_DEADBAND:
        return "inconclusive"
    return "validated" if lift * (expected_direction or 1) > 0 else "failed"


def measure_due_recommendations():
    """
    Measure every implemented/measuring rec whose window has elapsed: compute
    the post-window metric, write lift to `outcome`, append the history row,
    and advance status. Returns the measured recs' summaries.
    """
    measured = []
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, segment, metric_impact, expected_direction,
                       implemented_at, COALESCE(measurement_window_days, 30),
                       baseline_value, baseline_sample_n
                FROM recommendations
                WHERE status IN ('implemented', 'measuring')
                  AND implemented_at IS NOT NULL
                  AND implemented_at + make_interval(days => COALESCE(measurement_window_days, 30)) <= now()
            """)
            due = cur.fetchall()

            for (rec_id, segment, metric, direction, implemented_at,
                 window, baseline, baseline_n) in due:
                if baseline is None:
                    # implemented before baseline recording existed - backfill
                    value, n = _segment_metric(
                        cur, segment, metric,
                        "%s::timestamptz - make_interval(days => %s)", "%s::timestamptz",
                        [implemented_at, window, implemented_at])
                    baseline, baseline_n = value, n
                    cur.execute("UPDATE recommendations SET baseline_value = %s, "
                                "baseline_sample_n = %s WHERE id = %s",
                                (baseline, baseline_n, rec_id))

                post, post_n = _segment_metric(
                    cur, segment, metric,
                    "%s::timestamptz", "%s::timestamptz + make_interval(days => %s)",
                    [implemented_at, implemented_at, window])

                lift = (post - baseline) if (post is not None and baseline is not None) else None
                verdict = _verdict(baseline, post, direction, baseline_n or 0, post_n)
                outcome = {
                    "baseline_value": baseline, "post_value": post,
                    "lift": round(lift, 4) if lift is not None else None,
                    "baseline_sample_n": baseline_n, "post_sample_n": post_n,
                    "verdict": verdict,
                }
                cur.execute("""
                    UPDATE recommendations
                    SET outcome = %s, measured_at = now(), status = %s
                    WHERE id = %s
                """, (Json(outcome), verdict, rec_id))
                cur.execute("""
                    INSERT INTO recommendation_outcomes (
                        recommendation_id, metric, segment,
                        baseline_value, post_value, target_delta,
                        baseline_sample_n, post_sample_n, verdict
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (rec_id, metric, Json(segment) if segment else None,
                      baseline, post, lift, baseline_n, post_n, verdict))
                measured.append({"id": str(rec_id), "metric": metric, **outcome})
                logger.info(f"Measured rec {rec_id}: lift={outcome['lift']} -> {verdict}")
        conn.commit()
    return measured


if __name__ == "__main__":
    import io, sys, json
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    results = measure_due_recommendations()
    print(json.dumps({"measured": len(results), "results": results}, indent=1, default=str))
