"""
The deterministic classification layers under the router: source-type
bucketing (incl. the cvent-forum case), outreach feasibility, the coverage
matcher's junk-page exclusion, and the page-facts failure-retry window.
"""

from datetime import datetime, timedelta, timezone

from api.queries.page_facts import (
    source_type, inclusion_opportunity, _is_stale_failure, _token_matches_domain,
    _classify_by_domain,
)
from scripts.registry_pipeline_diff import _expected_override
from api.queries.question_router import outreach_feasibility
from api.queries.sitemap_coverage import _NOISE_SLUG


# ─────────────────────────────────────────────────────────────────────────────
# source_type: domain rules beat page_type
# ─────────────────────────────────────────────────────────────────────────────

def test_vendor_forum_is_ugc_not_competitor():
    # community.cvent.com/discussion/... classifies competitor at page_type
    # level (brand token wins the domain match); the slot is user discussion.
    assert source_type({"domain": "community.cvent.com", "page_type": "competitor"}) == "ugc"


def test_vendor_root_domain_stays_competitor():
    assert source_type({"domain": "cvent.com", "page_type": "competitor"}) == "competitor"


def test_review_platform_beats_competitor_classification():
    assert source_type({"domain": "coursera.org", "page_type": "competitor"}) == "review"


def test_reference_and_default_buckets():
    assert source_type({"domain": "en.wikipedia.org", "page_type": "guide"}) == "reference"
    assert source_type({"domain": "someblog.com", "page_type": "guide", "status": "ok"}) == "editorial"
    assert source_type({"domain": "youtube.com", "page_type": "video"}) == "other"


def test_registry_override_beats_runtime_page_type(monkeypatch):
    import api.queries.page_facts as pf

    monkeypatch.setattr(pf, "_load_brand_registry", lambda: [{
        "name": "Pinned Platform",
        "type": "platform",
        "names": ["Pinned Platform"],
        "tokens": set(),
        "domains": {"pinned.example"},
    }])
    assert pf.source_type({"domain": "pinned.example", "page_type": "competitor"}) == "review"


def test_expected_override_exemption():
    assert _expected_override(
        "community.cvent.com",
        "https://community.cvent.com/discussion/123",
        "ugc",
    ) is True
    assert _expected_override(
        "linkedin.com",
        "https://linkedin.com/learning/topics/event-planning",
        "review",
    ) is True
    assert _expected_override(
        "coursera.org",
        "https://coursera.org/learn/introduction-to-events-management",
        "competitor",
    ) is True
    assert _expected_override(
        "cvent.com",
        "https://cvent.com/blog/best-event-planning-tools",
        "competitor",
    ) is False


def test_unread_unclassified_page_abstains_from_vote():
    # fetch failed + no domain rule -> page_type is the "editorial" FALLBACK,
    # not a classification: bucket as other, abstain from the dominance vote.
    for status in ("fetch_failed", "blocked_robots", "not_html", "too_large"):
        assert source_type({"domain": "indeed.com", "page_type": "editorial",
                            "status": status}) == "other", status
    # a successfully READ editorial page still votes
    assert source_type({"domain": "indeed.com", "page_type": "editorial",
                        "status": "ok"}) == "editorial"


def test_domain_classified_pages_vote_even_unfetched():
    # type came from the domain, not the page body - the vote stands
    assert source_type({"domain": "pennfoster.edu", "page_type": "competitor",
                        "status": "fetch_failed"}) == "competitor"
    assert source_type({"domain": "usa.gov", "page_type": "government",
                        "status": "fetch_failed"}) == "reference"
    assert source_type({"domain": "reddit.com", "page_type": "community",
                        "status": "not_fetched"}) == "ugc"
    assert source_type({"domain": "trustpilot.com", "page_type": "editorial",
                        "status": "fetch_failed"}) == "review"  # allowlist beats fallback


def test_competitor_directory_pages_do_not_trigger_inclusion():
    facts = {
        "domain": "alison.com",
        "url": "https://alison.com/tag/event-planning",
        "status": "ok",
        "page_type": "directory",
        "brand_mentions": {"Alison": 3},
        "qc_mentioned": False,
    }
    assert source_type(facts) == "competitor"
    assert inclusion_opportunity(facts) is False


# ─────────────────────────────────────────────────────────────────────────────
# Subpath carve-outs: a product surface under a community/review root
# ─────────────────────────────────────────────────────────────────────────────

def test_linkedin_learning_is_review_not_ugc():
    # linkedin.com/learning is LinkedIn Learning's course catalog - a platform
    # slot (claim/get listed), not the social feed's discussion slot.
    facts = {"domain": "linkedin.com", "status": "blocked_robots",
             "page_type": "editorial",
             "url": "https://linkedin.com/learning/topics/event-planning"}
    assert source_type(facts) == "review"


