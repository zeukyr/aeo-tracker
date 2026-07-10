"""
Deterministic recommendation synthesis.

Every rec family is produced by its own deterministic engine — the LLM no
longer authors recommendations at all (it only fills classification slots
inside the builders: page-type classification, semantic feature checks,
concern-rebuttal confirmation — all cached, single-fact, quote-enforced):

  - Fix / Build / Reach-out:         question_router.build_router_recommendations
                                     (per-question: winners classified first,
                                     one branch per losing question; what it
                                     can't confidently action goes to a
                                     visible triage list)
  - Concern objection-response:      concern_engine.build_concern_recommendations
  - Credibility:                     credibility.build_credibility_recommendation
  - Competitive losses:              a priority/evidence input, not a rec family
                                     (score multiplier in _apply_priority_ranking)

Because nothing here is free LLM prose, the old defense apparatus (fabrication
guard, LLM judge, schema normalization, coverage-diagnosis correction,
bucket-scope filter, supersession of LLM recs by deterministic ones) is gone —
every claim in a rec already traces to a query or a fetched, verified page fact.
"""

import uuid
from datetime import datetime, timedelta, timezone
from psycopg2.extras import Json
from src.logger import logger
from api.queries.recommendation_signals import get_competitive_loss_topics
from api.queries.tab1_strategy import strategic_evidence
from api.queries.question_router import build_router_recommendations
from api.queries.concern_engine import build_concern_recommendations
from api.queries.credibility import build_credibility_recommendation

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


# Priority is a RELATIVE rank within the batch, not an absolute label - when
# nearly every topic has >= 3 competitive losses, a blanket "bump to high"
# makes every card high and the field carries no information. Quartiles:
_PRIORITY_TOP_QUARTILE = 0.25   # strongest quarter -> high
_PRIORITY_BOTTOM_QUARTILE = 0.25  # weakest quarter -> low


def _rec_rank_signals(rec):
    """
    (family, volume, urgency) for one rec. Volume is normalized WITHIN a
    family before ranking, because the units differ: router recs count
    citations on the question, concern recs count responses raising the
    concern. Urgency is 0..1 - how badly QC is losing that surface.
    """
    d = rec.get("detail") or {}
    router = d.get("router") or {}
    if router.get("n_citations") is not None:
        volume = router["n_citations"] + 3 * len(router.get("grouped_questions") or [])
        return "router", volume, 1.0 - (router.get("qc_share") or 0.0)
    concern = d.get("concern") or {}
    if concern.get("count") is not None:
        return "concern", concern["count"], concern.get("share_not_positive") or 0.5
    return "other", None, 0.5


def _rank_reason(rank, n, family, pct, rec, loss):
    """
    The driver behind a rec's priority, in the reader's units - shown on the
    card so two identical-looking builds explain their different ranks.
    """
    d = rec.get("detail") or {}
    if family == "router":
        router = d.get("router") or {}
        vol = f"{router.get('n_citations')} citations at stake on this question"
        grouped = router.get("grouped_questions") or []
        if grouped:
            vol += f" (+{len(grouped)} near-duplicate question(s) folded in)"
        urg = f"QC is cited in {round((router.get('qc_share') or 0.0) * 100)}% of its responses"
    elif family == "concern":
        concern = d.get("concern") or {}
        vol = f"the concern was raised {concern.get('count')}x"
        urg = (f"{round((concern.get('share_not_positive') or 0.5) * 100)}% of those "
               f"responses land not-positive")
    else:
        return f"Ranked {rank}/{n} in this batch (no volume signal - mid-pack by default)."
    reason = (f"Ranked {rank}/{n} in this batch: {vol} - >= {round(pct * 100)}% of "
              f"{family} recs on volume - and {urg}.")
    if loss:
        reason += " Boosted x1.25: competitors repeatedly win this topic."
    return reason


