"""Recommendation-system public API.

The implementation is grouped by responsibility:

* :mod:`generation` assembles deterministic recommendation batches.
* :mod:`prioritization` ranks recommendations within a batch.
* :mod:`store` owns recommendation persistence and lifecycle queries.

The older ``api.queries.recommendations_synthesis`` module remains as a
compatibility layer while callers migrate to this package.
"""

from api.recommendations.generation import generate_recommendations
from api.recommendations.store import (
    get_generation_status,
    get_recommendation,
    get_saved_recommendations,
    get_triage,
    save_recommendations,
    update_recommendation_status,
)

__all__ = [
    "generate_recommendations",
    "get_generation_status",
    "get_recommendation",
    "get_saved_recommendations",
    "get_triage",
    "save_recommendations",
    "update_recommendation_status",
]