def test_linkedin_learning_override_beats_stale_community_type():
    facts = {"domain": "linkedin.com", "status": "not_fetched",
             "page_type": "community",
             "url": "https://linkedin.com/learning/topics/event-planning"}
    assert source_type(facts) == "review"


def test_linkedin_profiles_stay_community():
    assert _classify_by_domain("https://linkedin.com/company/event-logistics-inc.", []) == "community"
    assert _classify_by_domain("https://linkedin.com/learning/topics/event-planning", []) is None


def test_coursera_learn_product_page_is_competitor_catalog_stays_review():
    # /learn/<slug> is an individual course product page (the Udemy pattern);
    # the /courses catalog keeps the review slot.
    product = {"domain": "coursera.org", "status": "ok", "page_type": "competitor",
               "url": "https://coursera.org/learn/introduction-to-events-management"}
    catalog = {"domain": "coursera.org", "status": "ok", "page_type": "competitor",
               "url": "https://coursera.org/courses?query=event+management"}
    assert source_type(product) == "competitor"
    assert source_type(catalog) == "review"


# ─────────────────────────────────────────────────────────────────────────────
# Brand-token domain match: label boundaries, never substrings
# ─────────────────────────────────────────────────────────────────────────────

def test_brand_token_matches_on_label_boundaries():
    assert _token_matches_domain("pennfoster", "pennfoster.edu")           # = label
    assert _token_matches_domain("pennfoster", "pennfostergroup.com")      # label prefix
    assert _token_matches_domain("purdue", "lifelonglearning.purdueforlife.org")
    assert _token_matches_domain("caninecollege", "caninecollege.akc.org")  # subdomain label
    assert _token_matches_domain("nyiadedu", "nyiad.edu")                  # domain-form brand
    assert _token_matches_domain("calmcaninesacademy", "calmcanines.academy")
    assert _token_matches_domain("cventcom", "community.cvent.com")        # trailing chain
    assert _token_matches_domain("pennfoster", "penn-foster.com")          # hyphens squash


def test_brand_token_never_matches_mid_label_substrings():
    # the selar.com squat-host class: a brand token buried inside a label
    assert not _token_matches_domain("edxuniversity", "wedxuniversity.selar.com")
    assert not _token_matches_domain("edxuniversity", "w-edx-university.selar.com")
    assert not _token_matches_domain("eventplanningcom", "qceventplanning.com")
    assert _classify_by_domain("https://wedxuniversity.selar.com/3td3",
                               ["edX University"]) is None


# ─────────────────────────────────────────────────────────────────────────────
# outreach_feasibility: registry -> affordance -> source-type default
# ─────────────────────────────────────────────────────────────────────────────

def test_registry_overrides(monkeypatch):
    assert outreach_feasibility({"domain": "reddit.com"})["feasibility"] == "open"
    assert outreach_feasibility({"domain": "coursera.org"})["feasibility"] == "gated"
    assert outreach_feasibility({"domain": "en.wikipedia.org"})["feasibility"] == "closed"
    assert outreach_feasibility({"domain": "grants.gov"})["feasibility"] == "closed"


def test_page_affordance_scan():
    open_page = {"domain": "unknownblog.com", "page_type": "editorial", "status": "ok",
                 "title": "Best pet courses", "headings": ["Write for us"],
                 "content_excerpt": "..."}
    feas = outreach_feasibility(open_page)
    assert feas["feasibility"] == "open"
    assert "write for us" in feas["evidence"].lower()

    gated_page = {"domain": "unknownblog.com", "page_type": "editorial", "status": "ok",
                  "title": "Best pet courses", "headings": [],
                  "content_excerpt": "Questions? Contact us at editor@unknownblog.com"}
    assert outreach_feasibility(gated_page)["feasibility"] == "gated"


def test_source_type_defaults_when_page_unreadable():
    assert outreach_feasibility(
        {"domain": "someforum.io", "page_type": "community", "status": "not_fetched"}
    )["feasibility"] == "open"          # ugc -> participate
    assert outreach_feasibility(
        {"domain": "unknownblog.com", "page_type": "editorial", "status": "fetch_failed"}
    )["feasibility"] == "unknown"       # editorial, unread -> triage, not a guess


# ─────────────────────────────────────────────────────────────────────────────
# coverage matcher junk-page exclusion (class rule, not one-off URLs)
# ─────────────────────────────────────────────────────────────────────────────

