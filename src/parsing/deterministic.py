import re

from .domains import QC_BRAND_LIST, QC_DOMAINS


def find_qc_brand_mentions(raw_response: str):
    """All literal QC brand occurrences as (brand_name, char_index), sorted by position."""
    hits = []
    for brand in QC_BRAND_LIST:
        for m in re.finditer(re.escape(brand), raw_response or "", re.IGNORECASE):
            hits.append((brand, m.start()))
    hits.sort(key=lambda x: x[1])
    return hits


def classify_links_qc(citations: list[str]):
    """Deterministic is_qc flag per citation URL, based on domain match."""
    citations = citations or []
    return [
        {"url": url, "is_qc": any(d in url.lower() for d in QC_DOMAINS)}
        for url in citations
    ]


def qc_deterministic_fields(raw_response: str, citations: list[str]):
    brand_hits = find_qc_brand_mentions(raw_response)
    link_flags = classify_links_qc(citations)
    return {
        "qc_mentioned": bool(brand_hits),
        "qc_brand_hits": brand_hits,          # [(brand, char_index), ...] — used for ordering later
        "qc_cited": any(l["is_qc"] for l in link_flags),
        "qc_link_flags": link_flags,          # merged into final "links" output
    }