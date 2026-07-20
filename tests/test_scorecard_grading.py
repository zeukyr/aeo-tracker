"""
Evidence-graded scorecard recs: scorecard_to_recommendation no longer returns
a binary rec-or-None. Verified checklist gaps over a sufficient sample are
tier "high"; thin samples, sub-threshold gaps and the emergent LLM pattern
are tier "low"; None is reserved for the three empty states named precisely
by scorecard_triage_reason. Unreadable cited winners must be disclosed, never
silently dropped from the denominator. All inputs are constructed scorecards -
no DB, no LLM.
"""

import api.queries.scorecard as ts


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


def _metric(fid, qc_value, target_min, target_max, weight="medium", confidence="high", unit="pct"):
    in_range = qc_value is not None and target_min <= qc_value <= target_max
    return {
        "id": fid, "label": fid.replace("_", " "), "geo_weight": weight,
        "confidence": confidence, "unit": unit,
        "target_min": target_min, "target_max": target_max,
        "qc_value": qc_value, "in_range": in_range,
        "recommend": qc_value is not None and not in_range,
    }


def _sc(features, n=4, qc_readable=True, unreadable=(), excluded=(),
        emergent_insight="", emergent_edit="", metric_rows=()):
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
        "metric_rows": list(metric_rows),
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


# ─────────────────────────────────────────────────────────────────────────────
# Ratio ("metric") features: absolute literature targets, not winner-relative,
# scored against a fixed target range rather than this topic's cited winners.
# They stay on the SAME card as any checklist finding, but their prose,
# evidence, and priority/confidence contribution are kept separate from the
# competitor-verified checklist - a metric gap is backed by literature, not
# by this topic's competitors, so it must never read as (or outrank) a
# competitor-verified finding on its own.
# ─────────────────────────────────────────────────────────────────────────────

def test_metric_gap_is_actionable_even_with_insufficient_winners():
    sc = _sc([], n=1, metric_rows=[
        _metric("internal_linking_density", qc_value=6, target_min=15, target_max=20, weight="high"),
    ])
    rec = ts.scorecard_to_recommendation(sc)
    assert rec is not None
    assert "internal linking density" in rec["problem"].lower()
    assert "15-20%" in rec["action"]
    # a metric gap alone can nudge low -> medium priority but never claims high
    # on its own, regardless of geo_weight - that's reserved for competitor-
    # verified checklist gaps.
    assert rec["priority"] == "medium"
    assert rec["confidence"] <= 0.5
    assert rec["detail"]["evidence_grade"]["metric_gaps"][0]["id"] == "internal_linking_density"
    # checklist comparison genuinely didn't run - no false parity claim
    assert "matches the analyzed winners" not in rec["problem"]
    # evidence text keeps the metric finding out from behind the winner-sample
    # completeness caveat, which never applied to it
    assert "Structural metrics (independent of the winner comparison)" in rec["evidence"]


def test_metric_gap_shares_card_but_stays_narratively_separate():
    sc = _sc(
        [_feat("career_outcomes", qc_has=False, wp=3, n=4, weight="high")],
        metric_rows=[_metric("structured_content_ratio", qc_value=10, target_min=25, target_max=35, weight="high")],
    )
    rec = ts.scorecard_to_recommendation(sc)
    assert rec is not None
    # one card, both findings present
    assert rec["detail"]["evidence_grade"]["checklist_gaps"][0]["id"] == "career_outcomes"
    assert rec["detail"]["evidence_grade"]["metric_gaps"][0]["id"] == "structured_content_ratio"
    assert "structured content ratio" in rec["action"].lower()
    # the checklist gap alone already earns "high" priority/0.7 confidence -
    # the metric gap must not be why, and must not be indistinguishable from it
    assert rec["priority"] == "high"
    assert rec["confidence"] == 0.7
    assert "independent of the winner comparison" in rec["problem"].lower()
    checklist_evidence, _, metric_evidence = rec["evidence"].partition(" | ")
    assert "career outcomes" in checklist_evidence.lower()
    assert "structured content ratio" in metric_evidence.lower()
    assert "Analyzed" in checklist_evidence   # coverage note stays on the checklist half
    assert "Analyzed" not in metric_evidence  # ...never bleeds into the metric half


def test_multiple_metric_gaps_lead_with_highest_research_priority():
    # emphasis_density (micro-structure, lowest priority) and
    # internal_linking_density (macro-structure, highest priority) both fail -
    # the narrative should lead with internal_linking_density, not emphasis
    # density or a flat listing of both.
    sc = _sc([], n=1, metric_rows=[
        _metric("emphasis_density", qc_value=1, target_min=5, target_max=10, weight="low", confidence="medium"),
        _metric("internal_linking_density", qc_value=3, target_min=15, target_max=20, weight="high"),
    ])
    rec = ts.scorecard_to_recommendation(sc)
    assert rec is not None
    assert "internal linking density" in rec["problem"].lower()
    assert "emphasis density" not in rec["problem"].lower()
    assert rec["problem"].lower().count("more also measured out of range") == 1
    assert "internal linking density" in rec["action"].lower()
    assert "1 more metric(s)" in rec["action"]
    # both still fully present in the stored evidence/detail data - nothing dropped
    assert "emphasis density" in rec["evidence"].lower()
    gap_ids = [g["id"] for g in rec["detail"]["evidence_grade"]["metric_gaps"]]
    assert set(gap_ids) == {"emphasis_density", "internal_linking_density"}
    assert gap_ids[0] == "internal_linking_density"  # ranked, lead first


def test_true_parity_with_all_metrics_in_range_returns_none():
    sc = _sc(
        [_feat("direct_answer_first", qc_has=True, wp=4, n=4),
         _feat("faq_section", qc_has=True, wp=3, n=4)],
        metric_rows=[_metric("internal_linking_density", qc_value=17, target_min=15, target_max=20)],
    )
    assert ts.scorecard_to_recommendation(sc) is None
    assert ts.scorecard_triage_reason(sc) == "fix_true_feature_parity"


def test_metric_value_unmeasurable_does_not_recommend():
    m = _metric("internal_linking_density", qc_value=None, target_min=15, target_max=20)
    assert m["recommend"] is False
