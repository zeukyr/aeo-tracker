"""
Canonical URL form for everything that keys on a cited URL.

Engines decorate the links they cite (?utm_source=openai, srsltid=...), so the
same page shows up as several distinct strings. Counted raw, that fragments
citation counts and distorts the router's dominance vote - so every read path
that groups/keys by URL (citation rollups, the router's winner sets, the
page_facts cache) must normalize FIRST. Storage stays raw; normalization is a
read-time concern.

Rules (deliberately minimal - never rewrite the identifying parts of a URL):
  - drop tracking params: utm_*, gclid, fbclid, ref, srsltid
    (real params like youtube's ?v= are kept, order preserved)
  - scheme: http -> https
  - host: lowercase, leading "www." dropped
  - path: trailing slashes dropped ("/grooming/" == "/grooming", "/" == "")
"""

from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

_TRACKING_PARAMS = {"gclid", "fbclid", "ref", "srsltid"}


def _is_tracking_param(name):
    return name.lower() in _TRACKING_PARAMS or name.lower().startswith("utm_")


def normalize_url(url):
    """Canonical form of one URL; non-http(s) or unparseable input is returned
    stripped but otherwise untouched."""
    if not url:
        return url
    url = url.strip()
    try:
        parts = urlsplit(url)
    except ValueError:
        return url
    if parts.scheme not in ("http", "https"):
        return url

    host = parts.netloc.lower()
    if host.startswith("www."):
        host = host[4:]

    kept = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
            if not _is_tracking_param(k)]

    return urlunsplit((
        "https",
        host,
        parts.path.rstrip("/"),
        urlencode(kept),
        parts.fragment,
    ))


def merge_url_counts(rows, url_key="url", count_key="count"):
    """
    Re-aggregate [{url, count, ...}] rows after normalization: variants of the
    same page merge into one row (counts summed, first row's other fields kept),
    ordered by merged count desc. For SQL GROUP BY cited_url results - the
    caller should drop its SQL LIMIT and limit the merged output instead.
    """
    merged = {}
    for row in rows:
        key = normalize_url(row[url_key])
        if key in merged:
            merged[key][count_key] += row[count_key]
        else:
            merged[key] = {**row, url_key: key}
    return sorted(merged.values(), key=lambda r: -r[count_key])
