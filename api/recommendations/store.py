"""Persistence and lifecycle for recommendation records.

Owns the recommendations + recommendation_triage tables: batch saves with the
non-destructive supersession lifecycle, status updates (which start the
measurement clock), the triage queue, the generation cooldown, and every read
the API serves. Batch assembly lives in :mod:`generation`, ranking in
:mod:`prioritization`, and the on-demand per-question path in
:mod:`question_plan`.
"""

import uuid
from datetime import datetime, timedelta, timezone

from psycopg2.extras import Json

from src.logger import logger
from api.db import get_connection

# Minimum gap between generate_recommendations() runs. Recommendations are a
# periodic report, not an on-demand toy - this keeps a batch's worth of work
# stable long enough to act on before the next one supersedes it.
GENERATION_COOLDOWN_DAYS = 30

# A rec counts as "active" (committed work, immune to supersession/dedup-skip)
# once it's past the untouched-suggestion stage.
ACTIVE_STATUSES = (
    "accepted", "in_progress", "implemented",
    "measuring", "validated", "failed", "inconclusive",
)


def _work_stream(action_type):
    """
    Which dashboard tab a rec belongs to (question-router plan §5.8):
      on_page   - "Improve Existing Pages": fix a QC page that exists but
                  engines skip. action_type 'technical' is set by the fix
                  branch, which only fires when the page provably exists.
      outreach  - "Outreach & Earn": earn presence on third-party sources QC
                  can't own (reach-out branch + inclusion opportunities).
      strategic - "Strategic Growth": build new owned content (content /
                  strategy, or unclassified).
    """
    if action_type == "technical":
        return "on_page"
    if action_type in ("outreach", "citation", "community"):
        return "outreach"
    return "strategic"


def _segment_key(rec):
    """(dimension, value, metric_impact) - identifies 'the same underlying problem'
    for dedup against active recs, independent of exact wording."""
    segment = rec.get("segment") or {}
    return (segment.get("dimension"), segment.get("value"), rec.get("metric_impact"))


_INSERT_REC_SQL = """
    INSERT INTO recommendations (
        problem, action, priority, school, evidence,
        action_type, target, segment, metric_impact,
        expected_direction, expected_magnitude, effort, confidence,
        batch_id, detail
    )
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    RETURNING id
"""


def _insert_rec(cur, rec, batch_id):
    cur.execute(_INSERT_REC_SQL, (
        rec["problem"],
        rec["action"],
        rec["priority"],
        rec.get("school"),
        rec.get("evidence"),
        rec.get("action_type"),
        rec.get("target"),
        Json(rec["segment"]) if rec.get("segment") is not None else None,
        rec.get("metric_impact"),
        rec.get("expected_direction"),
        rec.get("expected_magnitude"),
        rec.get("effort"),
        rec.get("confidence"),
        batch_id,
        Json(rec["detail"]) if rec.get("detail") is not None else None,
    ))
    return cur.fetchone()[0]


def save_recommendations(recommendations):
    """
    Appends a new batch. Never deletes anything - this is the core of the
    non-destructive lifecycle:
      1. Any rec already committed to (status in ACTIVE_STATUSES) is left
         untouched, and new candidates covering the same segment+metric are
         skipped so in-progress work doesn't get a duplicate "new" suggestion.
      2. All previously `proposed` (untouched) recs are archived to
         `superseded` - kept for history, just no longer shown as live
         suggestions. A rec becomes immune to this the moment it's Accepted
         or marked Implemented, since it's no longer `proposed`.
      3. Surviving candidates are inserted as `proposed`, tagged with one
         fresh batch_id shared across the whole call.
    """
    batch_id = str(uuid.uuid4())
    inserted, skipped = 0, 0

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT segment, metric_impact FROM recommendations WHERE status IN %s",
                (ACTIVE_STATUSES,)
            )
            active_keys = {(r[0].get("dimension") if r[0] else None,
                             r[0].get("value") if r[0] else None,
                             r[1]) for r in cur.fetchall()}

            cur.execute("UPDATE recommendations SET status = 'superseded' WHERE status = 'proposed'")

            for rec in recommendations:
                key = _segment_key(rec)
                if key != (None, None, None) and key in active_keys:
                    skipped += 1
                    logger.info(f"Skipping duplicate recommendation for active segment {key}: {rec.get('problem', '')[:80]}")
                    continue

                _insert_rec(cur, rec, batch_id)
                inserted += 1
        conn.commit()

    return {"batch_id": batch_id, "inserted": inserted, "skipped": skipped}


