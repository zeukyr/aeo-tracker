"""
Router invariants (question-router plan §9 R11), as durable regression tests:

  (a) a clear genre-mismatch question emits NO fix rec - the scorecard is
      suppressed and the build branch owns it
  (b) every losing question yields exactly one route - triage is a
      first-class outcome, nothing is silently dropped
  (c) no question emits both a fix and a build
  plus branch behavior: non-ownable -> reach-out when a channel exists,
  known-closed (wikipedia/.gov) -> build, fragmented -> triage (never
  auto-built), reputation with no channel -> triage.

All DB / network / LLM boundaries are stubbed; the classification logic
(source_type, dominant_source_type, genre_gap, outreach_feasibility registry
and defaults) runs for real over crafted page facts.
"""

import pytest

import api.queries.question_router as qr
from api.queries.page_facts import source_type


# ─────────────────────────────────────────────────────────────────────────────
# Crafted facts / questions
# ─────────────────────────────────────────────────────────────────────────────

def facts(domain, page_type, url=None, status="ok", **overrides):
    f = {
        "url": url or f"https://{domain}/page",
        "final_url": url or f"https://{domain}/page",
        "domain": domain,
        "status": status,
        "page_type": page_type,
        "title": "",
        "headings": [],
        "schema_types": [],
        "features": {},
        "brand_mentions": {},
        "qc_mentioned": False,
    }
    f.update(overrides)
    return f


def commercial_winner(domain, url=None):
    """A rival's course page: course schema + pricing + /courses/ URL."""
    return facts(domain, "competitor", url=url or f"https://{domain}/courses/x",
                 features={"course_schema": True, "pricing_signals": True})


def informational_winner(domain):
    """An editorial how-to guide."""
    return facts(domain, "guide", url=f"https://{domain}/blog/how-to-x",
                 title="How to Become an X")


QC_INFORMATIONAL = facts(
    "qcpetstudies.com", "qc_owned",
    url="https://www.qcpetstudies.com/blog/how-to-become-a-dog-groomer",
    title="How to Become a Dog Groomer", features={"question_headings": 4})

QC_COMMERCIAL = facts(
    "qcpetstudies.com", "qc_owned",
    url="https://www.qcpetstudies.com/certification-courses/dog-training",
    title="Dog Training Course",
    features={"course_schema": True, "pricing_signals": True})


def question(qid, text, topic="How to Become", school="QC Pet Studies"):
    return {"question_id": qid, "question": text, "topic": topic, "school": school,
            "qc_share": 0.0, "n_responses": 10, "n_citations": 30}


def wire(monkeypatch, winners_by_qid, coverage_by_qid=None, qc_facts=None):
    """Stub the router's DB/network boundaries for a set of questions."""
    monkeypatch.setattr(qr, "get_question_cited_urls",
                        lambda qid, days=None, **kw: [
                            {"url": f["url"], "count": c}
                            for f, c in winners_by_qid.get(qid, [])])
    all_facts = {f["url"]: f for pairs in winners_by_qid.values() for f, _c in pairs}
    monkeypatch.setattr(qr, "get_pages_facts",
                        lambda urls, **kw: [dict(all_facts[u]) for u in urls])
    monkeypatch.setattr(qr, "diagnose_text_coverage",
                        lambda text, school=None: (coverage_by_qid or {}).get(
                            text, {"verdict": "missing_page", "qc_url": None}))
    monkeypatch.setattr(qr, "get_page_facts", lambda url, **kw: qc_facts or {})


def forbid_scorecard(monkeypatch):
    def _boom(*a, **kw):
        raise AssertionError("build_scorecard must not run for this route")
    monkeypatch.setattr(qr, "build_scorecard", _boom)


