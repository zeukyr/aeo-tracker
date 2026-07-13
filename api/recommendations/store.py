"""Persistence boundary for recommendation records.

The SQL implementation remains temporarily in the legacy compatibility module
because per-question generation still relies on its internal lifecycle helpers.
New application code should import persistence operations from here; this keeps
database concerns out of batch-generation and ranking code while allowing a
later extraction without another API rename.
"""

from api.queries.recommendations_synthesis import (
    get_generation_status,
    get_recommendation,
    get_saved_recommendations,
    get_triage,
    save_recommendations,
    update_recommendation_status,
)

__all__ = [
    "get_generation_status",
    "get_recommendation",
    "get_saved_recommendations",
    "get_triage",
    "save_recommendations",
    "update_recommendation_status",
]
