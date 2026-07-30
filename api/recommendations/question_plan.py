"""On-demand per-question recommendation plans (dashboard question view).

One question's action plan is every live rec covering it: the routed branch's
primary rec plus inclusion/community companions
(question_router.build_question_recommendations). This module owns the reads,
the per-question generation gate (same 30-day cooldown as the batch), and the
question-scoped supersession that keeps regeneration from clobbering the rest
of the live batch.
"""

from datetime import datetime, timedelta, timezone

import uuid

from psycopg2.extras import Json

from api.db import get_connection
from api.recommendations.store import (
    ACTIVE_STATUSES,
    GENERATION_COOLDOWN_DAYS,
    _REC_SELECT,
    _insert_rec,
    _rec_dict,
    get_recommendation,
)


def _live_recs_for_question(question_id):
    """
    Every rec that currently covers this question - the question's action
    plan. Covers = the rec's segment targets the question, OR the question
    was folded into the rec's dedup group (detail.router.source_questions).
    Committed (active) recs sort first, then the plan's primary before its
    companions, then newest-first. Superseded recs never appear - history.
    """
    qid = str(question_id)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(f"""
                {_REC_SELECT}
                WHERE status != 'superseded'
                  AND (segment->>'question_id' = %s
                       OR (detail->'router'->'source_questions') @> %s)
                ORDER BY CASE WHEN status IN %s THEN 0 ELSE 1 END,
                         CASE WHEN detail->'question_plan'->>'role' = 'primary' THEN 0 ELSE 1 END,
                         generated_at DESC
            """, (qid, Json([{"question_id": qid}]), ACTIVE_STATUSES))
            rows = cur.fetchall()
    return [_rec_dict(r) for r in rows]


def get_question_recommendations(question_id):
    """Public read for the question's live action plan (API surface)."""
    return _live_recs_for_question(question_id)


def _is_sweep_produced(rec):
    return ((rec.get("detail") or {}).get("question_plan") or {}).get("source") == "sweep"


def get_question_recommendation_status(question_id, cooldown_days=GENERATION_COOLDOWN_DAYS):
    """
    Per-question analogue of get_generation_status: whether an on-demand
    build/fix rec may be generated for this question, and the live rec that
    blocks it (so the UI can navigate there instead). Blocked by: an active
    rec (committed work never gets a duplicate), or a proposed rec younger
    than the same 30-day cooldown the batch uses.

    Sweep-produced rows (reach_out_sweep.py's auto reach-out/inclusion/
    community recs, tagged detail.question_plan.source="sweep") are excluded
    from this gating: they land on EVERY losing question regardless of that
    question's own branch, so a fix/build question would otherwise show
    falsely blocked_by="cooldown"/"active_rec" purely because an unrelated
    sweep rec landed on it moments ago - locking out the one thing this
    button is actually for. get_question_recommendations (the plan-page
    read) is unaffected - a human still sees the full plan including sweep
    rows, only the generate-button gate ignores them. Rows without a
    question_plan.source key (pre-existing data from before this change)
    are NOT sweep-produced, so they keep gating exactly as before.
    """
    recs = _live_recs_for_question(question_id)
    if not recs:
        return {"recommendation": None, "recommendations": [], "count": 0,
                "can_generate": True, "next_available_at": None, "blocked_by": None}
    base = {"recommendation": recs[0], "recommendations": recs, "count": len(recs)}
    gating = [r for r in recs if not _is_sweep_produced(r)]
    if not gating:
        return {**base, "can_generate": True, "next_available_at": None, "blocked_by": None}
    if any(r["status"] in ACTIVE_STATUSES for r in gating):
        return {**base, "can_generate": False,
                "next_available_at": None, "blocked_by": "active_rec"}
    newest = max(r["generated_at"] for r in gating)
    generated_at = datetime.fromisoformat(newest)
    if generated_at.tzinfo is None:
        generated_at = generated_at.replace(tzinfo=timezone.utc)
    next_available_at = generated_at + timedelta(days=cooldown_days)
    can_generate = datetime.now(timezone.utc) >= next_available_at
    return {**base, "can_generate": can_generate,
            "next_available_at": next_available_at.isoformat(),
            "blocked_by": None if can_generate else "cooldown"}


def save_question_recommendations(recs, question_id):
    """
    Insert one question's on-demand build/fix plan under ONE shared batch_id.
    Supersession is scoped to the question: prior untouched (proposed) recs
    covering the same question are archived - matched by segment OR by
    source_questions containment, the same predicate _live_recs_for_question
    reads with (segment alone missed on-demand fix recs, whose segment is
    topic-grained). The rest of the live batch is untouched (unlike
    save_recommendations). No triage rows are written: the batch triage
    queue must keep reflecting the latest full batch.

    Excludes sweep-produced rows (detail.question_plan.source="sweep") from
    supersession - those are reach_out_sweep.py's territory, regenerated on
    its own cadence, and this question's build/fix plan sharing the same
    question_id must not wipe them out.
    """
    qid = str(question_id)
    batch_id = str(uuid.uuid4())
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE recommendations SET status = 'superseded'
                WHERE status = 'proposed'
                  AND (segment->>'question_id' = %s
                       OR (detail->'router'->'source_questions') @> %s)
                  AND COALESCE(detail->'question_plan'->>'source', 'on_demand') != 'sweep'
            """, (qid, Json([{"question_id": qid}])))
            rec_ids = [_insert_rec(cur, rec, batch_id) for rec in recs]
        conn.commit()
    return [str(r) for r in rec_ids]


def generate_question_recommendation(question_id, days=None):
    """
    On-demand generation for one question, gated per question by the same
    30-day cooldown as the batch. Builds the question's full action plan
    (primary branch rec + inclusion opportunities + community fan-out).
    Returns:
      {"generated": True,  "recommendations": [<saved recs>]}       - new plan
      {"generated": False, "recommendations": [<existing live>]}    - gated:
          navigate to the plan that already covers the question
      {"generated": False, "recommendations": [], "triage": {...}}  - the
          router couldn't action it; triage.reason says why
    "recommendation" (singular, the plan's first rec) is kept for callers of
    the one-rec era.
    """
    from api.queries.question_router import build_question_recommendations

    status = get_question_recommendation_status(question_id)
    if not status["can_generate"]:
        return {"generated": False, "recommendation": status["recommendation"],
                "recommendations": status["recommendations"],
                "triage": None, "blocked_by": status["blocked_by"],
                "next_available_at": status["next_available_at"]}

    recs, triage_entry = build_question_recommendations(question_id, days)
    if not recs:
        if triage_entry is None:
            triage_entry = {"question_id": str(question_id),
                            "reason": "no_mention_responses"}
        else:
            triage_entry = {**triage_entry,
                            "question_id": str(triage_entry.get("question_id"))}
        return {"generated": False, "recommendation": None,
                "recommendations": [], "triage": triage_entry}

    rec_ids = save_question_recommendations(recs, question_id)
    saved = [get_recommendation(rid) for rid in rec_ids]
    return {"generated": True, "recommendation": saved[0], "recommendations": saved}
