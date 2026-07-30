"""
get_question_recommendation_status must ignore sweep-produced rows
(reach_out_sweep.py's auto reach-out/inclusion/community recs, tagged
detail.question_plan.source="sweep") when deciding whether a question's
manual build/fix "Generate" button is blocked - otherwise every losing
question would show falsely blocked_by="active_rec"/"cooldown" purely
because the sweep dropped an unrelated companion rec on it.
"""
from datetime import datetime, timezone

import api.recommendations.question_plan as qp


def _rec(status, source=None, generated_at=None):
    return {
        "status": status,
        "generated_at": generated_at or datetime.now(timezone.utc).isoformat(),
        "detail": {"question_plan": {"source": source}} if source else {},
    }


def test_sweep_only_recs_do_not_block_generation(monkeypatch):
    monkeypatch.setattr(qp, "_live_recs_for_question",
                        lambda qid: [_rec("proposed", "sweep")])
    status = qp.get_question_recommendation_status("q1")
    assert status["can_generate"] is True
    assert status["blocked_by"] is None


def test_active_sweep_rec_does_not_block_generation(monkeypatch):
    # An accepted/implemented sweep rec is still just a sweep rec - it must
    # not trip the active_rec gate meant for a committed build/fix plan.
    monkeypatch.setattr(qp, "_live_recs_for_question",
                        lambda qid: [_rec("accepted", "sweep")])
    status = qp.get_question_recommendation_status("q1")
    assert status["can_generate"] is True
    assert status["blocked_by"] is None


def test_active_on_demand_rec_still_blocks_alongside_sweep_rec(monkeypatch):
    monkeypatch.setattr(qp, "_live_recs_for_question",
                        lambda qid: [_rec("accepted", "on_demand"), _rec("proposed", "sweep")])
    status = qp.get_question_recommendation_status("q1")
    assert status["can_generate"] is False
    assert status["blocked_by"] == "active_rec"


def test_recent_on_demand_rec_still_gates_by_cooldown(monkeypatch):
    monkeypatch.setattr(qp, "_live_recs_for_question",
                        lambda qid: [_rec("proposed", "on_demand")])
    status = qp.get_question_recommendation_status("q1")
    assert status["can_generate"] is False
    assert status["blocked_by"] == "cooldown"


def test_rec_missing_source_key_still_gates_as_before(monkeypatch):
    # Pre-existing rows from before this change carry no question_plan.source
    # at all - they must keep gating exactly as they did previously.
    monkeypatch.setattr(qp, "_live_recs_for_question",
                        lambda qid: [_rec("proposed", source=None)])
    status = qp.get_question_recommendation_status("q1")
    assert status["can_generate"] is False
    assert status["blocked_by"] == "cooldown"