EXCLUDED = [
    "https://www.qceventplanning.com/qc-event-and-wedding-planner-rlsa",
    "https://www.qcdesignschool.com/rm/become-an-interior-decorator",
    "https://www.qcpetstudies.com/certification-courses/rm/become-a-professional-dog-groomer",
    "https://www.qcpetstudies.com/terms",
    "https://www.qcdesignschool.com/terms-gb",
    "https://www.qccareerschool.com/privacy-policy",
    "https://www.qccareerschool.com/404",
    "https://www.qcmakeupacademy.com/404-2",
    "https://www.qcpetstudies.com/contact-us",
    "https://www.qcmakeupacademy.com/contact-follow-up",
    "https://www.qcmakeupacademy.com/about-qc/qc-affiliate-program",
]

MATCHABLE = [
    "https://www.qcdesignschool.com/online-courses/home-staging",      # not "staging" junk
    "https://www.qcmakeupacademy.com/testimonials-and-showcase",       # not a test page
    "https://www.qcpetstudies.com/grooming-career-guide",
    "https://www.qcpetstudies.com/about/faq",
    "https://www.qceventplanning.com/student-success",
    "https://www.qcpetstudies.com/certification-courses/dog-training",
]


def test_junk_page_classes_excluded():
    for url in EXCLUDED:
        assert _NOISE_SLUG.search(url), f"should be excluded: {url}"


def test_real_pages_stay_matchable():
    for url in MATCHABLE:
        assert not _NOISE_SLUG.search(url), f"should be matchable: {url}"


# ─────────────────────────────────────────────────────────────────────────────
# page_facts failure-retry window
# ─────────────────────────────────────────────────────────────────────────────

def _at(days_ago):
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()


def test_failures_retry_after_window_successes_never():
    assert _is_stale_failure({"status": "fetch_failed", "fetched_at": _at(15)}) is True
    assert _is_stale_failure({"status": "fetch_failed", "fetched_at": _at(2)}) is False
    assert _is_stale_failure({"status": "ok", "fetched_at": _at(400)}) is False
    assert _is_stale_failure({"status": "not_fetched", "fetched_at": _at(400)}) is False
    assert _is_stale_failure({"status": "blocked_robots"}) is True  # no timestamp -> retry


# ─────────────────────────────────────────────────────────────────────────────
# Brand-token domain match is provisional: content decides for fetched pages
# ─────────────────────────────────────────────────────────────────────────────

def _wire_fetch(monkeypatch, brands, llm_result):
    import api.queries.page_facts as pf
    monkeypatch.setattr(pf, "get_cached_fact", lambda url: None)
    monkeypatch.setattr(pf, "load_competitor_brands", lambda min_len=4: brands)
    monkeypatch.setattr(pf, "_fetch_html",
                        lambda url: ("<html><title>Jobs With Dogs</title>"
                                     "<body><p>career guide text</p></body></html>", url, None))
    monkeypatch.setattr(pf, "_classify_editorial_llm", lambda *a: llm_result)
    monkeypatch.setattr(pf, "_store", lambda facts, _cache: facts)
    return pf


def test_fetched_brand_domain_page_classified_by_content(monkeypatch):
    # "Purdue" sits in the noisy extracted brand list, but the fetched page is
    # an association/guide page - content wins over the domain token.
    pf = _wire_fetch(monkeypatch, ["Purdue"], ("association", "llm"))
    facts = pf.get_page_facts("https://vet.purdue.edu/ccc/about.php")
    assert facts["page_type"] == "association"
    assert facts["page_type_source"] == "llm"


def test_fetched_brand_domain_page_confirmed_provider_stays_competitor(monkeypatch):
    pf = _wire_fetch(monkeypatch, ["Penn Foster"], ("competitor", "llm"))
    facts = pf.get_page_facts("https://pennfoster.edu/programs/dog-grooming")
    assert facts["page_type"] == "competitor"


def test_llm_failure_falls_back_to_domain_match(monkeypatch):
    pf = _wire_fetch(monkeypatch, ["Penn Foster"], ("editorial", "fallback"))
    facts = pf.get_page_facts("https://pennfoster.edu/programs/dog-grooming")
    assert facts["page_type"] == "competitor"
    assert facts["page_type_source"] == "domain"


def test_unfetched_brand_domain_page_keeps_competitor(monkeypatch):
    import api.queries.page_facts as pf
    monkeypatch.setattr(pf, "get_cached_fact", lambda url: None)
    monkeypatch.setattr(pf, "load_competitor_brands", lambda min_len=4: ["Penn Foster"])
    monkeypatch.setattr(pf, "_fetch_html", lambda url: (None, url, "fetch_failed"))
    monkeypatch.setattr(pf, "_store", lambda facts, _cache: facts)
    facts = pf.get_page_facts("https://pennfoster.edu/programs/dog-grooming")
    assert facts["page_type"] == "competitor"
    assert facts["status"] == "fetch_failed"