def stub_scorecard(monkeypatch, calls):
    monkeypatch.setattr(qr, "build_scorecard",
                        lambda *a, **kw: calls.append(a) or {"stub": True})
    monkeypatch.setattr(qr, "scorecard_to_recommendation",
                        lambda sc: {"problem": "p", "action": "a", "priority": "medium",
                                    "school": None, "evidence": "e",
                                    "action_type": "technical", "target": "t",
                                    "segment": {}, "metric_impact": "citation_rate",
                                    "expected_direction": 1, "expected_magnitude": None,
                                    "effort": "M", "confidence": 0.7, "detail": {}})


# ─────────────────────────────────────────────────────────────────────────────
# (a) genre mismatch suppresses the fix / feature-diff
# ─────────────────────────────────────────────────────────────────────────────

def test_genre_mismatch_routes_build_and_never_runs_scorecard(monkeypatch):
    q = question(1, "how to become a dog groomer")
    winners = [(informational_winner(f"guide{i}.com"), 5) for i in range(3)]
    wire(monkeypatch, {1: winners},
         coverage_by_qid={q["question"]: {"verdict": "have_page",
                                          "qc_url": QC_COMMERCIAL["url"]}},
         qc_facts=QC_COMMERCIAL)
    forbid_scorecard(monkeypatch)

    route = qr.route_question(q)
    assert route["branch"] == "build"
    assert route["reason"] == "ownable_wrong_kind_page"
    assert route["genre_mismatch"]["winner_genre"] == "informational"

    monkeypatch.setattr(qr, "get_losing_questions", lambda days=None, **kw: [q])
    recs, triage = qr.build_router_recommendations()
    assert not any(r["action_type"] == "technical" for r in recs)
    assert len(recs) == 1 and recs[0]["detail"]["router"]["branch"] == "build"
    assert triage == []


def test_same_kind_page_routes_fix_and_scorecard_runs(monkeypatch):
    q = question(2, "best dog training course")
    winners = [(commercial_winner(f"rival{i}.com"), 4) for i in range(3)]
    wire(monkeypatch, {2: winners},
         coverage_by_qid={q["question"]: {"verdict": "have_page",
                                          "qc_url": QC_COMMERCIAL["url"]}},
         qc_facts=QC_COMMERCIAL)

    route = qr.route_question(q)
    assert route["branch"] == "fix"
    assert route["genre_mismatch"] is None

    calls = []
    stub_scorecard(monkeypatch, calls)
    monkeypatch.setattr(qr, "get_losing_questions", lambda days=None, **kw: [q])
    recs, _ = qr.build_router_recommendations()
    assert len(calls) == 1
    assert [r["action_type"] for r in recs] == ["technical"]


# ─────────────────────────────────────────────────────────────────────────────
# branch behavior: reach-out / closed / fragmented / reputation
# ─────────────────────────────────────────────────────────────────────────────

def test_ugc_winners_reach_out_open(monkeypatch):
    q = question(3, "is dog grooming worth it reddit")
    winners = [(facts("reddit.com", "community", status="not_fetched",
                      url=f"https://reddit.com/r/dogs/{i}"), 6) for i in range(3)]
    wire(monkeypatch, {3: winners})
    forbid_scorecard(monkeypatch)

    route = qr.route_question(q)
    assert route["branch"] == "reach_out"
    assert route["feasibility"]["feasibility"] == "open"
    assert route["feasibility"]["channel"] == "participate"


def test_wikipedia_closed_routes_build_earn_indirect(monkeypatch):
    q = question(4, "what is a dog groomer")
    winners = [(facts("en.wikipedia.org", "guide",
                      url=f"https://en.wikipedia.org/wiki/Dog_{i}"), 8) for i in range(3)]
    wire(monkeypatch, {4: winners})
    forbid_scorecard(monkeypatch)

    route = qr.route_question(q)
    assert route["branch"] == "build"
    assert route["reason"] == "earn_indirect"
    assert route["feasibility"]["feasibility"] == "closed"


