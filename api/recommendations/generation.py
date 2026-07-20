"""Batch assembly for the global brand-signal engines (concern + credibility +
competitive content).

Question-scoped recommendations are no longer auto-picked here - a human
selects which question(s) to generate for (dashboard/src/tabs/Recommendations.jsx),
which drives api.recommendations.question_plan.generate_question_recommendation
one question at a time. This module only refreshes the engines that have no
notion of "which question": brand concerns, overall credibility, and
cross-question competitive win-reason patterns.
"""

from api.queries.concern_engine import build_concern_recommendations
from api.queries.credibility import build_credibility_recommendation
from api.queries.competitive_content import build_competitive_content_recommendations
from api.queries.cited_urls import strategic_evidence
from api.recommendations.prioritization import apply_priority_ranking
from src.logger import logger


def generate_recommendations(days=None):
    """Build, enrich, and rank the concern + credibility + competitive-content
    signal recommendations."""
    recommendations = build_concern_recommendations(days)
    credibility_recommendation = build_credibility_recommendation(days)
    if credibility_recommendation:
        recommendations.append(credibility_recommendation)
    recommendations += build_competitive_content_recommendations(days)

    for rec in recommendations:
        if rec.get("detail") or rec.get("action_type") == "technical":
            continue
        segment = rec.get("segment") or {}
        try:
            evidence = strategic_evidence(segment, school=rec.get("school"))
            if evidence:
                rec["detail"] = {"evidence": evidence}
        except Exception as exc:
            logger.warning("strategic_evidence failed for %s: %s", segment, exc)
    return apply_priority_ranking(recommendations, days)
