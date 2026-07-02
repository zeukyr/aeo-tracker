"""
parser.py

Orchestrator layer. Wires together:
  - deterministic.py   (QC detection — no LLM)
  - llm_client.py       (competitor extraction + sentiment — LLM)
  - merge.py            (position merging — pure logic)
"""

from .deterministic import qc_deterministic_fields
from .llmclient import call_llm
from .merge import locate_competitor_positions, merge_brand_order


def parse_response(question, question_type, raw_response, citations=None):
    citations = citations or []

    det = qc_deterministic_fields(raw_response, citations)

    if question_type == "competition":
        llm_out = call_llm(question, question_type, raw_response, citations)
        return {
            "qc_mentioned": det["qc_mentioned"],
            "qc_cited": det["qc_cited"],
            **llm_out,
        }

    llm_out = call_llm(question, question_type, raw_response, citations)

    competitor_hits = locate_competitor_positions(raw_response, llm_out.get("competitors", []))
    ranked_brands = merge_brand_order(det["qc_brand_hits"], competitor_hits)

    qc_positions = [b["rank_position"] for b in ranked_brands if b["brand_type"] == "qc"]
    qc_mention_order = qc_positions[0] if qc_positions else None

    # merge is_qc (deterministic) with is_inline (LLM) per URL
    is_qc_by_url = {l["url"]: l["is_qc"] for l in det["qc_link_flags"]}
    is_inline_by_url = {l["url"]: l.get("is_inline", False) for l in llm_out.get("links", [])}
    merged_links = [
        {
            "url": url,
            "is_qc": is_qc_by_url.get(url, False),
            "is_inline": is_inline_by_url.get(url, False),
        }
        for url in citations
    ]

    return {
        "qc_mentioned": det["qc_mentioned"],
        "qc_mention_order": qc_mention_order,
        "qc_cited": det["qc_cited"],
        "brands": ranked_brands,
        "links": merged_links,
    }