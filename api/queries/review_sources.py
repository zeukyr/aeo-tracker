from collections import defaultdict
from urllib.parse import urlparse

from api.db import get_connection, _date_filter, _school_clause_params

REVIEW_SITES = {
    "trustpilot.com":      "Trustpilot",
    "bbb.org":             "Better Business Bureau",
    "yelp.com":            "Yelp",
    "google.com":          "Google",
    "indeed.com":          "Indeed",
    "glassdoor.com":       "Glassdoor",
    "sitejabber.com":      "SiteJabber",
    "reviews.io":          "Reviews.io",
    "g2.com":              "G2",
    "capterra.com":        "Capterra",
    "consumeraffairs.com": "Consumer Affairs",
    "birdeye.com":         "Birdeye",
    "bark.com":            "Bark",
    "reddit.com":          "Reddit",
}

def _extract_domain(url):
    try:
        host = urlparse(url).hostname or ""
        return host.removeprefix("www.")
    except Exception:
        return ""

def get_review_sources(days=None, school=None):
    filter_clause = _date_filter(days).replace("AND created_at", "AND m.created_at")
    school_clause, school_params = _school_clause_params(school)

    # Counts per (domain, competitor_name) from competitor_citation_map
    comp_query = f"""
        SELECT ccm.url, ccm.competitor_name
        FROM competitor_citation_map ccm
        JOIN mention_responses m ON m.id = ccm.mention_response_id
        LEFT JOIN questions q ON q.id = m.question_id
        WHERE 1=1 {filter_clause} {school_clause};
    """

    # QC citation URLs — unnest raw citations[] from responses where QC was mentioned
    qc_query = f"""
        SELECT unnest(m.citations) AS url
        FROM mention_responses m
        LEFT JOIN questions q ON q.id = m.question_id
        WHERE m.qc_mentioned = TRUE
          AND m.citations IS NOT NULL
          {filter_clause} {school_clause};
    """

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(comp_query, school_params)
            comp_rows = cur.fetchall()

            cur.execute(qc_query, school_params)
            qc_rows = cur.fetchall()

    # Aggregate competitor citations by (domain, brand)
    comp_counts = defaultdict(lambda: defaultdict(int))
    for url, competitor in comp_rows:
        domain = _extract_domain(url)
        if domain in REVIEW_SITES:
            comp_counts[domain][competitor] += 1

    # Aggregate QC citations by domain
    qc_counts = defaultdict(int)
    for (url,) in qc_rows:
        domain = _extract_domain(url)
        if domain in REVIEW_SITES:
            qc_counts[domain] += 1

    # Merge into result structure
    all_domains = set(comp_counts.keys()) | set(qc_counts.keys())
    results = []
    for domain in all_domains:
        site_name = REVIEW_SITES[domain]
        qc_total = qc_counts.get(domain, 0)
        comp_total = sum(comp_counts[domain].values())

        brands = []
        if qc_total:
            brands.append({"name": "QC", "is_qc": True, "count": qc_total})
        for brand, count in sorted(comp_counts[domain].items(), key=lambda x: -x[1]):
            brands.append({"name": brand, "is_qc": False, "count": count})

        results.append({
            "site": site_name,
            "domain": domain,
            "total": qc_total + comp_total,
            "qc": qc_total,
            "competitor": comp_total,
            "brands": brands,
        })

    return sorted(results, key=lambda x: -x["total"])