def get_generation_status(cooldown_days=GENERATION_COOLDOWN_DAYS):
    """
    Whether a new batch may be generated right now, gated by a cooldown since
    the last batch - keeps generation to a periodic-report cadence instead of
    an on-demand action that can be spammed.
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT MAX(generated_at) FROM recommendations")
            last_generated_at = cur.fetchone()[0]

    if last_generated_at is None:
        return {"last_generated_at": None, "next_available_at": None, "can_generate": True}

    next_available_at = last_generated_at + timedelta(days=cooldown_days)
    return {
        "last_generated_at": last_generated_at.isoformat(),
        "next_available_at": next_available_at.isoformat(),
        "can_generate": datetime.now(timezone.utc) >= next_available_at,
    }


def update_recommendation_status(rec_id, status, implemented_at=None):
    with get_connection() as conn:
        with conn.cursor() as cur:
            if implemented_at is not None:
                cur.execute(
                    "UPDATE recommendations SET status = %s, implemented_at = %s WHERE id = %s",
                    (status, implemented_at, rec_id)
                )
            else:
                cur.execute(
                    "UPDATE recommendations SET status = %s WHERE id = %s",
                    (status, rec_id)
                )
        conn.commit()

    # Implementation starts the measurement clock: snapshot the trailing-
    # window baseline now, so the post-window lift has something honest to
    # compare against (question-router plan §8).
    if status == "implemented":
        try:
            from api.queries.recommendation_measurement import record_baseline
            record_baseline(rec_id)
        except Exception as e:
            logger.warning(f"Baseline recording failed for rec {rec_id}: {e}")


_REC_SELECT = """
    SELECT id, generated_at, problem, action, priority, school, evidence, status,
           action_type, target, segment, metric_impact,
           expected_direction, expected_magnitude, effort, confidence,
           implemented_at, measurement_window_days, batch_id, detail,
           baseline_value, baseline_sample_n, measured_at, outcome
    FROM recommendations
"""


def _rec_dict(r):
    return {
        "id": str(r[0]),
        "generated_at": str(r[1]),
        "problem": r[2],
        "action": r[3],
        "priority": r[4],
        "school": r[5],
        "evidence": r[6],
        "status": r[7],
        "action_type": r[8],
        "target": r[9],
        "segment": r[10],
        "metric_impact": r[11],
        "expected_direction": r[12],
        "expected_magnitude": float(r[13]) if r[13] is not None else None,
        "effort": r[14],
        "confidence": float(r[15]) if r[15] is not None else None,
        "implemented_at": str(r[16]) if r[16] is not None else None,
        "measurement_window_days": r[17],
        "batch_id": str(r[18]) if r[18] is not None else None,
        "detail": r[19],
        "baseline_value": float(r[20]) if r[20] is not None else None,
        "baseline_sample_n": r[21],
        "measured_at": str(r[22]) if r[22] is not None else None,
        "outcome": r[23],
        "work_stream": _work_stream(r[8]),
    }


def get_saved_recommendations(include_superseded=False):
    where = "" if include_superseded else "WHERE status != 'superseded'"
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(f"{_REC_SELECT} {where} ORDER BY generated_at DESC, priority ASC;")
            rows = cur.fetchall()
    return [_rec_dict(r) for r in rows]


def get_recommendation(rec_id):
    """One rec by id (any status - a focused card view may target a rec the
    default list filters out), or None."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(f"{_REC_SELECT} WHERE id = %s", (rec_id,))
            row = cur.fetchone()
    return _rec_dict(row) if row else None
