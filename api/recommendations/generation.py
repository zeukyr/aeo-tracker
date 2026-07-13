"""Batch assembly for deterministic recommendation engines."""

from api.queries.concern_engine import build_concern_recommendations
from api.queries.credibility import build_credibility_recommendation
from api.queries.question_router import build_router_recommendations
from api.queries.tab1_strategy import strategic_evidence
from api.recommendations.prioritization import apply_priority_ranking
from src.logger import logger


def generate_recommendations(days=None):
    """Build, enrich, and rank one recommendation batch plus its triage queue."""
    recommendations, triage = build_router_recommendations(days)
    if triage:
        reasons = {}
        for item in triage:
            reasons[item["reason"]] = reasons.get(item["reason"], 0) + 1
        logger.info("Router triage: %s losing question(s) not auto-actioned: %s", len(triage), reasons)

    recommendations.extend(build_concern_recommendations(days))
    credibility_recommendation = build_credibility_recommendation(days)
    if credibility_recommendation:
        recommendations.append(credibility_recommendation)

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
    return apply_priority_ranking(recommendations, days), triage
