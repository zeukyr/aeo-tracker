"""
merge.py

Pure functions for combining QC's deterministic brand-position hits with
the LLM's competitor-position hits into one ranked mention order. No I/O,
no API calls — easy to unit test with plain strings and dicts in, a list
out.
"""


def locate_competitor_positions(raw_response: str, competitors: list[dict]):
    """Find char index for each LLM-reported competitor via its own claimed substring."""
    positioned = []
    for c in competitors:
        name = c.get("name", "")
        snippet = c.get("text_as_written", name)
        idx = raw_response.find(snippet)
        if idx == -1:
            idx = raw_response.lower().find(name.lower())
        if idx != -1:
            positioned.append((name, idx))
        else:
            from src.logger import logger
            logger.warning(f"Could not locate competitor '{name}' in response text; dropping from ranking")
    return positioned


def merge_brand_order(qc_hits, competitor_hits):
    """Combine QC + competitor mentions by position, dedupe by brand, return ranked list."""
    all_hits = [(name, idx, "qc") for name, idx in qc_hits] + \
               [(name, idx, "competitor") for name, idx in competitor_hits]
    all_hits.sort(key=lambda x: x[1])

    seen = set()
    ranked = []
    for name, idx, btype in all_hits:
        if name in seen:
            continue
        seen.add(name)
        ranked.append({"name": name, "brand_type": btype, "rank_position": len(ranked) + 1})
    return ranked