def test_fragmented_field_stays_triage_flagged_build_candidate(monkeypatch):
    # ownable 4/8 and non-ownable 4/8 - neither side clears 0.6
    q = question(5, "careers with dogs")
    winners = [
        (commercial_winner("rival1.com"), 2),
        (commercial_winner("rival2.com"), 2),
        (facts("reddit.com", "community", status="not_fetched"), 2),
        (facts("quora.com", "community", status="not_fetched",
               url="https://quora.com/q1"), 2),
    ]
    wire(monkeypatch, {5: winners})
    forbid_scorecard(monkeypatch)

    route = qr.route_question(q)
    assert route["branch"] == "triage"
    assert route["reason"] == "fragmented_field"
    assert route["build_candidate"] is True  # buildable topic, human green-light
    assert route["vote"]["voters"] == 8


def test_two_stage_vote_unites_competitor_and_editorial(monkeypatch):
    # competitor 45% + editorial 36% - neither leads a FLAT vote, but the
    # slot is 82% ownable: the two-stage vote routes it instead of triaging.
    q = question(8, "how to become a dog trainer in canada")
    winners = [
        (commercial_winner("rival1.com"), 5),
        (informational_winner("guide1.com"), 4),
        (facts("reddit.com", "community", status="not_fetched",
               url="https://reddit.com/r/dogs/z"), 2),
    ]
    wire(monkeypatch, {8: winners})  # no QC page -> build (buildable topic)
    forbid_scorecard(monkeypatch)

    route = qr.route_question(q)
    assert route["branch"] == "build"
    assert route["reason"] == "ownable_no_qc_page"
    assert route["vote"]["ownable_share"] == 0.82
    assert route["dominant"][0] == "competitor"  # stage leader, for wording


def test_insufficient_voters_triages_regardless_of_share(monkeypatch):
    # 100% ownable - but only 3 voting citations. One page's opinion.
    q = question(9, "niche question with thin citations")
    winners = [(commercial_winner("rival1.com"), 3)]
    wire(monkeypatch, {9: winners})
    forbid_scorecard(monkeypatch)

    route = qr.route_question(q)
    assert route["branch"] == "triage"
    assert route["reason"] == "insufficient_voters"
    assert route["vote"]["voters"] == 3


def test_stage_two_picks_leading_non_ownable_bucket(monkeypatch):
    # non-ownable 78% (ugc 5 + review 2); ugc leads -> participate, not claim
    q = question(10, "dog grooming course reviews")
    winners = [
        (facts("reddit.com", "community", status="not_fetched",
               url="https://reddit.com/r/dogs/rev"), 5),
        (facts("trustpilot.com", "editorial", url="https://trustpilot.com/review/x"), 2),
        (commercial_winner("rival1.com"), 2),
    ]
    wire(monkeypatch, {10: winners})
    forbid_scorecard(monkeypatch)

    route = qr.route_question(q)
    assert route["branch"] == "reach_out"
    assert route["dominant"][0] == "ugc"
    assert route["feasibility"]["channel"] == "participate"


def test_reputation_topic_without_channel_triages(monkeypatch):
    q = question(6, "is QC Pet Studies legit", topic="Brand Credibility")
    winners = [(commercial_winner(f"rival{i}.com"), 3) for i in range(3)]
    wire(monkeypatch, {6: winners})
    forbid_scorecard(monkeypatch)

    route = qr.route_question(q)
    assert route["branch"] == "triage"
    assert route["reason"] == "reputation_no_channel"


def test_no_cited_winners_triages(monkeypatch):
    q = question(7, "obscure question nothing cites")
    wire(monkeypatch, {7: []})
    route = qr.route_question(q)
    assert route["branch"] == "triage"
    assert route["reason"] == "no_cited_winners"


# ─────────────────────────────────────────────────────────────────────────────
# (b) + (c): full dispatch accounting over a mixed set
# ─────────────────────────────────────────────────────────────────────────────

