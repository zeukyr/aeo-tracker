"""
generate_recommendations() now only refreshes the two brand-signal engines
that have no notion of "which question" (concern + credibility). Per-question
recommendations come exclusively from the on-demand path
(api.recommendations.question_plan.generate_question_recommendation), driven
by a human picking questions in the dashboard - never auto-selected here.
"""

import api.recommendations.generation as gen


def _rec(problem="p", action_type=None, detail=None):
    return {
        "problem": problem, "action": "a", "priority": "medium",
        "school": None, "evidence": "e", "action_type": action_type,
        "target": "t", "segment": {}, "metric_impact": "citation_rate",
        "expected_direction": 1, "expected_magnitude": None,
        "effort": "M", "confidence": 0.7, "detail": detail,
    }


def test_generate_recommendations_combines_concern_and_credibility_only(monkeypatch):
    concern_recs = [_rec("concern issue", detail={"evidence": "already set"})]
    credibility_rec = _rec("credibility issue", detail={"evidence": "already set"})

    monkeypatch.setattr(gen, "build_concern_recommendations", lambda days: list(concern_recs))
    monkeypatch.setattr(gen, "build_credibility_recommendation", lambda days: credibility_rec)
    monkeypatch.setattr(gen, "apply_priority_ranking", lambda recs, days: recs)

    result = gen.generate_recommendations(days=30)

    assert result == concern_recs + [credibility_rec]


def test_generate_recommendations_omits_credibility_when_none(monkeypatch):
    monkeypatch.setattr(gen, "build_concern_recommendations", lambda days: [])
    monkeypatch.setattr(gen, "build_credibility_recommendation", lambda days: None)
    monkeypatch.setattr(gen, "apply_priority_ranking", lambda recs, days: recs)

    assert gen.generate_recommendations(days=30) == []
