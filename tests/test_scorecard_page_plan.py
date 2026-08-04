"""
build_page_plan() (api/queries/scorecard.py): the deterministic, format-
templated page plan for a BUILD rec. No LLM synthesis - sections come from a
fixed skeleton keyed by target_format (how_to/long_form/listicle/landing),
each backed by a build_winner_checklist() row when enough comparable winners
share it, or a static template sentence otherwise; word_count_target is the
median of comparable winners' fetched word_count; structure_targets are the
absolute literature targets already in geo_features.json (ratio features),
unchanged by target_format.

No DB, no LLM: get_page_facts is never called by build_page_plan directly,
semantic features are pre-cached on each fake facts dict (so no network call
is attempted), and winner_genre is stubbed to read genre off the fixture
directly - same conventions as test_scorecard_genre_stratification.py.
"""

import api.queries.scorecard as ts

QUESTION = "how to become a dog groomer"


def _facts(url, page_type, genre, word_count=None, semantic=None, features=None, headings=None):
    f = {
        "url": url, "domain": url, "final_url": url, "page_type": page_type,
        "status": "ok", "title": "t", "headings": headings or [], "content_excerpt": "",
        "features": features or {},
        f"__semantic__{QUESTION}": semantic or {},
        "_genre": genre,
    }
    if word_count is not None:
        f["word_count"] = word_count
    return f


def _wire_genre(monkeypatch):
    monkeypatch.setattr(ts, "winner_genre", lambda facts: facts.get("_genre"))


def _how_to_winners(n=3, word_counts=None, headings=None):
    word_counts = word_counts or [None] * n
    headings = headings or [[] for _ in range(n)]
    return [
        _facts(f"https://guide{i}.example", "guide", "informational",
               word_count=word_counts[i], headings=headings[i],
               semantic={"direct_answer_first": True, "certification_pathway": True})
        for i in range(n)
    ]


def test_none_below_min_winners(monkeypatch):
    _wire_genre(monkeypatch)
    winners = _how_to_winners(2)  # below MIN_WINNERS=3
    assert ts.build_page_plan(winners, QUESTION, "how_to", target_genre="informational") is None


def test_none_for_unrecognized_format(monkeypatch):
    _wire_genre(monkeypatch)
    winners = _how_to_winners(3)
    assert ts.build_page_plan(winners, QUESTION, "some_format_nobody_uses", target_genre="informational") is None
    assert ts.build_page_plan(winners, QUESTION, None, target_genre="informational") is None


def test_how_to_sections_checklist_vs_template(monkeypatch):
    _wire_genre(monkeypatch)
    winners = _how_to_winners(3, word_counts=[1000, 1200, 1400])

    plan = ts.build_page_plan(winners, QUESTION, "how_to", target_genre="informational")
    assert plan["format"] == "how_to"

    by_title = {s["title"]: s for s in plan["sections"]}

    # direct_answer_first and certification_pathway are true on all 3 winners
    # (100% - clears "most") - both slots resolve from the checklist.
    assert by_title["Direct answer up front"]["source"] == "checklist"
    assert by_title["Direct answer up front"]["detail"] == "100% of cited pages have it"
    assert by_title["Direct answer up front"]["geo_weight"] == "high"

    assert by_title["Requirements / prerequisites"]["source"] == "checklist"
    assert by_title["Requirements / prerequisites"]["geo_weight"] == "high"

    # "Step-by-step process" has no checklist_ids at all - always the template.
    assert by_title["Step-by-step process"]["source"] == "template"

    # career_outcomes/faq_section/question_headings are false/absent on every
    # winner - neither slot clears the prevalence bar, so both fall back to
    # their static template sentence rather than silently omitting the slot.
    assert by_title["Career outcomes"]["source"] == "template"
    assert by_title["FAQ / common questions"]["source"] == "template"

    # Every skeleton slot renders - a page plan never drops a section outright.
    assert len(plan["sections"]) == 5


def test_word_count_target_is_median_odd_and_even(monkeypatch):
    _wire_genre(monkeypatch)

    odd = _how_to_winners(3, word_counts=[1000, 1400, 1200])
    plan = ts.build_page_plan(odd, QUESTION, "how_to", target_genre="informational")
    assert plan["word_count_target"] == {"value": 1200, "based_on_n_winners": 3}

    even = _how_to_winners(4, word_counts=[1000, 1200, 1400, 1600])
    plan = ts.build_page_plan(even, QUESTION, "how_to", target_genre="informational")
    assert plan["word_count_target"] == {"value": 1300, "based_on_n_winners": 4}


