"""
generate_reach_out_sweep (api/recommendations/reach_out_sweep.py): reach-out/
inclusion/community recs for every current losing question, independent of
that question's own branch (build/fix questions can still carry inclusion/
fan-out opportunities) and of the manual, cooldown-gated per-question flow.
"""
import api.queries.question_router as qr
from api.recommendations.reach_out_sweep import generate_reach_out_sweep
from tests.test_question_router import (
    facts, question, informational_winner, wire, forbid_scorecard,
)


def test_sweep_produces_reach_out_primary_tagged_as_sweep(monkeypatch):
    q = question(3, "is dog grooming worth it reddit")
    winners = [(facts("reddit.com", "community", status="not_fetched",
                      url=f"https://reddit.com/r/dogs/{i}"), 6) for i in range(3)]
    wire(monkeypatch, {3: winners})
    forbid_scorecard(monkeypatch)
    monkeypatch.setattr(qr, "get_losing_questions", lambda days=None: [q])

    recs = generate_reach_out_sweep()
    assert len(recs) == 1
    assert recs[0]["detail"]["question_plan"] == {
        "question_id": "3", "role": "primary", "emitter": "reach_out", "source": "sweep"}
    assert recs[0]["action_type"] == "community"


def test_sweep_yields_nothing_for_build_question_with_no_companion_opportunities(monkeypatch):
    # Plain guide winners: not roundup/directory (no inclusion opportunity),
    # not a non-ownable bucket (no fan-out target) - this question's actual
    # build rec is the manual flow's job, not the sweep's, so the sweep
    # should surface nothing for it at all.
    q = question(1, "how to become a dog groomer")
    winners = [(informational_winner(f"guide{i}.com"), 5) for i in range(3)]
    wire(monkeypatch, {1: winners})
    forbid_scorecard(monkeypatch)
    monkeypatch.setattr(qr, "get_losing_questions", lambda days=None: [q])

    assert generate_reach_out_sweep() == []


def test_sweep_skips_triage_questions(monkeypatch):
    q = question(7, "obscure question nothing cites")
    wire(monkeypatch, {7: []})
    monkeypatch.setattr(qr, "get_losing_questions", lambda days=None: [q])

    assert generate_reach_out_sweep() == []
