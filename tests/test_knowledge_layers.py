"""
The deterministic classification layers under the router: source-type
bucketing (incl. the cvent-forum case), outreach feasibility, the coverage
matcher's junk-page exclusion, and the page-facts failure-retry window.
"""

from datetime import datetime, timedelta, timezone

from api.queries.page_facts import source_type, _is_stale_failure
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
