"""
Registry-vs-pipeline diff: for every reviewed row of brand_registry_review.csv,
what does the RUNTIME pipeline (page_facts domain rules + source_type
bucketing) actually decide for that brand's cited pages - and does it agree
with what the row's proposed_type implies?

Nothing at runtime reads the registry: the pipeline re-derives classification
from mention_response_brands + domain rules, so a row can drift out of sync
silently. Skillshare and Alison sat typed "platform" while skillshare.com /
alison.com classified competitor via the brand-token domain match (no
_REVIEW_DOMAINS or subpath rule routes them to the review bucket). This
script finds the rest of that class. READ-ONLY: prints a report, writes
nothing.

What a proposed_type IMPLIES at runtime, compared at the level that changes
ROUTING (the ownable-vs-non-ownable bit first, then which non-ownable bucket):
    competitor       -> an ownable bucket: competitor or editorial (the two
                        route identically - a rival's cited blog guide
                        bucketing "editorial" is page-level nuance, not drift)
    platform         -> review            (non-ownable, claim/get listed)
    certifying_body  -> certifying_body   (non-ownable, pursue listing)
    not_actionable   -> anything BUT competitor (must not swing the vote
                        toward "competitive loss")

Evidence, strongest first, per domain attributed to the row by the same
label-boundary token match the runtime uses:
    cached   source_type() over real page_facts rows on that domain
    simulated  _classify_by_domain() on the cited URL (what the pipeline
               would stamp on first sight); "content-decides" when the
               domain alone decides nothing - not counted as a conflict

    python -m scripts.registry_pipeline_diff
"""

import csv
import os
from collections import Counter, defaultdict

from api.db import get_connection
from src.parsing.urls import normalize_url
from api.queries.page_facts import (
    _brand_token, _classify_by_domain, _domain_of, _subpath_source_type,
    _token_matches_domain, _UGC_SUBDOMAIN, load_competitor_brands,
    source_type,
)

REGISTRY_PATH = os.path.join(os.path.dirname(__file__), "..", "brand_registry_review.csv")

# {proposed_type: buckets that AGREE with it}; a bucket outside the set is
# drift. None-valued entries flag only the "competitor" bucket (see docstring).
AGREEING_BUCKETS = {
    "competitor":      {"competitor", "editorial"},
    "platform":        {"review"},
    "certifying_body": {"certifying_body"},
    "not_actionable":  None,
}


def _load_registry():
    with open(os.path.abspath(REGISTRY_PATH), encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def _row_tokens(row):
    """The row's brand tokens as the runtime matcher sees them (>= 6 chars,
    every variant - runtime matches raw variant names, not the canonical)."""
    names = [row["canonical_name"]] + row["variants"].split("; ")
    return {t for t in (_brand_token(n) for n in names if n) if len(t) >= 6}


def _cited_urls():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT DISTINCT unnest(citations) FROM mention_responses "
                        "WHERE citations IS NOT NULL")
            return sorted({normalize_url(r[0]) for r in cur.fetchall() if r[0]})


def _cached_buckets():
    """{domain: Counter(source bucket over cached page_facts rows)}."""
    buckets = defaultdict(Counter)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT facts FROM page_facts")
            for (facts,) in cur.fetchall():
                buckets[facts.get("domain", "")][source_type(facts)] += 1
    return buckets


def _runtime_verdict(domain, rep_url, cached, brands):
    """(bucket, evidence) for one attributed domain."""
    if domain in cached:
        counted = cached[domain]
        bucket = counted.most_common(1)[0][0]
        return bucket, f"cached page_facts x{sum(counted.values())}"
    page_type = _classify_by_domain(rep_url, brands)
    if page_type is None:
        return "content-decides", "simulated (no domain rule fires)"
    bucket = source_type({"domain": domain, "url": rep_url,
                          "page_type": page_type, "status": "not_fetched"})
    return bucket, f"simulated domain rule ({page_type})"


def _expected_override(domain, rep_url, bucket):
    """True when the observed bucket comes from a deliberate carve-out."""
    if bucket == "ugc" and _UGC_SUBDOMAIN.match(domain):
        return True
    return _subpath_source_type(domain, rep_url) == bucket


def diff():
    rows = _load_registry()
    brands = load_competitor_brands()
    urls = _cited_urls()
    cached = _cached_buckets()

    url_by_domain = {}
    for u in urls:
        url_by_domain.setdefault(_domain_of(u), u)

    mismatches, unverifiable = [], 0
    for row in rows:
        ptype = row["proposed_type"]
        if ptype not in AGREEING_BUCKETS or row["matched_rule"].startswith("low volume"):
            continue
        tokens = _row_tokens(row)
        attributed = sorted(
            {d for d in url_by_domain if any(_token_matches_domain(t, d) for t in tokens)}
            | {d.strip() for d in row["domains"].split(";") if d.strip()}
        )
        if not attributed:
            unverifiable += 1
            continue
        agreeing = AGREEING_BUCKETS[ptype]
        for domain in attributed:
            rep_url = url_by_domain.get(domain, f"https://{domain}")
            bucket, evidence = _runtime_verdict(domain, rep_url, cached, brands)
            if bucket == "content-decides":
                continue
            if _expected_override(domain, rep_url, bucket):
                continue
            bad = (bucket == "competitor") if agreeing is None else (bucket not in agreeing)
            if bad:
                mismatches.append((row["canonical_name"], ptype, domain, bucket, evidence))

    print(f"{len(rows)} registry rows; {unverifiable} with no cited-domain evidence "
          f"(text-mention only - runtime never classifies a page as theirs)\n")
    if not mismatches:
        print("no registry-vs-pipeline mismatches")
    for name, ptype, domain, bucket, evidence in mismatches:
        implied = " or ".join(sorted(AGREEING_BUCKETS[ptype] or {"anything-but-competitor"}))
        print(f"  {name:<38} registry={ptype:<16} implies {implied:<24} "
              f"runtime={bucket:<16} on {domain}  [{evidence}]")
    return mismatches


if __name__ == "__main__":
    diff()
