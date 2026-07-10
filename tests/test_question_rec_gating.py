"""
Per-question generation gate (on-demand recs from the question view): an
active rec always blocks, a proposed rec blocks only inside the 30-day
cooldown, and the blocking rec is returned so the UI can navigate to it
instead. DB is stubbed at _latest_live_rec_for_question.
"""

from datetime import datetime, timedelta, timezone

import api.queries.recommendations_synthesis as rs


def _rec(status, generated_days_ago):
    generated = datetime.now(timezone.utc) - timedelta(days=generated_days_ago)
    return {"id": "rec-1", "status": status, "generated_at": generated.isoformat()}


def _wire(monkeypatch, rec):
    monkeypatch.setattr(rs, "_latest_live_rec_for_question", lambda qid: rec)


def test_no_live_rec_allows_generation(monkeypatch):
    _wire(monkeypatch, None)
    s = rs.get_question_recommendation_status("q1")
    assert s == {"recommendation": None, "can_generate": True,
                 "next_available_at": None, "blocked_by": None}


def test_active_rec_blocks_regardless_of_age(monkeypatch):
    _wire(monkeypatch, _rec("in_progress", generated_days_ago=120))
    s = rs.get_question_recommendation_status("q1")
    assert s["can_generate"] is False
    assert s["blocked_by"] == "active_rec"
    assert s["recommendation"]["id"] == "rec-1"


def test_fresh_proposed_rec_blocks_within_cooldown(monkeypatch):
    _wire(monkeypatch, _rec("proposed", generated_days_ago=5))
    s = rs.get_question_recommendation_status("q1")
    assert s["can_generate"] is False
    assert s["blocked_by"] == "cooldown"
    assert s["next_available_at"] is not None


def test_stale_proposed_rec_allows_regeneration(monkeypatch):
    _wire(monkeypatch, _rec("proposed", generated_days_ago=31))
    s = rs.get_question_recommendation_status("q1")
    assert s["can_generate"] is True
    assert s["blocked_by"] is None
    assert s["recommendation"]["id"] == "rec-1"   # still surfaced for context


def test_generate_returns_existing_rec_when_gated(monkeypatch):
    _wire(monkeypatch, _rec("proposed", generated_days_ago=5))
    out = rs.generate_question_recommendation("q1")
    assert out["generated"] is False
    assert out["recommendation"]["id"] == "rec-1"
    assert out["triage"] is None


def test_generate_reports_triage_when_router_declines(monkeypatch):
    _wire(monkeypatch, None)
    import api.queries.question_router as qr
    monkeypatch.setattr(qr, "build_question_recommendation",
                        lambda qid, days=None: (None, {"question_id": qid,
                                                       "reason": "no_cited_winners"}))
    out = rs.generate_question_recommendation("q1")
    assert out["generated"] is False
    assert out["recommendation"] is None
    assert out["triage"]["reason"] == "no_cited_winners"


def test_generate_reports_missing_mention_data(monkeypatch):
    _wire(monkeypatch, None)
    import api.queries.question_router as qr
    monkeypatch.setattr(qr, "build_question_recommendation",
                        lambda qid, days=None: (None, None))
    out = rs.generate_question_recommendation("q1")
    assert out["generated"] is False
    assert out["triage"]["reason"] == "no_mention_responses"


def test_generate_saves_and_returns_new_rec(monkeypatch):
    _wire(monkeypatch, None)
    import api.queries.question_router as qr
    rec = {"problem": "p", "segment": {"question_id": "q1"}}
    monkeypatch.setattr(qr, "build_question_recommendation",
                        lambda qid, days=None: (rec, None))
    saved = {}
    monkeypatch.setattr(rs, "save_question_recommendation",
                        lambda r, qid: saved.update(rec=r, qid=qid) or "new-id")
    monkeypatch.setattr(rs, "get_recommendation",
                        lambda rid: {"id": rid, "status": "proposed"})
    out = rs.generate_question_recommendation("q1")
    assert out["generated"] is True
    assert out["recommendation"]["id"] == "new-id"
    assert saved["rec"] is rec and saved["qid"] == "q1"