def test_every_question_routes_exactly_once_and_branches_disjoint(monkeypatch):
    q_build = question(1, "how to become a dog groomer")
    q_fix = question(2, "best dog training course")
    q_reach = question(3, "is dog grooming worth it reddit")
    q_frag = question(5, "careers with dogs")
    q_empty = question(7, "obscure question nothing cites")
    questions = [q_build, q_fix, q_reach, q_frag, q_empty]

    winners_by_qid = {
        1: [(informational_winner(f"guide{i}.com"), 5) for i in range(3)],
        2: [(commercial_winner(f"rival{i}.com"), 4) for i in range(3)],
        3: [(facts("reddit.com", "community", status="not_fetched",
                   url=f"https://reddit.com/r/dogs/{i}"), 6) for i in range(3)],
        5: [
            (commercial_winner("rival1.com"), 2),
            (commercial_winner("rival2.com"), 2),
            (facts("reddit.com", "community", status="not_fetched",
                   url="https://reddit.com/r/x"), 2),
            (facts("quora.com", "community", status="not_fetched",
                   url="https://quora.com/q1"), 2),
        ],
        7: [],
    }
    coverage = {
        q_build["question"]: {"verdict": "have_page", "qc_url": QC_COMMERCIAL["url"]},
        q_fix["question"]:   {"verdict": "have_page", "qc_url": QC_COMMERCIAL["url"]},
    }
    wire(monkeypatch, winners_by_qid, coverage_by_qid=coverage, qc_facts=QC_COMMERCIAL)
    calls = []
    stub_scorecard(monkeypatch, calls)
    monkeypatch.setattr(qr, "get_losing_questions", lambda days=None, **kw: questions)

    # (b) every question yields exactly one route
    routes = [qr.route_question(q) for q in questions]
    assert [r["branch"] for r in routes] == ["build", "fix", "reach_out", "triage", "triage"]

    recs, triage = qr.build_router_recommendations()

    # accounting: every question lands in exactly one place
    qids_by_branch = {}
    for r in recs:
        router = r["detail"]["router"]
        if router["branch"] == "inclusion_opportunity":
            continue  # per-winner extras, may share a question with a branch rec
        qids_by_branch.setdefault(router["branch"], set()).add(router["question_id"])
    # question_id is stringified in detail/triage (uuids in production)
    triage_qids = {str(t["question_id"]) for t in triage}

    assert qids_by_branch.get("fix") == {"2"}
    assert qids_by_branch.get("build") == {"1"}
    assert qids_by_branch.get("reach_out") == {"3"}
    assert triage_qids == {"5", "7"}

    # (c) no question emits both a fix and a build
    assert not (qids_by_branch.get("fix", set()) & qids_by_branch.get("build", set()))
    # and no routed question is also triaged
    routed = set().union(*qids_by_branch.values())
    assert not (routed & triage_qids)


# ─────────────────────────────────────────────────────────────────────────────
# Benchmark/evidence URL hygiene: cards never point at junk
# ─────────────────────────────────────────────────────────────────────────────

def test_videos_and_bare_homepages_never_benchmark(monkeypatch):
    # Vote is carried by competitor pages; a heavily-cited youtube video and a
    # bare homepage ride along in the winner set. Neither may surface as a
    # benchmark or in the evidence line.
    q = question(10, "how to start a home decor business",
                 topic="Starting a Business")
    winners = [
        (commercial_winner("rivalschool.com"), 5),
        (facts("youtube.com", "video", status="not_fetched",
               url="https://youtube.com/watch?v=abc"), 9),
        (facts("pdga.online", "editorial", url="https://pdga.online",
               status="fetch_failed"), 4),
        (commercial_winner("otherschool.com"), 3),
    ]
    wire(monkeypatch, {10: winners})
    route = qr.route_question(q)
    assert route["branch"] == "build"

    rec = qr._build_rec(route, [route])
    for text in (rec["action"], rec["evidence"]):
        assert "youtube" not in text
        assert "pdga.online" not in text
    assert "rivalschool.com" in rec["action"]


# ─────────────────────────────────────────────────────────────────────────────
# On-demand single-question generation
# ─────────────────────────────────────────────────────────────────────────────

