"""
Site-wide, LLM-free structural/schema audit of QC's own pages - the cheap
counterpart to the FIX-branch scorecard (scorecard.py). Where scorecard.py
compares one QC page against a specific tracked question's cited competitor
pages (semantic LLM calls per page, per-question, cooldown-gated), this
sweeps every URL in qc_sitemaps.json and checks only the `deterministic` +
`ratio` features from geo_features.json against the page itself - no
competitor data, no LLM call, no tracked question. `query_term_coverage`
(the one ratio feature that needs a question) is excluded here and stays
exclusively a FIX-branch concern.

Severity reuses the existing geo_weight vocabulary (high/medium/low) rather
than inventing new labels. Low-weight misses (faq_schema, org_schema, ...)
are kept in a separate hygiene bucket, never the main issue list -
geo_features.json's own citation-correlation notes say these measure "near-
zero independent effect" on citation, so flagging them as high-severity (the
way some commercial AEO tools do) would misrepresent our own data.

No new DB table: this computes on demand from the already-cached page_facts
table (get_pages_facts - no LLM call for QC's own pages, network fetch only
on cache miss/stale), so there is no cooldown/generation-status gating to
build, unlike the LLM-metered recommendation engines.
"""

from api.queries.page_facts import get_pages_facts, page_genre, school_for_url
from api.queries.scorecard import (
    _load_features, _deterministic_present, _ratio_value, _fix_hint,
    _effective_geo_weight, _INAPPLICABLE_ON_COMMERCIAL,
)
from api.queries.sitemap_coverage import load_sitemap_cache

_SEVERITY_RANK = {"high": 2, "medium": 1, "low": 0}


def _audit_features():
    """geo_features.json's deterministic + ratio features, minus
    query_term_coverage (needs a tracked question - not available here)."""
    return [f for f in _load_features()
            if f["detection"] in ("deterministic", "ratio") and f["id"] != "query_term_coverage"]


def _all_qc_urls():
    """Every URL across every QC domain in the cached sitemap snapshot
    (api/knowledge/qc_sitemaps.json), or [] if it hasn't been fetched yet
    (sitemap_coverage.refresh_sitemap_cache)."""
    cache = load_sitemap_cache()
    if not cache:
        return []
    urls = []
    for domain_urls in (cache.get("domains") or {}).values():
        urls.extend(domain_urls)
    return sorted(set(urls))


def _page_issues(facts, features):
    """Deterministic + ratio findings for one page, scored against its own
    presence check / fixed literature target - no winner comparison at all.
    Returns (issues, hygiene): hygiene holds low-geo_weight misses
    separately so they never inflate the headline issue count."""
    genre = page_genre(facts)
    issues, hygiene = [], []
    for feat in features:
        if feat["id"] in _INAPPLICABLE_ON_COMMERCIAL and genre == "commercial":
            continue
        weight = _effective_geo_weight(feat, genre)

        if feat["detection"] == "deterministic":
            if _deterministic_present(feat["id"], facts):
                continue
            row = {"id": feat["id"], "label": feat["label"], "geo_weight": weight,
                   "kind": "missing", "value": None, "detail": None}
        else:  # ratio
            value = _ratio_value(feat["id"], facts, question=None)
            in_range = value is not None and feat["target_min"] <= value <= feat["target_max"]
            if value is None or in_range:
                continue
            row = {"id": feat["id"], "label": feat["label"], "geo_weight": weight,
                   "kind": "out_of_range", "value": value,
                   "target_min": feat["target_min"], "target_max": feat["target_max"],
                   "unit": feat["unit"], "detail": _fix_hint(feat, value, in_range)}

        (hygiene if weight == "low" else issues).append(row)
    return issues, hygiene


def run_site_audit(school=None, force=False):
    """Site-wide structural/schema audit across every cached QC URL
    (optionally filtered to one school). No LLM calls, no competitor data -
    see module docstring. `force=True` bypasses the page_facts cache and
    re-fetches every page's HTML."""
    urls = _all_qc_urls()
    if school:
        urls = [u for u in urls if school_for_url(u) == school]
    if not urls:
        return {"pages": [], "issues_summary": [], "hygiene_summary": [],
                "urls_total": 0, "urls_readable": 0}

    features = _audit_features()
    # defer_llm=True: belt-and-suspenders - QC's own pages already never
    # reach the LLM classification branch (domain alone resolves
    # page_type="qc_owned"), but this sweep must stay LLM-free even if that
    # ever changes.
    facts_list = get_pages_facts(urls, force=force, defer_llm=True)

    pages = []
    issue_pages, hygiene_pages = {}, {}
    readable = 0

    for facts in facts_list:
        url = facts.get("final_url") or facts["url"]
        if facts.get("status") != "ok":
            pages.append({"url": url, "school": school_for_url(url), "status": facts.get("status"),
                          "page_type": facts.get("page_type"), "issues": [],
                          "critical_count": 0, "medium_count": 0})
            continue

        readable += 1
        issues, hygiene = _page_issues(facts, features)
        for row in issues:
            bucket = issue_pages.setdefault(
                row["id"], {"label": row["label"], "geo_weight": row["geo_weight"], "pages": []})
            bucket["pages"].append(url)
        for row in hygiene:
            bucket = hygiene_pages.setdefault(
                row["id"], {"label": row["label"], "geo_weight": row["geo_weight"], "pages": []})
            bucket["pages"].append(url)

        pages.append({
            "url": url, "school": school_for_url(url), "status": "ok",
            "page_type": facts.get("page_type"),
            "issues": issues,
            "critical_count": sum(1 for r in issues if r["geo_weight"] == "high"),
            "medium_count": sum(1 for r in issues if r["geo_weight"] == "medium"),
        })

    def _summarize(bucket_map):
        return sorted(
            [{"feature_id": fid, **bucket, "page_count": len(bucket["pages"])}
             for fid, bucket in bucket_map.items()],
            key=lambda r: (-_SEVERITY_RANK.get(r["geo_weight"], 0), -r["page_count"]),
        )

    return {
        "pages": pages,
        "issues_summary": _summarize(issue_pages),
        "hygiene_summary": _summarize(hygiene_pages),
        "urls_total": len(urls),
        "urls_readable": readable,
    }


if __name__ == "__main__":
    import io
    import sys

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    arg_school = sys.argv[1] if len(sys.argv) > 1 else None
    result = run_site_audit(arg_school)
    print(f"{result['urls_readable']}/{result['urls_total']} pages readable"
          + (f" (school={arg_school})" if arg_school else ""))
    print(f"{len(result['issues_summary'])} issue type(s), "
          f"{len(result['hygiene_summary'])} hygiene-only type(s)")
    for row in result["issues_summary"]:
        print(f"  [{row['geo_weight']:6}] {row['label']} - {row['page_count']} page(s)")
    if result["hygiene_summary"]:
        print("hygiene (low citation impact, not counted above):")
        for row in result["hygiene_summary"]:
            print(f"  [{row['geo_weight']:6}] {row['label']} - {row['page_count']} page(s)")
