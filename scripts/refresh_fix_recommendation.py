"""
Force-refresh one scorecard-based ("fix") recommendation whose stored
problem/action/detail.scorecard was generated before a content fix to
geo_features.json or scorecard.py (e.g. the neutral_tone prompt now
correctly rejecting second-person "you'll learn..." copy as marketing
voice, not neutral third-person). page_facts.py's semantic-feature pass
is never durably cached (scorecard.py's _semantic_features cache_key only
lives on the in-memory dict for the one build_scorecard call that computed
it) - the staleness lives entirely in the stored `recommendations` row,
which is a point-in-time snapshot the dashboard reads back verbatim.

Mirrors question_router.py's `build_question_recommendations` fix branch
EXACTLY (route_question -> build_scorecard -> scorecard_to_recommendation
-> attach detail.router via _router_detail), rather than calling
build_scorecard/scorecard_to_recommendation directly - a fix rec without
detail.router renders as a flat card (RecommendationCard.jsx's two-pane
Feature-diff / Structural-metrics / "Show reasoning" section is gated on
`rec.detail?.router` being present). Only this one rec is touched - unlike
question_plan.generate_question_recommendation, which regenerates the
WHOLE question's plan (reddit/certifying-body companions too).

Usage:
    python -m scripts.refresh_fix_recommendation <rec_id>
"""

import sys
import uuid

from api.db import get_connection
from api.queries.question_router import get_question_stats, route_question, _router_detail
from api.queries.scorecard import (
    CANDIDATE_POOL, build_scorecard, scorecard_to_recommendation,
)
from api.queries.page_facts import get_pages_facts
from api.queries.cited_urls import get_question_cited_urls
from api.recommendations.store import _insert_rec, get_recommendation, update_recommendation_status


def _question_id_for(old):
    """The old rec's segment is topic-scoped (scorecard_to_recommendation
    always sets segment.dimension='topic'), so the question_id has to come
    from detail.scorecard.question matched against the questions table."""
    question_text = old["detail"]["scorecard"]["question"]
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM questions WHERE question = %s", (question_text,))
            row = cur.fetchone()
    return row[0] if row else None


def main():
    if len(sys.argv) != 2:
        print("usage: python -m scripts.refresh_fix_recommendation <rec_id>")
        return
    rec_id = sys.argv[1]

    old = get_recommendation(rec_id)
    if old is None:
        print(f"no such recommendation: {rec_id}")
        return
    if old.get("action_type") != "technical" or not old.get("detail", {}).get("scorecard"):
        print(f"rec {rec_id} isn't a scorecard/fix recommendation "
              f"(action_type={old.get('action_type')!r})")
        return
    if old["status"] != "proposed":
        print(f"rec {rec_id} is status={old['status']!r}, not 'proposed' - "
              "refusing to supersede committed/measured work automatically")
        return

    question_id = _question_id_for(old)
    if question_id is None:
        print("couldn't resolve this rec's question_id - can't route it")
        return

    q = get_question_stats(question_id)
    if q is None:
        print(f"question {question_id} has no mention responses in range")
        return
    route = route_question(q, None)
    if route["branch"] == "triage":
        print(f"router now says triage ({route.get('reason')}) - not a fix branch anymore")
        return
    if route["branch"] != "fix":
        print(f"router now routes this question to branch={route['branch']!r}, not 'fix' - "
              "the old fix rec would need a different kind of replacement, not this script")
        return

    # Exactly question_router.py's fix branch (build_question_recommendations,
    # route["branch"] == "fix" arm): a wider, independently-fetched pool than
    # route["winners"] (sized for the citation-share vote, not the scorecard).
    scorecard_cited = get_question_cited_urls(q["question_id"], None, limit=CANDIDATE_POOL)
    counts = {c["url"]: c["count"] for c in scorecard_cited}
    scorecard_winners = get_pages_facts([c["url"] for c in scorecard_cited])
    for f in scorecard_winners:
        f["citation_count"] = counts.get(f["url"], 0)
    sc = build_scorecard(q["topic"] or q["question"], route["qc_url"],
                          question=q["question"], days=None,
                          winner_facts=scorecard_winners)
    new_rec = scorecard_to_recommendation(sc)

    if new_rec is None:
        print("scorecard no longer produces an actionable recommendation "
              "(true parity / unreadable page / insufficient winners) - "
              f"superseding {rec_id} with no replacement")
        update_recommendation_status(rec_id, "superseded")
        return

    new_rec["detail"]["router"] = _router_detail(route)

    with get_connection() as conn:
        with conn.cursor() as cur:
            new_id = _insert_rec(cur, new_rec, str(uuid.uuid4()))
        conn.commit()
    update_recommendation_status(rec_id, "superseded")

    print(f"\nsuperseded {rec_id} -> new rec {new_id}\n")
    print("OLD action:", old["action"])
    print("\nNEW action:", new_rec["action"])


if __name__ == "__main__":
    main()
