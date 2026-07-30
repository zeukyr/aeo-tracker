"""
Per-question generation gate (on-demand recs from the question view): an
active rec anywhere in the question's plan blocks, a proposed plan blocks
only inside the 30-day cooldown, and the blocking plan is returned so the
UI can navigate to it instead. DB is stubbed at _live_recs_for_question.
"""

from datetime import datetime, timedelta, timezone

import api.recommendations.question_plan as rs


def _rec(status, generated_days_ago, rec_id="rec-1"):
    generated = datetime.now(timezone.utc) - timedelta(days=generated_days_ago)
    return {"id": rec_id, "status": status, "generated_at": generated.isoformat()}


def _wire(monkeypatch, recs):
    monkeypatch.setattr(rs, "_live_recs_for_question", lambda qid: list(recs))


def test_no_live_recs_allow_generation(monkeypatch):
    _wire(monkeypatch, [])
    s = rs.get_question_recommendation_status("q1")
    assert s == {"recommendation": None, "recommendations": [], "count": 0,
                 "can_generate": True, "next_available_at": None, "blocked_by": None}


def test_any_active_rec_blocks_regardless_of_age(monkeypatch):
    # One committed companion is enough - regeneration must not supersede a
    # plan someone is mid-way through implementing.
    _wire(monkeypatch, [_rec("proposed", 120), _rec("in_progress", 120, "rec-2")])
    s = rs.get_question_recommendation_status("q1")
    assert s["can_generate"] is False
    assert s["blocked_by"] == "active_rec"
    assert s["count"] == 2
    assert s["recommendation"]["id"] == "rec-1"


def test_fresh_proposed_plan_blocks_within_cooldown(monkeypatch):
    _wire(monkeypatch, [_rec("proposed", 5)])
    s = rs.get_question_recommendation_status("q1")
    assert s["can_generate"] is False
    assert s["blocked_by"] == "cooldown"
    assert s["next_available_at"] is not None


def test_cooldown_keys_off_the_newest_rec(monkeypatch):
    _wire(monkeypatch, [_rec("proposed", 45), _rec("proposed", 5, "rec-2")])
    s = rs.get_question_recommendation_status("q1")
    assert s["can_generate"] is False
    assert s["blocked_by"] == "cooldown"


def test_stale_proposed_plan_allows_regeneration(monkeypatch):
    _wire(monkeypatch, [_rec("proposed", 31)])
    s = rs.get_question_recommendation_status("q1")
    assert s["can_generate"] is True
    assert s["blocked_by"] is None
    assert s["recommendation"]["id"] == "rec-1"   # still surfaced for context


def test_generate_returns_existing_plan_when_gated(monkeypatch):
    _wire(monkeypatch, [_rec("proposed", 5), _rec("proposed", 5, "rec-2")])
    out = rs.generate_question_recommendation("q1")
    assert out["generated"] is False
    assert out["recommendation"]["id"] == "rec-1"
    assert [r["id"] for r in out["recommendations"]] == ["rec-1", "rec-2"]
    assert out["triage"] is None


def test_generate_reports_triage_when_router_declines(monkeypatch):
    _wire(monkeypatch, [])
    import api.queries.question_router as qr
    monkeypatch.setattr(qr, "build_question_recommendations",
                        lambda qid, days=None: ([], {"question_id": qid,
                                                     "reason": "no_cited_winners"}))
    out = rs.generate_question_recommendation("q1")
    assert out["generated"] is False
    assert out["recommendation"] is None
    assert out["recommendations"] == []
    assert out["triage"]["reason"] == "no_cited_winners"


def test_generate_reports_missing_mention_data(monkeypatch):
    _wire(monkeypatch, [])
    import api.queries.question_router as qr
    monkeypatch.setattr(qr, "build_question_recommendations",
                        lambda qid, days=None: ([], None))
    out = rs.generate_question_recommendation("q1")
    assert out["generated"] is False
    assert out["triage"]["reason"] == "no_mention_responses"


def test_generate_saves_and_returns_the_whole_plan(monkeypatch):
    _wire(monkeypatch, [])
    import api.queries.question_router as qr
    plan = [{"problem": "p1", "segment": {"question_id": "q1"}},
            {"problem": "p2", "segment": {"question_id": "q1"}}]
    monkeypatch.setattr(qr, "build_question_recommendations",
                        lambda qid, days=None: (plan, None))
    saved = {}
    monkeypatch.setattr(rs, "save_question_recommendations",
                        lambda recs, qid: saved.update(recs=recs, qid=qid)
                        or ["id-1", "id-2"])
    monkeypatch.setattr(rs, "get_recommendation",
                        lambda rid: {"id": rid, "status": "proposed"})
    out = rs.generate_question_recommendation("q1")
    assert out["generated"] is True
    assert out["recommendation"]["id"] == "id-1"
    assert [r["id"] for r in out["recommendations"]] == ["id-1", "id-2"]
    assert saved["recs"] is plan and saved["qid"] == "q1"