def _apply_priority_ranking(recommendations, days=None):
    """
    Assigns priority by evidence-strength rank within the batch: volume
    percentile within the rec's family x urgency, with competitive losses as
    a score MULTIPLIER (the compounding-evidence rule) rather than a blanket
    label bump. Top quartile -> high, bottom quartile -> low, rest medium.
    Deterministic: ties break on raw volume, then target.

    The rank inputs and a human-readable driver are written to
    detail.priority_rank, so the card can SHOW why one rec outranks another
    instead of presenting the label as a verdict from nowhere.
    """
    if not recommendations:
        return recommendations
    try:
        losses = get_competitive_loss_topics(days, min_losses=3)
    except Exception as e:
        logger.warning(f"Competitive loss lookup failed: {e}")
        losses = {}

    by_family = {}
    signals = []
    for rec in recommendations:
        family, volume, urgency = _rec_rank_signals(rec)
        signals.append((family, volume, urgency))
        if volume is not None:
            by_family.setdefault(family, []).append(volume)

    scored = []
    for rec, (family, volume, urgency) in zip(recommendations, signals):
        if volume is None:
            pct = 0.5                      # no volume signal: mid-pack by default
        else:
            peers = by_family[family]
            pct = (sum(1 for v in peers if v <= volume)) / len(peers)
        score = pct * urgency
        # Router recs are question-segmented (R6); their topic for the
        # competitive-loss lookup lives in detail.router.
        seg = rec.get("segment") or {}
        topic = (seg.get("value") if seg.get("dimension") == "topic"
                 else ((rec.get("detail") or {}).get("router") or {}).get("topic"))
        loss = losses.get(topic) if topic else None
        if loss:
            score *= 1.25
            note = (f" Compounding: competitors ({', '.join(loss['competitors'][:3])}) appear on "
                    f"{loss['losses']} responses in this topic where QC is absent.")
            rec["evidence"] = (rec.get("evidence") or "") + note
        scored.append((score, volume or 0, rec, family, pct, urgency, bool(loss)))

    scored.sort(key=lambda t: (-t[0], -t[1], str(t[2].get("target"))))
    n = len(scored)
    n_high = max(1, round(n * _PRIORITY_TOP_QUARTILE))
    n_low = max(1, round(n * _PRIORITY_BOTTOM_QUARTILE)) if n >= 4 else 0
    for i, (score, volume, rec, family, pct, urgency, loss) in enumerate(scored):
        if i < n_high:
            rec["priority"] = "high"
        elif i >= n - n_low:
            rec["priority"] = "low"
        else:
            rec["priority"] = "medium"
        detail = rec.get("detail") or {}
        detail["priority_rank"] = {
            "rank": i + 1,
            "of": n,
            "score": round(score, 3),
            "volume": volume,
            "volume_percentile": round(pct, 2),
            "urgency": round(urgency, 2),
            "loss_multiplier": 1.25 if loss else 1.0,
            "reason": _rank_reason(i + 1, n, family, pct, rec, loss),
        }
        rec["detail"] = detail
    return recommendations


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


def save_recommendations(recommendations, triage=None):
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
    The router's triage list (§5.9) is stored alongside, same batch_id -
    the dashboard shows the latest batch's queue.
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

            for t in (triage or []):
                qc_share = t.get("qc_share") or 0.0
                n_citations = t.get("n_citations") or 0
                cur.execute("""
                    INSERT INTO recommendation_triage (
                        batch_id, question_id, question, topic, school,
                        reason, build_candidate, qc_share, n_citations,
                        rank_score, detail
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    batch_id,
                    t.get("question_id"),
                    t["question"],
                    t.get("topic"),
                    t.get("school"),
                    t["reason"],
                    bool(t.get("build_candidate")),
                    qc_share,
                    n_citations,
                    round(n_citations * (1.0 - qc_share), 2),
                    Json({k: t.get(k) for k in
                          ("dominant_source", "dominant_share", "vote",
                           "qc_url", "genre_mismatch", "winners")}),
                ))
        conn.commit()

    return {"batch_id": batch_id, "inserted": inserted, "skipped": skipped,
            "triaged": len(triage or [])}


def get_triage():
    """
    The latest batch's triage queue, strongest candidates first (rank_score =
    citation volume x how badly QC is losing). Empty list if no batch has
    stored triage yet.
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT question_id, question, topic, school, reason,
                       build_candidate, qc_share, n_citations, rank_score,
                       detail, generated_at
                FROM recommendation_triage
                WHERE batch_id = (
                    SELECT batch_id FROM recommendation_triage
                    ORDER BY generated_at DESC LIMIT 1
                )
                ORDER BY rank_score DESC, n_citations DESC
            """)
            rows = cur.fetchall()
    return [
        {
            "question_id": str(r[0]) if r[0] else None,
            "question": r[1], "topic": r[2], "school": r[3], "reason": r[4],
            "build_candidate": r[5],
            "qc_share": float(r[6]) if r[6] is not None else None,
            "n_citations": r[7],
            "rank_score": float(r[8]) if r[8] is not None else None,
            "detail": r[9], "generated_at": r[10],
        }
        for r in rows
    ]


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


# ─────────────────────────────────────────────────────────────────────────────
# On-demand per-question generation (dashboard question view)
# ─────────────────────────────────────────────────────────────────────────────

def _latest_live_rec_for_question(question_id):
    """
    The rec that currently covers this question, or None. Covers = the rec's
    segment targets the question, OR the question was folded into the rec's
    dedup group (detail.router.source_questions). Committed (active) recs win
    over untouched proposed ones; ties break newest-first. Superseded recs
    never block - they're history.
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
                         generated_at DESC
                LIMIT 1
            """, (qid, Json([{"question_id": qid}]), ACTIVE_STATUSES))
            row = cur.fetchone()
    return _rec_dict(row) if row else None


def get_question_recommendation_status(question_id, cooldown_days=GENERATION_COOLDOWN_DAYS):
    """
    Per-question analogue of get_generation_status: whether an on-demand rec
    may be generated for this question, and the live rec that blocks it (so
    the UI can navigate there instead). Blocked by: an active rec (committed
    work never gets a duplicate), or a proposed rec younger than the same
    30-day cooldown the batch uses.
    """
    rec = _latest_live_rec_for_question(question_id)
    if rec is None:
        return {"recommendation": None, "can_generate": True,
                "next_available_at": None, "blocked_by": None}
    if rec["status"] in ACTIVE_STATUSES:
        return {"recommendation": rec, "can_generate": False,
                "next_available_at": None, "blocked_by": "active_rec"}
    generated_at = datetime.fromisoformat(rec["generated_at"])
    if generated_at.tzinfo is None:
        generated_at = generated_at.replace(tzinfo=timezone.utc)
    next_available_at = generated_at + timedelta(days=cooldown_days)
    can_generate = datetime.now(timezone.utc) >= next_available_at
    return {"recommendation": rec, "can_generate": can_generate,
            "next_available_at": next_available_at.isoformat(),
            "blocked_by": None if can_generate else "cooldown"}


def save_question_recommendation(rec, question_id):
    """
    Insert ONE on-demand rec under its own batch_id. Supersession is scoped
    to the question: only prior untouched (proposed) recs whose segment
    targets the same question are archived - the rest of the live batch is
    untouched (unlike save_recommendations). No triage rows are written: the
    batch triage queue must keep reflecting the latest full batch.
    """
    batch_id = str(uuid.uuid4())
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE recommendations SET status = 'superseded'
                WHERE status = 'proposed' AND segment->>'question_id' = %s
            """, (str(question_id),))
            rec_id = _insert_rec(cur, rec, batch_id)
        conn.commit()
    return str(rec_id)


