"""
Auto reach-out sweep: reach-out/inclusion/community recs for EVERY current
losing question, regenerated on the same cadence as the concern/credibility
signals (api.recommendations.generation) rather than gated behind a human's
per-question "Generate" click.

Why this is split out from the manual per-question flow
(question_router.build_question_recommendations): that flow is deliberately
expensive and human-gated (LLM scorecard / format-aware build prose,
30-day-per-question cooldown) because it commits to a specific build/fix
plan. Reach-out (primary + inclusion opportunities + community fan-out) is
comparatively cheap - outreach_feasibility() is a registry lookup or a regex
over already-classified page text, no LLM call - and inclusion/fanout
opportunities exist independently of whichever branch a question's OWN vote
lands on (a build-branch question can still cite a directory that lists
rivals and never QC). So it's safe, and useful, to recompute for every
losing question on every refresh rather than wait for a human to pick that
specific question.

Persistence is intentionally NOT api.recommendations.store.save_recommendations:
that function supersedes every currently-`proposed` recommendation
system-wide, which would silently wipe out live, human-generated build/fix
proposed recs on every refresh. save_reach_out_recommendations below scopes
its supersession to exactly this sweep's own rows.
"""

import uuid

from src.logger import logger
from api.db import get_connection
from api.recommendations.store import _insert_rec

# detail.router.branch values this sweep owns. Chosen over action_type
# because action_type values ("citation", "community") are also used by
# api.queries.competitive_content's cross-question patterns (tagged
# detail.router.branch = "competitive_pattern") - scoping supersession by
# action_type would clobber those unrelated rows. concern_engine.py never
# sets detail.router at all, so it's unaffected either way.
_SWEEP_BRANCHES = ("reach_out", "inclusion_opportunity", "reach_out_fanout")


def generate_reach_out_sweep(days=None):
    """
    Reach-out-family recs for every current losing question. Inclusion/
    fan-out fire regardless of the question's own branch; the reach-out
    branch's own primary rec fires only when that's the branch. Triage
    outcomes are skipped - `no_cited_winners` triage carries no winners to
    build companions from, and the rest (fragmented_field,
    insufficient_voters, feasibility_unknown, reputation_no_channel) are
    exactly the cases the router couldn't action with confidence, which
    applies to reach-out too.
    """
    from api.queries.question_router import (
        get_losing_questions, route_question, _reach_out_rec,
        _companion_recs, _community_key, _tag_question_plan,
    )

    recs = []
    for q in get_losing_questions(days):
        route = route_question(q, days)
        if route["branch"] == "triage":
            continue

        taken_keys = set()
        question_recs = []
        if route["branch"] == "reach_out":
            question_recs.append(_reach_out_rec(route, [route]))
            taken_keys.add(_community_key(route.get("feasibility_target")))
        question_recs.extend(_companion_recs(route, taken_keys))

        recs.extend(_tag_question_plan(
            question_recs, q["question_id"], route["branch"],
            has_primary=(route["branch"] == "reach_out"), source="sweep",
        ))
    return recs


def _active_targets(cur):
    """(question_id, target) pairs already committed to (status in
    ACTIVE_STATUSES) among this sweep's own prior rows - re-sweeping must
    not drop a fresh duplicate `proposed` card next to one a human already
    accepted."""
    from api.recommendations.store import ACTIVE_STATUSES
    cur.execute(
        """
        SELECT segment->>'question_id', target FROM recommendations
        WHERE status IN %s AND detail->'router'->>'branch' IN %s
        """,
        (ACTIVE_STATUSES, _SWEEP_BRANCHES),
    )
    return {(r[0], r[1]) for r in cur.fetchall()}


def save_reach_out_recommendations(recs):
    """
    Batch-replace ONLY this sweep's own territory: prior `proposed` rows
    tagged detail.router.branch in _SWEEP_BRANCHES are superseded (fix/build
    rows, and concern/credibility/competitive-content rows, never carry
    those tags - see _SWEEP_BRANCHES' docstring - so they're untouched
    regardless of status). Candidates whose (question_id, target) already
    has an ACTIVE rec are skipped, same non-destructive intent as
    store.save_recommendations' active-segment skip, just keyed on the
    question+target pair since one question can carry several simultaneous
    reach-out targets.
    """
    batch_id = str(uuid.uuid4())
    inserted, skipped = 0, 0

    with get_connection() as conn:
        with conn.cursor() as cur:
            active = _active_targets(cur)

            cur.execute(
                "UPDATE recommendations SET status = 'superseded' "
                "WHERE status = 'proposed' AND detail->'router'->>'branch' IN %s",
                (_SWEEP_BRANCHES,),
            )

            for rec in recs:
                segment = rec.get("segment") or {}
                key = (segment.get("question_id"), rec.get("target"))
                if key[0] is not None and key in active:
                    skipped += 1
                    logger.info(f"Skipping duplicate reach-out rec for active target {key}: "
                                f"{rec.get('problem', '')[:80]}")
                    continue
                _insert_rec(cur, rec, batch_id)
                inserted += 1
        conn.commit()

    return {"batch_id": batch_id, "inserted": inserted, "skipped": skipped}