def test_single_question_build_returns_rec_not_triage(monkeypatch):
    q = question(20, "how to become a dog groomer")
    wire(monkeypatch, {20: [(informational_winner(f"guide{i}.com"), 5) for i in range(3)]})
    forbid_scorecard(monkeypatch)
    monkeypatch.setattr(qr, "get_question_stats", lambda qid, days=None: q)

    rec, triage = qr.build_question_recommendation(20)
    assert triage is None
    assert rec["segment"] == {"dimension": "question",
                              "value": q["question"], "question_id": "20"}
    assert rec["detail"]["router"]["branch"] == "build"


def test_single_question_triage_comes_back_as_entry(monkeypatch):
    q = question(21, "obscure question nothing cites")
    wire(monkeypatch, {21: []})
    monkeypatch.setattr(qr, "get_question_stats", lambda qid, days=None: q)

    rec, triage = qr.build_question_recommendation(21)
    assert rec is None
    assert triage["reason"] == "no_cited_winners"
    assert triage["question_id"] == 21


def test_single_question_without_mention_responses(monkeypatch):
    monkeypatch.setattr(qr, "get_question_stats", lambda qid, days=None: None)
    assert qr.build_question_recommendation(22) == (None, None)


def test_single_question_fix_attaches_router_detail(monkeypatch):
    q = question(23, "best dog training course")
    wire(monkeypatch, {23: [(commercial_winner(f"rival{i}.com"), 4) for i in range(3)]},
         coverage_by_qid={q["question"]: {"verdict": "have_page",
                                          "qc_url": QC_COMMERCIAL["url"]}},
         qc_facts=QC_COMMERCIAL)
    calls = []
    stub_scorecard(monkeypatch, calls)
    monkeypatch.setattr(qr, "get_question_stats", lambda qid, days=None: q)

    rec, triage = qr.build_question_recommendation(23)
    assert triage is None
    assert len(calls) == 1
    assert rec["action_type"] == "technical"
    assert rec["detail"]["router"]["branch"] == "fix"


def test_single_question_fix_with_empty_scorecard_triages(monkeypatch):
    # An empty scorecard result triages with a PRECISE reason (true parity
    # here), never the false-parity catch-all - and the competitor winners
    # offer no inclusion-opportunity fallback to mask it.
    q = question(24, "best dog training course")
    wire(monkeypatch, {24: [(commercial_winner(f"rival{i}.com"), 4) for i in range(3)]},
         coverage_by_qid={q["question"]: {"verdict": "have_page",
                                          "qc_url": QC_COMMERCIAL["url"]}},
         qc_facts=QC_COMMERCIAL)
    monkeypatch.setattr(qr, "build_scorecard",
                        lambda *a, **kw: {"qc_readable": True, "winners_total": 3,
                                          "winners_cited_total": 3,
                                          "winners_unreadable": []})
    monkeypatch.setattr(qr, "scorecard_to_recommendation", lambda sc: None)
    monkeypatch.setattr(qr, "get_question_stats", lambda qid, days=None: q)

    rec, triage = qr.build_question_recommendation(24)
    assert rec is None
    assert triage["reason"] == "fix_true_feature_parity"
    assert triage["scorecard"]["winners_readable"] == 3


def test_build_card_omits_benchmark_rather_than_falling_back(monkeypatch):
    # All winners are junk for display (video + bare homepage) but a domain-
    # classified competitor homepage still votes -> build fires, benchmark
    # clause is dropped entirely.
    q = question(11, "best decor course", topic="Course Discovery")
    winners = [
        (facts("rivalschool.com", "competitor", url="https://rivalschool.com",
               status="fetch_failed"), 5),
        (facts("youtube.com", "video", status="not_fetched",
               url="https://youtube.com/watch?v=abc"), 9),
    ]
    wire(monkeypatch, {11: winners})
    route = qr.route_question(q)
    assert route["branch"] == "build"

    rec = qr._build_rec(route, [route])
    assert "Benchmark" not in rec["action"]
    assert "youtube" not in rec["action"]
