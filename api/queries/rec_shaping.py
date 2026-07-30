"""
Shared last-mile shaping for the Bucket C engines (concern_engine.py,
credibility.py, competitive_content.py): evidence-based confidence instead of
flat literals, a citability format spec, a pre-measurement checkpoint note,
and a citation-dominance vote so "missing content" recs route to the right
channel instead of always defaulting to "publish."

The dominance vote and channel resolution are NOT reimplemented here - they
delegate to the exact primitives question_router.py already uses correctly
for its per-question BUILD vs REACH_OUT routing (page_facts.source_votes,
question_router.outreach_feasibility), so a Bucket C rec and a question-router
rec agree about ownability/channel for the same evidence.

Lives in api/queries/ (not api/recommendations/) deliberately: the three
engines above import it, and api/recommendations/__init__.py eagerly imports
generation.py -> those same engines, so putting this module inside the
api.recommendations package would deadlock that import on itself. api/queries
has no such eager barrel-import of the engines, so it's cycle-free here.
"""

from api.queries.page_facts import (
    get_pages_facts, source_type,
    SOURCE_TYPE_DOMINANCE, OWNABLE_SOURCE_BUCKETS, NON_OWNABLE_SOURCE_BUCKETS,
    source_votes,
)
from api.queries.question_router import outreach_feasibility, MIN_VOTING_CITATIONS


def volume_confidence(n, min_n, floor, cap, saturate_multiple=4):
    """Linear scale by evidence volume: n<=min_n -> floor; n>=min_n*saturate_multiple -> cap."""
    if not n or n <= min_n:
        return floor
    ceiling_n = min_n * saturate_multiple
    frac = min(1.0, (n - min_n) / (ceiling_n - min_n)) if ceiling_n > min_n else 1.0
    return round(floor + frac * (cap - floor), 2)


def confidence_basis_note(n, min_n, share=None, share_label="non-positive"):
    """Plain-language explainer for a volume_confidence() number."""
    note = f"Volume: {n} (gate: {min_n}+)."
    if share is not None:
        note += f" {share:.0%} {share_label}."
    return note


def format_spec_sentence(label):
    """GEO playbook tactic #3 (Structured Q&A/FAQ), as an appendable clause."""
    return (f'Format for citability: the exact phrase "{label}" as an H2 heading, a direct '
            f"answer in the first sentence beneath it, FAQPage schema markup, no marketing "
            f"adjectives.")


def checkpoint_note():
    """GEO playbook's recrawl-lag timing note, as an interim signal ahead of
    the full diff-in-diff measurement window."""
    return ("Checkpoint: AI engines typically recrawl within 2-4 weeks of publication - check "
            "whether this shows up in citations by then, as an early read before the full "
            "sentiment/citation measurement window closes.")


def dominance_vote(facts):
    """
    Citation-weighted ownability vote over pre-fetched facts (each carrying
    citation_count) - same vote question_router.route_question() runs.
    Returns (bucket, share, top_fact, vote):
      bucket    - leading NON-OWNABLE bucket if it clears SOURCE_TYPE_DOMINANCE
                  and MIN_VOTING_CITATIONS, else None (ownable/mixed/too-thin
                  are all "no clear non-ownable dominance" from a caller's
                  perspective - they keep a content action).
      share     - that bucket's share of voting citations (0.0 if bucket is None).
      top_fact  - highest-cited fact IN that bucket (for a channel/feasibility
                  read), or None.
      vote      - {voters, buckets, ownable_share, non_ownable_share,
                  cleared_bar} - same shape question_router puts in
                  detail.router.vote, so a Bucket C card and a question-router
                  card render with the same VoteMeter component.
    """
    votes = source_votes(facts)
    voters = sum(votes.values())
    ownable = sum(votes.get(b, 0) for b in OWNABLE_SOURCE_BUCKETS)
    non_ownable_share = round((voters - ownable) / voters, 2) if voters else 0.0
    ownable_share = round(ownable / voters, 2) if voters else 0.0
    vote = {
        "voters": voters,
        "buckets": votes,
        "ownable_share": ownable_share,
        "non_ownable_share": non_ownable_share,
    }
    if voters < MIN_VOTING_CITATIONS or non_ownable_share < SOURCE_TYPE_DOMINANCE:
        vote["cleared_bar"] = False
        return None, 0.0, None, vote

    eligible = {b: w for b, w in votes.items() if b in NON_OWNABLE_SOURCE_BUCKETS and w}
    bucket = max(eligible.items(), key=lambda kv: kv[1])[0] if eligible else None
    vote["cleared_bar"] = bucket is not None
    top_fact = None
    if bucket:
        in_bucket = [f for f in facts if source_type(f) == bucket]
        top_fact = max(in_bucket, key=lambda f: f.get("citation_count") or 0, default=None)
    return bucket, non_ownable_share, top_fact, vote


def dominant_channel(cited, limit=20):
    """dominance_vote() for callers with only a raw citation-URL population
    (no pre-fetched facts): `cited` is a {url: count} dict, or a bare
    set/list of URLs (weight 1 each). Fetches/classifies the top `limit`
    by count via the cached get_pages_facts."""
    if isinstance(cited, dict):
        top = sorted(cited.items(), key=lambda kv: -kv[1])[:limit]
    else:
        top = [(u, 1) for u in list(cited)[:limit]]
    if not top:
        empty_vote = {"voters": 0, "buckets": {}, "ownable_share": 0.0,
                       "non_ownable_share": 0.0, "cleared_bar": False}
        return None, 0.0, None, empty_vote
    counts = dict(top)
    facts = get_pages_facts([u for u, _n in top])
    for f in facts:
        f["citation_count"] = counts.get(f["url"], 1)
    return dominance_vote(facts)


def channel_for_bucket(bucket, top_fact):
    """Real channel verdict for a dominant non-ownable bucket, via the same
    registry -> page-affordance -> source-type-default cascade question_router
    uses - so a 'reference' bucket (e.g. Wikipedia/.gov, no real outreach
    channel) resolves to feasibility 'closed', not a miscast outreach action."""
    if bucket is None or top_fact is None:
        return {"channel": None, "feasibility": "unknown",
                "mechanism": "No channel could be determined.", "evidence": "no dominant citation"}
    return outreach_feasibility(top_fact)
