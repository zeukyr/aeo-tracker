"""Evidence-based, relative priority ranking for recommendation batches."""

from api.queries.recommendation_signals import get_competitive_loss_topics
from src.logger import logger

_PRIORITY_TOP_QUARTILE = 0.25
_PRIORITY_BOTTOM_QUARTILE = 0.25


def _rec_rank_signals(rec):
    """Return ``(family, volume, urgency)`` in comparable ranking units."""
    detail = rec.get("detail") or {}
    router = detail.get("router") or {}
    if router.get("n_citations") is not None:
        volume = router["n_citations"] + 3 * len(router.get("grouped_questions") or [])
        return "router", volume, 1.0 - (router.get("qc_share") or 0.0)
    concern = detail.get("concern") or {}
    if concern.get("count") is not None:
        return "concern", concern["count"], concern.get("share_not_positive") or 0.5
    return "other", None, 0.5


def _rank_reason(rank, total, family, percentile, rec, has_competitive_loss):
    detail = rec.get("detail") or {}
    if family == "router":
        router = detail.get("router") or {}
        volume = f"{router.get('n_citations')} citations at stake on this question"
        grouped = router.get("grouped_questions") or []
        if grouped:
            volume += f" (+{len(grouped)} near-duplicate question(s) folded in)"
        urgency = f"QC is cited in {round((router.get('qc_share') or 0.0) * 100)}% of its responses"
    elif family == "concern":
        concern = detail.get("concern") or {}
        volume = f"the concern was raised {concern.get('count')}x"
        urgency = (f"{round((concern.get('share_not_positive') or 0.5) * 100)}% of those "
                   "responses land not-positive")
    else:
        return f"Ranked {rank}/{total} in this batch (no volume signal - mid-pack by default)."
    reason = (f"Ranked {rank}/{total} in this batch: {volume} - >= {round(percentile * 100)}% of "
              f"{family} recs on volume - and {urgency}.")
    if has_competitive_loss:
        reason += " Boosted x1.25: competitors repeatedly win this topic."
    return reason


def apply_priority_ranking(recommendations, days=None):
    """Annotate recommendations with deterministic, explainable priorities."""
    if not recommendations:
        return recommendations
    try:
        losses = get_competitive_loss_topics(days, min_losses=3)
    except Exception as exc:
        logger.warning("Competitive loss lookup failed: %s", exc)
        losses = {}

    signals = [_rec_rank_signals(rec) for rec in recommendations]
    volumes_by_family = {}
    for family, volume, _ in signals:
        if volume is not None:
            volumes_by_family.setdefault(family, []).append(volume)

    scored = []
    for rec, (family, volume, urgency) in zip(recommendations, signals):
        percentile = (sum(value <= volume for value in volumes_by_family[family]) /
                      len(volumes_by_family[family])) if volume is not None else 0.5
        segment = rec.get("segment") or {}
        topic = (segment.get("value") if segment.get("dimension") == "topic"
                 else ((rec.get("detail") or {}).get("router") or {}).get("topic"))
        loss = losses.get(topic) if topic else None
        score = percentile * urgency * (1.25 if loss else 1.0)
        if loss:
            note = (f" Compounding: competitors ({', '.join(loss['competitors'][:3])}) appear on "
                    f"{loss['losses']} responses in this topic where QC is absent.")
            rec["evidence"] = (rec.get("evidence") or "") + note
        scored.append((score, volume or 0, rec, family, percentile, urgency, bool(loss)))

    scored.sort(key=lambda item: (-item[0], -item[1], str(item[2].get("target"))))
    count = len(scored)
    high_count = max(1, round(count * _PRIORITY_TOP_QUARTILE))
    low_count = max(1, round(count * _PRIORITY_BOTTOM_QUARTILE)) if count >= 4 else 0
    for index, (score, volume, rec, family, percentile, urgency, has_loss) in enumerate(scored):
        rec["priority"] = "high" if index < high_count else "low" if index >= count - low_count else "medium"
        detail = rec.get("detail") or {}
        detail["priority_rank"] = {
            "rank": index + 1, "of": count, "score": round(score, 3), "volume": volume,
            "volume_percentile": round(percentile, 2), "urgency": round(urgency, 2),
            "loss_multiplier": 1.25 if has_loss else 1.0,
            "reason": _rank_reason(index + 1, count, family, percentile, rec, has_loss),
        }
        rec["detail"] = detail
    return recommendations
