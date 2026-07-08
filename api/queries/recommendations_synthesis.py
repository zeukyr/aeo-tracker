"""
Deterministic recommendation synthesis.

Every rec family is produced by its own deterministic engine — the LLM no
longer authors recommendations at all (it only fills classification slots
inside the builders: page-type classification, semantic feature checks,
concern-rebuttal confirmation — all cached, single-fact, quote-enforced):

  - Tab 2 "Improve Existing Pages":  tab2_scorecard.build_tab2_recommendations
  - Tab 1 "Strategic Growth":        tab1_strategy.build_tab1_recommendations
  - Concern objection-response:      concern_engine.build_concern_recommendations
  - Credibility:                     credibility.build_credibility_recommendation
  - Competitive losses:              a priority/evidence input, not a rec family
                                     (_apply_competitive_boost)

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
from api.queries.tab1_strategy import build_tab1_recommendations, strategic_evidence
from api.queries.tab2_scorecard import build_tab2_recommendations
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


def _apply_competitive_boost(recommendations, days=None):
    """
    Competitive losses are a PRIORITY input, not a rec family. The plan's
    "compounding evidence" rule, computed: a topic-scoped rec whose topic is
    also a competitive loss (rivals appear while QC is invisible) gets bumped
    one priority level, with the loss count appended to evidence.
    """
    try:
        losses = get_competitive_loss_topics(days, min_losses=3)
    except Exception as e:
        logger.warning(f"Competitive loss lookup failed: {e}")
        return recommendations
    bump = {"low": "medium", "medium": "high"}
    for rec in recommendations:
        seg = rec.get("segment") or {}
        loss = losses.get(seg.get("value")) if seg.get("dimension") == "topic" else None
        if not loss:
            continue
        if rec.get("priority") in bump:
            rec["priority"] = bump[rec["priority"]]
        note = (f" Compounding: competitors ({', '.join(loss['competitors'][:3])}) appear on "
                f"{loss['losses']} responses in this topic where QC is absent.")
        rec["evidence"] = (rec.get("evidence") or "") + note
    return recommendations


def _work_stream(action_type):
    """
    Which dashboard tab a rec belongs to (docs/ai/recommendation-two-tab-plan.md):
      on_page   - "Improve Existing Pages": fix a QC page that exists but engines
                  skip. action_type 'technical' is set by the Tab 2 scorecard
                  builder, which only fires when the sitemap shows the page exists.
      strategic - "Strategic Growth": build new owned content or earn external
                  presence (content / citation / outreach, or unclassified).
    """
    return "on_page" if action_type == "technical" else "strategic"


def _segment_key(rec):
    """(dimension, value, metric_impact) - identifies 'the same underlying problem'
    for dedup against active recs, independent of exact wording."""
    segment = rec.get("segment") or {}
    return (segment.get("dimension"), segment.get("value"), rec.get("metric_impact"))


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

                cur.execute("""
                    INSERT INTO recommendations (
                        problem, action, priority, school, evidence,
                        action_type, target, segment, metric_impact,
                        expected_direction, expected_magnitude, effort, confidence,
                        batch_id, detail
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
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

def get_saved_recommendations(include_superseded=False):
    where = "" if include_superseded else "WHERE status != 'superseded'"
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT id, generated_at, problem, action, priority, school, evidence, status,
                       action_type, target, segment, metric_impact,
                       expected_direction, expected_magnitude, effort, confidence,
                       implemented_at, measurement_window_days, batch_id, detail
                FROM recommendations
                {where}
                ORDER BY generated_at DESC, priority ASC;
            """)
            rows = cur.fetchall()
    return [
        {
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
            "work_stream": _work_stream(r[8]),
        }
        for r in rows
    ]


def generate_recommendations(days=None):
    """
    Assembles the full batch from the deterministic engines. Order within the
    batch is builder order; ranking/prioritization beyond the per-rec priority
    field is left to the frontend tabs.
    """
    # Tab 2 recs are built deterministically from the scorecard (page + cited-page
    # comparison + section edits), so they name the page and the missing sections
    # concretely.
    recommendations = build_tab2_recommendations(days)

    # Tab 1 recs are likewise deterministic (verified inclusion gates,
    # build-vs-earn composition, genre mismatches, per-intent coverage).
    recommendations = recommendations + build_tab1_recommendations(days)

    # Concern + credibility recs (Phase 7): concerns run the objection-response
    # engine (taxonomy -> QC-content check -> state), credibility keys the
    # citation contrast on the sentiment verdicts.
    recommendations = recommendations + build_concern_recommendations(days)
    cred_rec = build_credibility_recommendation(days)
    if cred_rec:
        recommendations.append(cred_rec)

    # Competitive losses boost priority on topic recs; they are not a rec family.
    recommendations = _apply_competitive_boost(recommendations, days)

    # Attach truthful citation evidence (what AI cites for the topic + QC's count)
    # to strategic recs so the Tab 1 card can show it. Tab 2 recs already carry a
    # scorecard in `detail`; leave those untouched.
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
    return recommendations
