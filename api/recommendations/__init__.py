"""Recommendation-system public API.

The implementation is grouped by responsibility:

* :mod:`generation` assembles deterministic recommendation batches.
* :mod:`prioritization` ranks recommendations within a batch.
* :mod:`store` owns recommendation persistence and lifecycle queries.
* :mod:`question_plan` owns the on-demand per-question plans.
"""

from api.recommendations.generation import generate_recommendations
from api.recommendations.question_plan import (
    generate_question_recommendation,
    get_question_recommendation_status,
    get_question_recommendations,
)
from api.recommendations.store import (
    get_generation_status,
    get_recommendation,
    get_saved_recommendations,
    save_recommendations,
    update_recommendation_status,
)

__all__ = [
    "generate_recommendations",
    "generate_question_recommendation",
    "get_generation_status",
    "get_question_recommendation_status",
    "get_question_recommendations",
    "get_recommendation",
    "get_saved_recommendations",
    "save_recommendations",
    "update_recommendation_status",
]