def generate_question_recommendation(question_id, days=None):
    """
    On-demand generation for one question, gated per question by the same
    30-day cooldown as the batch. Returns:
      {"generated": True,  "recommendation": <saved rec>}          - new rec
      {"generated": False, "recommendation": <existing live rec>}  - gated:
          navigate to the rec that already covers the question
      {"generated": False, "recommendation": None, "triage": {...}} - the
          router couldn't action it; triage.reason says why
    """
    from api.queries.question_router import build_question_recommendation

    status = get_question_recommendation_status(question_id)
    if not status["can_generate"]:
        return {"generated": False, "recommendation": status["recommendation"],
                "triage": None, "blocked_by": status["blocked_by"],
                "next_available_at": status["next_available_at"]}

    rec, triage_entry = build_question_recommendation(question_id, days)
    if rec is None:
        if triage_entry is None:
            triage_entry = {"question_id": str(question_id),
                            "reason": "no_mention_responses"}
        else:
            triage_entry = {**triage_entry,
                            "question_id": str(triage_entry.get("question_id"))}
        return {"generated": False, "recommendation": None, "triage": triage_entry}

    rec_id = save_question_recommendation(rec, question_id)
    return {"generated": True, "recommendation": get_recommendation(rec_id)}


def generate_recommendations(days=None):
    """
    Assembles the full batch from the deterministic engines. Returns
    (recommendations, triage): the triage list (§5.9) is a first-class output,
    persisted with the batch and rendered as the dashboard's "Needs triage"
    queue - never silently dropped.
    """
    # The question router owns fix, build and reach-out (per-question winners,
    # winner-type classified BEFORE any comparison or leaf builder runs), plus
    # the verified inclusion opportunities across all routed winners.
    # (build_tab1_recommendations is retired: the build/reach-out branches
    # cover its rec families at question grain.)
    recommendations, triage = build_router_recommendations(days)
    if triage:
        reasons = {}
        for t in triage:
            reasons[t["reason"]] = reasons.get(t["reason"], 0) + 1
        logger.info(f"Router triage: {len(triage)} losing question(s) not auto-actioned: {reasons}")

    # Concern + credibility recs (Phase 7): concerns run the objection-response
    # engine (taxonomy -> QC-content check -> state), credibility keys the
    # citation contrast on the sentiment verdicts.
    recommendations = recommendations + build_concern_recommendations(days)
    cred_rec = build_credibility_recommendation(days)
    if cred_rec:
        recommendations.append(cred_rec)

    # Attach truthful citation evidence (what AI cites for the topic + QC's count)
    # to strategic recs so the Tab 1 card can show it. Tab 2 recs already carry a
    # scorecard in `detail`; leave those untouched. Runs BEFORE priority ranking,
    # which writes detail.priority_rank onto every rec - "has detail" must still
    # mean "already carries its own evidence" here.
    for rec in recommendations:
        if rec.get("detail") or rec.get("action_type") == "technical":
            continue
        seg = rec.get("segment") or {}
        try:
            ev = strategic_evidence(seg, school=rec.get("school"))
            if ev:
                rec["detail"] = {"evidence": ev}
        except Exception as e:
            logger.warning(f"strategic_evidence failed for {seg}: {e}")

    # Priority = evidence-strength rank within the batch (competitive losses
    # multiply the score; they are not a rec family and never blanket-bump).
    # Also writes the rank driver to detail.priority_rank for the card.
    recommendations = _apply_priority_ranking(recommendations, days)
    return recommendations, triage
