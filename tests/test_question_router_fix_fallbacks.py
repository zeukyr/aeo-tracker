"""
On-demand fix-branch fallback order (build_question_recommendation):
  high-tier scorecard rec > verified inclusion opportunity > low-tier
  scorecard rec > triage with a precise reason + winner-coverage counts.
Routing, scorecard and inclusion builders are stubbed - this tests the
dispatch, not the engines.
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
            "detail": {"router": {"branch": "inclusion_opportunity"},
                       "opportunity": {"url": f"https://dir.example/{citations}",
                                       "citation_count": citations}}}


@pytest.fixture
def wire(monkeypatch):
    q = _q()
    monkeypatch.setattr(qr, "get_question_stats", lambda qid, days=None: q)
    monkeypatch.setattr(qr, "route_question", lambda q, days=None: _route(q))

    def set(scorecard=None, rec=None, inclusion=(), raise_scorecard=False):
        def _build(*a, **k):
            if raise_scorecard:
                raise RuntimeError("boom")
            return scorecard
        monkeypatch.setattr(qr, "build_scorecard", _build)
        monkeypatch.setattr(qr, "scorecard_to_recommendation", lambda sc: rec)
        monkeypatch.setattr(qr, "_inclusion_recs", lambda routes: list(inclusion))
    return set


def test_high_tier_scorecard_rec_wins_over_inclusion(wire):
    high = {"problem": "gap", "detail": {"evidence_tier": "high"}}
    wire(scorecard=_sc(), rec=high, inclusion=[_inclusion_rec(5)])
    rec, triage = qr.build_question_recommendation("q1")
    assert triage is None
    assert rec["problem"] == "gap"
    assert rec["detail"]["router"]["branch"] == "fix"


def test_inclusion_outranks_low_tier_scorecard_rec(wire):
    low = {"problem": "weak signal", "detail": {"evidence_tier": "low"}}
    wire(scorecard=_sc(), rec=low, inclusion=[_inclusion_rec(1), _inclusion_rec(3)])
    rec, triage = qr.build_question_recommendation("q1")
    assert triage is None
    assert rec["detail"]["opportunity"]["citation_count"] == 3  # strongest first


def test_low_tier_rec_survives_when_no_inclusion(wire):
    low = {"problem": "weak signal", "detail": {"evidence_tier": "low"}}
    wire(scorecard=_sc(), rec=low, inclusion=[])
    rec, triage = qr.build_question_recommendation("q1")
    assert triage is None
    assert rec["problem"] == "weak signal"
    assert rec["detail"]["router"]["branch"] == "fix"


def test_empty_result_triages_with_precise_reason_and_coverage(wire):
    wire(scorecard=_sc(), rec=None, inclusion=[])
    rec, triage = qr.build_question_recommendation("q1")
    assert rec is None
    assert triage["reason"] == "fix_true_feature_parity"
    assert triage["scorecard"]["winners_readable"] == 4
    assert triage["scorecard"]["winners_cited_total"] == 8
    assert triage["scorecard"]["winners_unreadable"][0]["status"] == "fetch_failed"


def test_insufficient_winner_data_reason_flows_through(wire):
    wire(scorecard=_sc(winners_total=1), rec=None, inclusion=[])
    rec, triage = qr.build_question_recommendation("q1")
    assert rec is None
    assert triage["reason"] == "fix_insufficient_winner_data"


def test_scorecard_failure_falls_back_to_inclusion_then_legacy_reason(wire):
    wire(raise_scorecard=True, inclusion=[_inclusion_rec(2)])
    rec, triage = qr.build_question_recommendation("q1")
    assert rec["detail"]["opportunity"]["citation_count"] == 2

    wire(raise_scorecard=True, inclusion=[])
    rec, triage = qr.build_question_recommendation("q1")
    assert rec is None
    assert triage["reason"] == "fix_no_feature_gaps"
    assert "scorecard" not in triage