def test_word_count_target_none_when_too_few_winners_carry_it(monkeypatch):
    _wire_genre(monkeypatch)
    # 3 comparable winners (clears the plan's own min_winners gate), but only
    # 2 carry a usable word_count - below min_winners for the target itself.
    winners = _how_to_winners(3, word_counts=[1000, 1200, None])
    plan = ts.build_page_plan(winners, QUESTION, "how_to", target_genre="informational")
    assert plan is not None
    assert plan["word_count_target"] is None


def test_structure_targets_are_format_flat(monkeypatch):
    _wire_genre(monkeypatch)
    winners = _how_to_winners(3, word_counts=[1000, 1200, 1400])
    features = {f["id"]: f for f in ts._load_features() if f["detection"] == "ratio"}

    for fmt in ("how_to", "long_form", "listicle", "landing"):
        plan = ts.build_page_plan(winners, QUESTION, fmt, target_genre="informational")
        targets_by_id = {t["id"]: t for t in plan["structure_targets"]}
        assert set(targets_by_id) == set(features)
        for fid, feat in features.items():
            t = targets_by_id[fid]
            assert t["target_min"] == feat["target_min"]
            assert t["target_max"] == feat["target_max"]
            assert t["unit"] == feat["unit"]
            assert t["guidance"] == feat.get("fix_below")


def test_genre_stratification_falls_back_like_checklist(monkeypatch):
    # Mirrors test_scorecard_genre_stratification.py's own fallback case:
    # too few genre-matched winners (1 commercial, below MIN_WINNERS) to trust
    # a stratified sample - _comparable_target_winners must fall back to the
    # full comparable pool, exactly like build_winner_checklist already does.
    _wire_genre(monkeypatch)
    winners = [
        _facts("https://c1.example", "competitor", "commercial", word_count=1000),
        _facts("https://g1.example", "guide", "informational", word_count=1000),
        _facts("https://g2.example", "guide", "informational", word_count=1200),
        _facts("https://g3.example", "guide", "informational", word_count=1400),
    ]
    plan = ts.build_page_plan(winners, QUESTION, "long_form", target_genre="commercial")
    # Falls back to the full 4-page pool (not just the 1 commercial page),
    # so the word-count target is computable at all: median of
    # [1000, 1000, 1200, 1400] is 1100.
    assert plan["word_count_target"] == {"value": 1100, "based_on_n_winners": 4}


def test_comparable_target_winners_matches_build_winner_checklist_sample():
    # Regression for the _comparable_target_winners extraction: same fixture
    # shape as test_scorecard_genre_stratification.py's stratified case -
    # build_winner_checklist's own denominator must be unchanged post-refactor.
    winners = [
        _facts("https://c1.example", "competitor", "commercial",
               semantic={"career_outcomes": True}),
        _facts("https://c2.example", "competitor", "commercial",
               semantic={"career_outcomes": True}),
        _facts("https://c3.example", "competitor", "commercial",
               semantic={"career_outcomes": True}),
        _facts("https://g1.example", "guide", "informational",
               semantic={"career_outcomes": False}),
        _facts("https://g2.example", "guide", "informational",
               semantic={"career_outcomes": False}),
        _facts("https://g3.example", "guide", "informational",
               semantic={"career_outcomes": False}),
    ]

    def _stub_winner_genre(facts):
        return facts.get("_genre")

    import api.queries.scorecard as sc
    orig = sc.winner_genre
    sc.winner_genre = _stub_winner_genre
    try:
        rows = sc.build_winner_checklist(winners, QUESTION, target_genre="commercial")
    finally:
        sc.winner_genre = orig

    row = next(r for r in rows if r["id"] == "career_outcomes")
    assert row["winners_total"] == 3
    assert row["winners_present"] == 3
    assert row["winners_pct"] == 100


# ─────────────────────────────────────────────────────────────────────────────
# Real example headings (_match_example_heading), extracted from cited winners'
# own page_facts.headings - keyword matching, no LLM.
# ─────────────────────────────────────────────────────────────────────────────