# ─────────────────────────────────────────────────────────────────────────────
# defer_llm: bulk populate never calls the LLM; deferred rows upgrade lazily
# ─────────────────────────────────────────────────────────────────────────────

def _llm_must_not_run(*a):
    raise AssertionError("LLM tiebreak called on the deferred path")


def _wire_deferred_populate(monkeypatch, brands, html):
    import api.queries.page_facts as pf
    monkeypatch.setattr(pf, "get_cached_fact", lambda url: None)
    monkeypatch.setattr(pf, "load_competitor_brands", lambda min_len=4: brands)
    monkeypatch.setattr(pf, "_fetch_html", lambda url: (html, url, None))
    monkeypatch.setattr(pf, "_classify_editorial_llm", _llm_must_not_run)
    monkeypatch.setattr(pf, "_store", lambda facts, _cache: facts)
    return pf


def test_defer_llm_brand_domain_page_stays_provisional_competitor(monkeypatch):
    pf = _wire_deferred_populate(
        monkeypatch, ["Penn Foster"],
        "<html><title>Dog Grooming</title><body><p>enroll today</p></body></html>")
    facts = pf.get_page_facts("https://pennfoster.edu/programs/dog-grooming",
                              defer_llm=True)
    assert (facts["page_type"], facts["page_type_source"]) == ("competitor", "deferred")


def test_defer_llm_ambiguous_editorial_page_stays_provisional(monkeypatch):
    pf = _wire_deferred_populate(
        monkeypatch, [],
        "<html><title>Dog Grooming Careers</title><body><p>career text</p></body></html>")
    facts = pf.get_page_facts("https://someblog.com/dog-grooming-careers",
                              defer_llm=True)
    assert (facts["page_type"], facts["page_type_source"]) == ("editorial", "deferred")


def test_defer_llm_heuristic_hit_still_classifies(monkeypatch):
    pf = _wire_deferred_populate(
        monkeypatch, [],
        "<html><title>Best Dog Grooming Courses Ranked</title>"
        "<body><p>our top picks</p></body></html>")
    facts = pf.get_page_facts("https://someblog.com/picks", defer_llm=True)
    assert (facts["page_type"], facts["page_type_source"]) == ("roundup", "heuristic")


def _deferred_row(url, page_type):
    return {
        "url": url, "domain": url.split("/")[2], "status": "ok",
        "page_type": page_type, "page_type_source": "deferred",
        "title": "Some Title", "headings": ["A Heading"],
        "content_excerpt": "some cached body text",
    }


def _wire_cached_deferred(monkeypatch, brands, row):
    import api.queries.page_facts as pf

    def _no_fetch(url):
        raise AssertionError("deferred upgrade must reuse the cached fetch")

    monkeypatch.setattr(pf, "get_cached_fact", lambda url: row)
    monkeypatch.setattr(pf, "load_competitor_brands", lambda min_len=4: brands)
    monkeypatch.setattr(pf, "_fetch_html", _no_fetch)
    monkeypatch.setattr(pf, "_store", lambda facts, _cache: facts)
    return pf


def test_normal_read_upgrades_deferred_row_without_refetch(monkeypatch):
    row = _deferred_row("https://someblog.com/dog-grooming-careers", "editorial")
    pf = _wire_cached_deferred(monkeypatch, [], row)
    monkeypatch.setattr(pf, "_classify_editorial_llm", lambda *a: ("guide", "llm"))
    facts = pf.get_page_facts(row["url"])
    assert (facts["page_type"], facts["page_type_source"]) == ("guide", "llm")


def test_deferred_read_returns_deferred_row_unchanged(monkeypatch):
    row = _deferred_row("https://someblog.com/dog-grooming-careers", "editorial")
    pf = _wire_cached_deferred(monkeypatch, [], row)
    monkeypatch.setattr(pf, "_classify_editorial_llm", _llm_must_not_run)
    facts = pf.get_page_facts(row["url"], defer_llm=True)
    assert facts["page_type_source"] == "deferred"


def test_upgrade_with_llm_down_stays_deferred(monkeypatch):
    # Unlike the eager path's terminal fallback stamp, a failed lazy upgrade
    # keeps the row retryable - and keeps the domain match's provisional type.
    row = _deferred_row("https://pennfoster.edu/programs/dog-grooming", "competitor")
    pf = _wire_cached_deferred(monkeypatch, ["Penn Foster"], row)
    monkeypatch.setattr(pf, "_classify_editorial_llm",
                        lambda *a: ("editorial", "fallback"))
    facts = pf.get_page_facts(row["url"])
    assert (facts["page_type"], facts["page_type_source"]) == ("competitor", "deferred")
