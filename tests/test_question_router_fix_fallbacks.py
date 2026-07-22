"""
On-demand fix-branch plan assembly (build_question_recommendations):
the scorecard rec (high OR low tier) leads the plan, verified inclusion
opportunities COEXIST as companions (strongest-cited first), and an empty
plan triages with a precise reason + winner-coverage counts. Routing,
scorecard and inclusion builders are stubbed - this tests the dispatch,
not the engines.
"""

import pytest

import api.queries.question_router as qr


def _q():
    return {"question_id": "q1", "question": "event planning online course",
            "topic": "Course Discovery", "school": "QC Event Planning",
            "qc_share": 0.0, "n_responses": 8, "n_citations": 28}


def _route(q):
    return {"branch": "fix", "reason": "qc_page_same_kind_still_loses",
            "question": q, "winners": [], "vote": {"voters": 4, "buckets": {}},
            "dominant": ("competitor", 0.85),
            "qc_url": "https://qc.example/page", "genre_mismatch": None}


def _sc(**over):
    sc = {"qc_readable": True, "winners_total": 4, "winners_cited_total": 8,
          "winners_unreadable": [{"url": "https://a.example", "domain": "a.example",
                                  "status": "fetch_failed", "citation_count": 3}]}
    sc.update(over)
    return sc


def _inclusion_rec(citations):
    return {"problem": f"inclusion {citations}", "action": "pitch", "priority": "high",
            "target": f"https://dir.example/{citations}",
            "detail": {"router": {"branch": "inclusion_opportunity"},
                       "opportunity": {"url": f"https://dir.example/{citations}",
                                       "citation_count": citations}}}


@pytest.fixture
def wire(monkeypatch):
    q = _q()
    monkeypatch.setattr(qr, "get_question_stats", lambda qid, days=None: q)
    monkeypatch.setattr(qr, "route_question", lambda q, days=None: _route(q))
    # route_question is stubbed above (its own get_question_cited_urls/
    # get_pages_facts calls never run), but build_question_recommendations
    # independently re-fetches a wider candidate pool for the scorecard - see
    # question_router.py's fix branch. build_scorecard below ignores
    # winner_facts entirely, so these just need to not hit a real DB.
    monkeypatch.setattr(qr, "get_question_cited_urls", lambda qid, days=None, **kw: [])
    monkeypatch.setattr(qr, "get_pages_facts", lambda urls, **kw: [])

    def set(scorecard=None, rec=None, inclusion=(), raise_scorecard=False):
        def _build(*a, **k):
            if raise_scorecard:
                raise RuntimeError("boom")
            return scorecard
        monkeypatch.setattr(qr, "build_scorecard", _build)
        monkeypatch.setattr(qr, "scorecard_to_recommendation", lambda sc: rec)
        monkeypatch.setattr(qr, "_inclusion_recs", lambda routes: list(inclusion))
    return set


def test_scorecard_rec_leads_and_inclusion_coexists(wire):
    high = {"problem": "gap", "detail": {"evidence_tier": "high"}}
    wire(scorecard=_sc(), rec=high, inclusion=[_inclusion_rec(5)])
    recs, triage = qr.build_question_recommendations("q1")
    assert triage is None
    assert len(recs) == 2
    assert recs[0]["problem"] == "gap"
    assert recs[0]["detail"]["router"]["branch"] == "fix"
    assert recs[0]["detail"]["question_plan"]["role"] == "primary"
    assert recs[1]["detail"]["question_plan"] == {
        "question_id": "q1", "role": "companion", "emitter": "inclusion_opportunity"}


def test_low_tier_rec_still_leads_over_inclusions(wire):
    # Coexistence, not fallback: a low-tier scorecard rec is the plan's lead
    # AND every inclusion opportunity ships alongside, strongest-cited first.
    low = {"problem": "weak signal", "detail": {"evidence_tier": "low"}}
    wire(scorecard=_sc(), rec=low, inclusion=[_inclusion_rec(1), _inclusion_rec(3)])
    recs, triage = qr.build_question_recommendations("q1")
    assert triage is None
    assert [r["problem"] for r in recs] == ["weak signal", "inclusion 3", "inclusion 1"]
    assert recs[1]["detail"]["opportunity"]["citation_count"] == 3  # strongest first


def test_low_tier_rec_survives_when_no_inclusion(wire):
    low = {"problem": "weak signal", "detail": {"evidence_tier": "low"}}
    wire(scorecard=_sc(), rec=low, inclusion=[])
    recs, triage = qr.build_question_recommendations("q1")
    assert triage is None
    assert len(recs) == 1
    assert recs[0]["problem"] == "weak signal"
    assert recs[0]["detail"]["router"]["branch"] == "fix"


def test_empty_result_triages_with_precise_reason_and_coverage(wire):
    wire(scorecard=_sc(), rec=None, inclusion=[])
    recs, triage = qr.build_question_recommendations("q1")
    assert recs == []
    assert triage["reason"] == "fix_true_feature_parity"
    assert triage["scorecard"]["winners_readable"] == 4
    assert triage["scorecard"]["winners_cited_total"] == 8
    assert triage["scorecard"]["winners_unreadable"][0]["status"] == "fetch_failed"


def test_insufficient_winner_data_reason_flows_through(wire):
    wire(scorecard=_sc(winners_total=1), rec=None, inclusion=[])
    recs, triage = qr.build_question_recommendations("q1")
    assert recs == []
    assert triage["reason"] == "fix_insufficient_winner_data"


def test_scorecard_failure_leaves_inclusion_leading_the_plan(wire):
    wire(raise_scorecard=True, inclusion=[_inclusion_rec(2)])
    recs, triage = qr.build_question_recommendations("q1")
    assert triage is None
    assert recs[0]["detail"]["opportunity"]["citation_count"] == 2
    assert recs[0]["detail"]["question_plan"]["role"] == "primary"

    wire(raise_scorecard=True, inclusion=[])
    recs, triage = qr.build_question_recommendations("q1")
    assert recs == []
    assert triage["reason"] == "fix_no_feature_gaps"
    assert "scorecard" not in triage
