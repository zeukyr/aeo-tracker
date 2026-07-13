"""
Evidence-graded scorecard recs: scorecard_to_recommendation no longer returns
a binary rec-or-None. Verified checklist gaps over a sufficient sample are
tier "high"; thin samples, sub-threshold gaps and the emergent LLM pattern
are tier "low"; None is reserved for the three empty states named precisely
by scorecard_triage_reason. Unreadable cited winners must be disclosed, never
silently dropped from the denominator. All inputs are constructed scorecards -
no DB, no LLM.
"""

import api.queries.tab2_scorecard as ts


def _feat(fid, qc_has, wp, n, weight="medium"):
    frac = wp / n if n else 0
    prevalence = "most" if frac >= 0.6 else ("some" if frac >= 0.3 else "few")
    return {
        "id": fid, "label": fid.replace("_", " "), "geo_weight": weight,
        "winners_present": wp, "winners_total": n,
        "winners_pct": round(100 * wp / n) if n else None,
        "prevalence": prevalence, "qc_has": qc_has,
        "recommend": prevalence == "most" and not qc_has and weight != "low",
    }


def _sc(features, n=4, qc_readable=True, unreadable=(), excluded=(),
        emergent_insight="", emergent_edit=""):
    edits = ([emergent_edit] if emergent_edit else []) + [
        f"Add {f['label']}" for f in features if f["recommend"]]
    return {
        "topic": "Course Discovery",
        "question": "event planning online course",
        "qc_url": "https://www.qceventplanning.com/online-event-courses/event-planning",
        "qc_title": "QC page",
        "qc_readable": qc_readable,
        "winners": [],
        "winners_total": n,
        "winners_cited_total": n + len(unreadable) + len(excluded),
        "winners_unreadable": list(unreadable),
        "winners_excluded": list(excluded),
        "sufficient": n >= ts.MIN_WINNERS,
        "features": features,
        "emergent_insight": emergent_insight,
        "emergent_edit": emergent_edit,
        "suggested_edits": edits,
    }


def test_verified_gap_over_sufficient_sample_is_high_tier():
    sc = _sc([_feat("career_outcomes", qc_has=False, wp=3, n=4, weight="high"),
              _feat("faq_section", qc_has=True, wp=4, n=4)])
    rec = ts.scorecard_to_recommendation(sc)
    assert rec is not None
    assert rec["detail"]["evidence_tier"] == "high"
    assert rec["confidence"] == 0.7
    assert "3/4 (75%)" in rec["evidence"]
    grade = rec["detail"]["evidence_grade"]
    assert [g["id"] for g in grade["checklist_gaps"]] == ["career_outcomes"]
    assert grade["emergent"] is None


def test_gap_over_thin_sample_is_low_tier_not_dropped():
    sc = _sc([_feat("career_outcomes", qc_has=False, wp=2, n=2, weight="high")], n=2)
    rec = ts.scorecard_to_recommendation(sc)
    assert rec is not None
    assert rec["detail"]["evidence_tier"] == "low"
    assert rec["confidence"] == 0.45


def test_subthreshold_gaps_and_emergent_produce_low_tier_card():
    # The "event planning online course" shape: no feature clears the
    # prevalence bar, but QC lacks features some winners have, and the
    # emergent pass found a pattern. Previously: None -> false "parity".
    sc = _sc(
        [_feat("direct_answer_first", qc_has=True, wp=4, n=4, weight="high"),
         _feat("career_outcomes", qc_has=False, wp=2, n=4, weight="high"),
         _feat("tuition_pricing", qc_has=False, wp=1, n=4),
         _feat("video_embed", qc_has=False, wp=0, n=4, weight="low")],
        emergent_insight="Cited pages share a course-benefits section QC lacks.",
        emergent_edit="Add a 'Benefits of Taking the Course' section.",
    )
    rec = ts.scorecard_to_recommendation(sc)
    assert rec is not None
    assert rec["detail"]["evidence_tier"] == "low"
    assert rec["priority"] == "low"
    assert "Benefits of Taking the Course" in rec["action"]
    assert "LLM-observed pattern" in rec["action"]
    assert "career outcomes" in rec["action"]
    grade = rec["detail"]["evidence_grade"]
    assert grade["checklist_gaps"] == []
    assert {g["id"] for g in grade["partial_gaps"]} == {"career_outcomes", "tuition_pricing"}
    assert grade["emergent"]["edit"].startswith("Add a 'Benefits")


def test_unreadable_winners_disclosed_in_evidence():
    unread = [{"url": "https://pennfoster.edu/x", "domain": "pennfoster.edu",
               "status": "fetch_failed", "citation_count": 3}]
    sc = _sc([_feat("career_outcomes", qc_has=False, wp=3, n=4, weight="high")],
             unreadable=unread)
    rec = ts.scorecard_to_recommendation(sc)
    assert "Analyzed 4 of 5 cited pages" in rec["evidence"]
    assert "https://pennfoster.edu/x" in rec["evidence"]
    assert rec["detail"]["evidence_grade"]["winners_unreadable"] == unread


def test_true_parity_returns_none_with_accurate_reason():
    sc = _sc([_feat("direct_answer_first", qc_has=True, wp=4, n=4),
              _feat("faq_section", qc_has=True, wp=3, n=4)])
    assert ts.scorecard_to_recommendation(sc) is None
    assert ts.scorecard_triage_reason(sc) == "fix_true_feature_parity"


def test_too_few_readable_winners_is_insufficient_data_not_parity():
    sc = _sc([_feat("career_outcomes", qc_has=False, wp=1, n=1, weight="high")], n=1,
             unreadable=[{"url": "https://a.example", "domain": "a.example",
                          "status": "blocked_robots", "citation_count": 2}])
    assert ts.scorecard_to_recommendation(sc) is None
    assert ts.scorecard_triage_reason(sc) == "fix_insufficient_winner_data"


def test_unreadable_qc_page_is_its_own_state():
    sc = _sc([_feat("career_outcomes", qc_has=False, wp=3, n=4)], qc_readable=False)
    assert ts.scorecard_to_recommendation(sc) is None
    assert ts.scorecard_triage_reason(sc) == "fix_qc_page_unreadable"
