"""
Feature-diff prevalence must be computed over cited winners that share QC's
own page genre (commercial vs informational), not the full comparable pool.
Pooling a commercial course page's winners together with informational
guide/reference winners drags every feature's count toward "few" regardless
of whether the feature actually transfers to QC's page - a genre-matched
"most" is a real signal even when the pooled count looks weak. Falls back to
the full pool when too few same-genre winners exist to trust a stratified
count. No DB, no LLM: get_page_facts is monkeypatched, semantic features are
pre-cached on each fake facts dict, page_genre/winner_genre are stubbed to
control genre directly, and _emergent_pattern is stubbed out.
"""

import api.queries.scorecard as ts

QUESTION = "q"


def _facts(url, page_type, genre, career_outcomes=False):
    return {
        "url": url, "domain": url, "final_url": url, "page_type": page_type,
        "status": "ok", "title": "t", "headings": [], "content_excerpt": "",
        "features": {},
        f"__semantic__{QUESTION}": {"career_outcomes": career_outcomes},
        "_genre": genre,
    }


def _run(monkeypatch, qc_genre, winners):
    qc_facts = _facts("https://qc.example/page", "qc_owned", qc_genre)
    monkeypatch.setattr(ts, "get_page_facts", lambda url: qc_facts)
    monkeypatch.setattr(ts, "page_genre", lambda facts: facts.get("_genre"))
    monkeypatch.setattr(ts, "winner_genre", lambda facts: facts.get("_genre"))
    monkeypatch.setattr(ts, "_emergent_pattern", lambda *a, **k: ("", ""))
    return ts.build_scorecard("Course Discovery", qc_facts["url"], question=QUESTION,
                              winner_facts=winners)


def _row(sc, feature_id):
    return next(r for r in sc["features"] if r["id"] == feature_id)


def test_genre_stratified_reveals_signal_pooled_analysis_missed(monkeypatch):
    # Pooled across all 6 comparable winners, career_outcomes is present in
    # only 3/6 (50%) - "some", below the "most" recommend bar. But QC's page
    # is commercial, and all 3 commercial winners share the feature (3/3):
    # a real, unanimous signal the pooled count masked by averaging it
    # against 3 unrelated informational winners.
    winners = [
        _facts("https://c1.example", "competitor", "commercial", career_outcomes=True),
        _facts("https://c2.example", "competitor", "commercial", career_outcomes=True),
        _facts("https://c3.example", "competitor", "commercial", career_outcomes=True),
        _facts("https://g1.example", "guide", "informational", career_outcomes=False),
        _facts("https://g2.example", "guide", "informational", career_outcomes=False),
        _facts("https://g3.example", "guide", "informational", career_outcomes=False),
    ]
    sc = _run(monkeypatch, qc_genre="commercial", winners=winners)
    row = _row(sc, "career_outcomes")

    assert sc["genre_stratified"] is True
    assert sc["genre_matched_winners"] == 3
    assert row["winners_total"] == 3
    assert row["winners_present"] == 3
    assert row["prevalence"] == "most"
    assert row["recommend"] is True


def test_falls_back_to_full_pool_when_too_few_genre_matched_winners(monkeypatch):
    # Only 1 commercial winner is cited (below MIN_WINNERS=3) - too thin to
    # trust a stratified count on its own, so the scorecard must fall back
    # to the full pool rather than asserting a one-page stratum.
    winners = [
        _facts("https://c1.example", "competitor", "commercial", career_outcomes=True),
        _facts("https://g1.example", "guide", "informational", career_outcomes=False),
        _facts("https://g2.example", "guide", "informational", career_outcomes=False),
        _facts("https://g3.example", "guide", "informational", career_outcomes=False),
        _facts("https://g4.example", "guide", "informational", career_outcomes=False),
    ]
    sc = _run(monkeypatch, qc_genre="commercial", winners=winners)
    row = _row(sc, "career_outcomes")

    assert sc["genre_stratified"] is False
    assert sc["genre_matched_winners"] == 1
    assert row["winners_total"] == 5
    assert row["winners_present"] == 1


def test_falls_back_to_full_pool_when_qc_genre_unknown(monkeypatch):
    # QC's own genre couldn't be determined (ambiguous page) - never guess a
    # stratum, always fall back to the full comparable pool.
    winners = [
        _facts("https://c1.example", "competitor", "commercial", career_outcomes=True),
        _facts("https://c2.example", "competitor", "commercial", career_outcomes=True),
        _facts("https://c3.example", "competitor", "commercial", career_outcomes=True),
    ]
    sc = _run(monkeypatch, qc_genre=None, winners=winners)

    assert sc["genre_stratified"] is False
    assert sc["genre_matched_winners"] == 0
    assert sc["qc_genre"] is None
    assert _row(sc, "career_outcomes")["winners_total"] == 3