def test_example_heading_matched_and_folded_into_checklist_detail(monkeypatch):
    _wire_genre(monkeypatch)
    winners = _how_to_winners(
        3, word_counts=[1000, 1200, 1400],
        headings=[["Becoming a Certified Dog Trainer"], [], []])

    plan = ts.build_page_plan(winners, QUESTION, "how_to", target_genre="informational")
    section = next(s for s in plan["sections"] if s["title"] == "Requirements / prerequisites")

    # certification_pathway is 100% prevalent (checklist-backed) AND a winner
    # heading matches _HINT_REQUIREMENTS - detail combines both, in place,
    # rather than adding a new field/line.
    assert section["source"] == "checklist"
    assert section["example"] == {"heading": "Becoming a Certified Dog Trainer",
                                   "domain": "https://guide0.example"}
    assert section["detail"] == \
        '"Becoming a Certified Dog Trainer" (https://guide0.example) — 100% of cited pages have it'


def test_example_heading_folded_into_template_detail(monkeypatch):
    _wire_genre(monkeypatch)
    # "Step-by-step process" has no checklist_ids at all - always template -
    # but a matching heading should still replace the generic sentence.
    winners = _how_to_winners(
        3, word_counts=[1000, 1200, 1400],
        headings=[["The Step-by-Step Path to Certification"], [], []])

    plan = ts.build_page_plan(winners, QUESTION, "how_to", target_genre="informational")
    section = next(s for s in plan["sections"] if s["title"] == "Step-by-step process")

    assert section["source"] == "template"
    assert section["example"]["heading"] == "The Step-by-Step Path to Certification"
    assert section["detail"] == '"The Step-by-Step Path to Certification" (https://guide0.example)'


def test_no_matching_heading_falls_back_unchanged(monkeypatch):
    _wire_genre(monkeypatch)
    # Headings present, but none match any slot's hint - behavior must be
    # identical to having no headings at all (the pre-existing regression
    # case from test_how_to_sections_checklist_vs_template).
    winners = _how_to_winners(
        3, word_counts=[1000, 1200, 1400],
        headings=[["Table of Contents"], ["Related Reading"], []])

    plan = ts.build_page_plan(winners, QUESTION, "how_to", target_genre="informational")
    by_title = {s["title"]: s for s in plan["sections"]}

    assert "example" not in by_title["Career outcomes"]
    assert by_title["Career outcomes"]["source"] == "template"
    assert by_title["Career outcomes"]["detail"] == \
        "What this leads to: salary range, job titles, employment prospects."


def test_duplicate_heading_not_reused_across_slots(monkeypatch):
    _wire_genre(monkeypatch)
    # One heading matches BOTH _HINT_REQUIREMENTS ("certif...") and
    # _HINT_OUTCOMES ("career") - only the earlier slot in skeleton order
    # ("Requirements / prerequisites") may claim it; "Career outcomes" (which
    # has no other signal on these fixtures - career_outcomes semantic is
    # False by default in _how_to_winners) must fall back as if unmatched.
    winners = _how_to_winners(
        3, word_counts=[1000, 1200, 1400],
        headings=[["Certification and Career Outcomes"], [], []])

    plan = ts.build_page_plan(winners, QUESTION, "how_to", target_genre="informational")
    by_title = {s["title"]: s for s in plan["sections"]}

    assert by_title["Requirements / prerequisites"]["example"]["heading"] == \
        "Certification and Career Outcomes"
    assert "example" not in by_title["Career outcomes"]
    assert by_title["Career outcomes"]["source"] == "template"


def test_overlong_heading_skipped_as_example(monkeypatch):
    _wire_genre(monkeypatch)
    long_heading = "Becoming a Certified Dog Trainer " + ("x" * 60)
    assert len(long_heading) > ts._MAX_EXAMPLE_HEADING_LEN
    winners = _how_to_winners(
        3, word_counts=[1000, 1200, 1400],
        headings=[[long_heading], [], []])

    plan = ts.build_page_plan(winners, QUESTION, "how_to", target_genre="informational")
    section = next(s for s in plan["sections"] if s["title"] == "Requirements / prerequisites")

    assert "example" not in section
    assert section["detail"] == "100% of cited pages have it"
