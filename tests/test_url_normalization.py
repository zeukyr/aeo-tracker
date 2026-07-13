"""
URL normalization (src/parsing/urls): the canonical form every URL-keyed read
path uses, so tracking-param variants of one page never fragment citation
counts or the dominance vote.
"""

from src.parsing.urls import normalize_url, merge_url_counts


def test_strips_tracking_params():
    assert (normalize_url("https://pennfoster.edu/programs/dog-grooming?utm_source=openai")
            == "https://pennfoster.edu/programs/dog-grooming")
    assert (normalize_url("https://example.com/a?gclid=x&fbclid=y&ref=z&srsltid=w")
            == "https://example.com/a")


def test_keeps_meaningful_params():
    # youtube's ?v= IS the page identity; strip only the tracking noise
    assert (normalize_url("https://www.youtube.com/watch?v=abc123&utm_source=openai")
            == "https://youtube.com/watch?v=abc123")


def test_scheme_www_and_trailing_slash():
    assert normalize_url("http://www.Example.com/path/") == "https://example.com/path"
    assert normalize_url("https://www.pdga.online/") == "https://pdga.online"


def test_non_http_and_empty_inputs_pass_through():
    assert normalize_url("mailto:someone@example.com") == "mailto:someone@example.com"
    assert normalize_url("") == ""
    assert normalize_url(None) is None


def test_idempotent():
    u = normalize_url("https://www.example.com/a/?utm_source=openai")
    assert normalize_url(u) == u


def test_merge_url_counts_collapses_variants():
    rows = [
        {"url": "https://www.example.com/a?utm_source=openai", "count": 2},
        {"url": "https://example.com/a", "count": 3},
        {"url": "https://example.com/b", "count": 4},
    ]
    merged = merge_url_counts(rows)
    assert merged == [
        {"url": "https://example.com/a", "count": 5},
        {"url": "https://example.com/b", "count": 4},
    ]
