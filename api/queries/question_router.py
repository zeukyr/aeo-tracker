"""
Per-question recommendation router
(docs/ai/recommendation-question-router-plan.md, §5.1).

Replaces the old "run every builder on every topic, additively" flow with:
select losing questions -> classify each question's cited winners FIRST ->
route to exactly one branch. The feature-diff (Tab 2 scorecard) is a LEAF of
the fix branch, not the entry point - so a course page is never scored against
informational guides (the bug the router exists to kill).

Branches (each losing question terminates in exactly one):

  FIX        QC has a same-kind page that still loses -> per-question
             feature-diff (scorecard), deduped by QC page.
  BUILD      ownable winners (editorial/competitor) and QC lacks the page or
             has the wrong KIND of page - buildability-gated by topic; also
             the fallback for known-unownable winners (wikipedia/.gov ->
             "earn the slot indirectly", genre inferred from any secondary
             ownable presence - see _secondary_ownable_signal). A reach_out-
             branch question with that same secondary signal additionally
             gets a companion build rec (on-demand flow only, topic-gated) -
             the vote picks ONE primary branch, but "also worth building"
             can be true alongside it.
  REACH OUT  non-ownable winners (ugc/review/reference/certifying_body) with
             a real channel (registry / page affordance / source-type default,
             §5.7), or a reputation question whose ownable winners are
             pitchable.
  TRIAGE     everything the router cannot action with confidence - visible,
             never a silent drop:
               fragmented_field       neither the ownable nor the non-ownable
                                      side clears the dominance bar
                                      (deliberately NOT auto-built; flagged
                                      build_candidate when the topic is
                                      buildable, for a human to green-light)
               insufficient_voters    fewer than MIN_VOTING_CITATIONS voting
                                      citations after abstentions - a share
                                      over a handful of votes is not a verdict
               no_cited_winners       QC loses but nothing external is cited
               feasibility_unknown    non-ownable winners, no channel found
               reputation_no_channel  can't build credibility, nothing to pitch

Work-stream note (R9): reach-out recs emit action_type in
{outreach, citation, community}; _work_stream still maps those to "strategic"
until the Tab 3 frontend lands, so the cards stay visible in Strategic Growth.
"""

import os
import re
import json
from collections import Counter
from urllib.parse import urlsplit

from src.logger import logger
from api.db import get_connection, _date_filter
from api.queries.page_facts import (
    get_page_facts,
    get_pages_facts,
    format_gap,
    FORMAT_TO_GENRE,
    source_type,
    registry_brand_type,
    source_votes,
    inclusion_opportunity,
    winner_format,
    school_for_url,
    _root_domain,
    SOURCE_TYPE_DOMINANCE,
    OWNABLE_SOURCE_BUCKETS,
    NON_OWNABLE_SOURCE_BUCKETS,
)
from api.queries.cited_urls import get_question_cited_urls
from api.queries.scorecard import (
    build_scorecard,
    scorecard_to_recommendation,
    scorecard_triage_reason,
    build_winner_checklist,
    build_page_plan,
    CANDIDATE_POOL,
)
from api.queries.sitemap_coverage import diagnose_text_coverage

# Topic gates the BUILD branch only (a reputation question can't build its way
# to credibility) - never selection, never the fix or reach-out branches.
BUILDABLE_TOPICS = {
    "Course Discovery", "How to Become",
    "Starting a Business", "Career Exploration",
}
REPUTATION_TOPICS = {"Brand Credibility", "Competitor Comparison"}

_MAX_QC_SHARE = 0.15          # "losing": QC cited in <= 15% of responses

# Below this many VOTING citations (after "other" abstentions) a share is
# noise, not a verdict - 64% of 3 voters is one page's opinion. Triage as
# insufficient_voters regardless of share.
MIN_VOTING_CITATIONS = 4

# A "secondary ownable signal" floor - deliberately BELOW SOURCE_TYPE_DOMINANCE
# (0.6). The two-stage vote is winner-take-all: whichever side clears 0.6 owns
# the whole routing decision, and the loser's votes are discarded entirely -
# so a question that's 65% ugc/reference and 35% competitor/editorial (a real
# split seen in live data: "How do I become an event designer?" runs 10
# competitor citations alongside 15 ugc) currently produces a reach-out rec
# with NO signal that a build opportunity exists too, and an earn_indirect
# build rec with NO idea what to build (target_genre stayed None even when
# 6 competitor + 6 editorial pages were sitting right there - "how to become
# an event planner"). This is that floor: real enough to act on (not 1-2
# stray citations), without claiming dominance.
_SECONDARY_OWNABLE_SHARE = 0.25
_SECONDARY_OWNABLE_MIN_VOTES = 3

_CHANNELS_PATH = os.path.join(os.path.dirname(__file__), "..", "knowledge", "outreach_channels.json")


# ─────────────────────────────────────────────────────────────────────────────
# Selection: per-question QC citation share, ALL topics (topic-blind)
# ─────────────────────────────────────────────────────────────────────────────

def get_losing_questions(days=None, max_qc_share=_MAX_QC_SHARE):
    """
    Questions where QC is (almost) never cited, weakest first. Deliberately
    topic-blind - buildability gates the build branch, not selection, so no
    category of losing question is swallowed before it's even looked at.
    Only questions with mention_responses appear (sentiment-only questions are
    handled by the concern/credibility engines).
    """
    date_m = _date_filter(days).replace("AND created_at", "AND m.created_at")
    query = f"""
        SELECT q.id, q.question, q.topic, q.school,
               AVG(CASE WHEN m.qc_cited THEN 1 ELSE 0 END) as qc_share,
               COUNT(*) as n_responses,
               COALESCE(SUM(COALESCE(array_length(m.citations, 1), 0)), 0) as n_citations
        FROM mention_responses m
        JOIN questions q ON q.id = m.question_id
        WHERE 1=1 {date_m}
        GROUP BY q.id, q.question, q.topic, q.school
        HAVING AVG(CASE WHEN m.qc_cited THEN 1 ELSE 0 END) <= %s
        ORDER BY 5 ASC, 7 DESC;
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, [max_qc_share])
            rows = cur.fetchall()
    return [
        {
            "question_id": r[0], "question": r[1], "topic": r[2], "school": r[3],
            "qc_share": round(float(r[4]), 3), "n_responses": r[5], "n_citations": int(r[6]),
        }
        for r in rows
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Outreach feasibility (§5.7): registry -> page affordance -> source default
# ─────────────────────────────────────────────────────────────────────────────

_channels_cache = None


def _load_channels():
    global _channels_cache
    if _channels_cache is None:
        with open(_CHANNELS_PATH, "r", encoding="utf-8") as f:
            _channels_cache = json.load(f)
    return _channels_cache


# Self-serve submission/claim affordances visible in page content. A match is
# the evidence - deterministic, no LLM.
_OUTREACH_AFFORDANCE = re.compile(
    r"\b(write for us|submit (a )?(listing|guest|your)|contribute|"
    r"add your (business|school|listing)|claim (this|your) (listing|profile|business)|"
    r"get listed|nominate|advertise with us)\b", re.I)

# A contact route but no self-serve channel -> pitchable, gated.
_CONTACT_HINT = re.compile(r"\bcontact (us|the editor)|editorial team|media inquir|press@|editor@", re.I)

# When the domain is unknown and the page couldn't be read, the ownability
# bucket itself implies the channel.
_SOURCE_TYPE_DEFAULTS = {
    "ugc":       {"channel": "participate", "feasibility": "open",
                  "mechanism": "Participate authentically as a named QC presence (expert answers, AMAs)."},
    "review":    {"channel": "claim", "feasibility": "gated",
                  "mechanism": "Claim or request a QC profile/listing on the platform."},
    "reference": {"channel": "align", "feasibility": "closed",
                  "mechanism": "No direct channel. Publish the authoritative source such pages cite."},
    "certifying_body": {"channel": "accreditation", "feasibility": "gated",
                        "mechanism": "Pursue listing / recognition / accreditation with the certifying "
                                     "body (approved-provider or school directory status)."},
    "editorial": {"channel": "pitch", "feasibility": "unknown",
                  "mechanism": "No verified channel found on the page."},
}


def outreach_feasibility(facts):
    """
    {channel, feasibility: open|gated|closed|unknown, mechanism, evidence}
    for one winning page. Registry override -> page-content affordance scan ->
    source-type default. Deterministic; "unknown" means we failed to classify
    the channel - the router triages that rather than forcing an action.
    """
    registry = _load_channels()
    domain = facts.get("domain", "")
    root = _root_domain(domain)
    entry = registry["domains"].get(root)
    if entry is None and domain.endswith(".gov"):
        entry = registry["gov_tld"]
    if entry:
        return {**{k: entry[k] for k in ("channel", "feasibility", "mechanism")},
                "evidence": f"registry: {root}"}

    if facts.get("status") == "ok":
        haystack = " ".join(filter(None, [
            facts.get("title") or "",
            " ".join(facts.get("headings") or []),
            facts.get("content_excerpt") or "",
        ]))
        m = _OUTREACH_AFFORDANCE.search(haystack)
        if m:
            return {"channel": "submit", "feasibility": "open",
                    "mechanism": f"Use the page's own channel ('{m.group(0)}').",
                    "evidence": f"page affordance: '{m.group(0)}'"}
        if _CONTACT_HINT.search(haystack):
            return {"channel": "pitch", "feasibility": "gated",
                    "mechanism": "Pitch via the site's contact/editorial route.",
                    "evidence": "page offers a contact route, no self-serve channel"}

    default = _SOURCE_TYPE_DEFAULTS.get(source_type(facts))
    if default:
        return {**default, "evidence": f"source-type default: {source_type(facts)}"}
    return {"channel": None, "feasibility": "unknown",
            "mechanism": "No channel could be determined.",
            "evidence": f"unclassified source: {domain or 'no domain'}"}


def _bucket_feasibility(facts_list, bucket):
    """
    Feasibility for a question's dominant bucket: walk that bucket's winners
    by citation weight and take the first conclusive (non-unknown) answer, so
    one unreadable page doesn't hide a reachable channel behind it.
    Returns (feasibility_dict, facts_of_target).
    """
    in_bucket = sorted((f for f in facts_list if source_type(f) == bucket),
                       key=lambda f: -(f.get("citation_count") or 0))
    first = None
    for f in in_bucket:
        feas = outreach_feasibility(f)
        if first is None:
            first = (feas, f)
        if feas["feasibility"] != "unknown":
            return feas, f
    return first if first else ({"channel": None, "feasibility": "unknown",
                                 "mechanism": "No winners in bucket.",
                                 "evidence": "empty bucket"}, None)


# ─────────────────────────────────────────────────────────────────────────────
# Routing
# ─────────────────────────────────────────────────────────────────────────────

def triage(q, reason, build_candidate=False, **extra):
    """A first-class routing outcome (plan §5.9) - never a silent None."""
    return {"branch": "triage", "question": q, "reason": reason,
            "build_candidate": build_candidate, **extra}


def _plurality_format(facts_list):
    """Plurality winner_format() among a set of facts, or None when none are
    format-classifiable. Shared by _secondary_ownable_signal (ownable-bucket
    winners on a non-dominant route) and _build_rec's plain ownable-win
    branch (ownable winners ARE the dominant bucket there) - same question,
    same vote."""
    formats = [f for f in (winner_format(wf) for wf in facts_list) if f]
    return Counter(formats).most_common(1)[0][0] if formats else None


def _secondary_ownable_signal(facts, ownable_share, ownable_votes):
    """
    Whether competitor/editorial winners have a REAL presence even when they
    don't dominate the vote - `_SECONDARY_OWNABLE_SHARE`/`_MIN_VOTES` is a
    deliberately lower bar than SOURCE_TYPE_DOMINANCE: this isn't "which side
    wins the routing decision," it's "is there a signal worth acting on
    alongside whatever wins." None when there isn't (too few ownable votes,
    or none of them format-classifiable) - never guess.

    When present, returns the PLURALITY format among just those ownable
    winners (same per-page vote winner_format uses elsewhere) - what QC
    would build if it acted on this signal - plus counts for evidence text.
    Deliberately no floor/margin gate here (unlike format_gap's
    _FORMAT_FLOOR/_FORMAT_MARGIN): the share+count gate above already
    established this is a real sample, and a secondary signal is "worth
    naming a format for," not "confident enough to suppress a fix rec."
    """
    if ownable_share < _SECONDARY_OWNABLE_SHARE or ownable_votes < _SECONDARY_OWNABLE_MIN_VOTES:
        return None
    ownable_facts = [f for f in facts if source_type(f) in OWNABLE_SOURCE_BUCKETS]
    dominant_format = _plurality_format(ownable_facts)
    if not dominant_format:
        return None
    formats = [f for f in (winner_format(wf) for wf in ownable_facts) if f]
    return {
        "format": dominant_format,
        "genre": FORMAT_TO_GENRE.get(dominant_format),
        "n_winners": len(ownable_facts),
        "n_classified": len(formats),
        # Callers quote this as "X/n_classified are {format}" - must be the
        # count that actually IS the dominant format, not n_classified itself
        # (that's "classified at all," which can silently overstate a weak
        # plurality as if every classified page agreed).
        "n_dominant": formats.count(dominant_format),
    }


def route_question(q, days=None):
    """
    Classify one losing question's cited winners and pick its branch.
    Returns {"branch": "fix"|"build"|"reach_out"|"triage", "question": q,
    "winners": [...facts], "vote": {...}, "dominant": (bucket, share),
    "qc_url", "genre_mismatch", "feasibility", "reason", ...}.

    The vote is TWO-STAGE: the first branching decision is one bit - can QC
    own the winning slot - so competitor and editorial (which route
    identically) must not split the vote against each other. Only when the
    non-ownable side clears the bar do we ask WHICH non-ownable bucket leads,
    because that choice changes behavior (ugc -> participate, review ->
    claim, reference -> align). `dominant` carries (stage-leader bucket,
    stage share) for wording/dedup; `vote` carries the full tally.
    """
    # CANDIDATE_POOL (20), not the cited_urls.py display default (8, tuned for
    # a readable card): the router's dominance/genre votes need real headroom -
    # every losing question has 24+ distinct cited URLs in practice, so an
    # 8-URL cap was starving the vote, not reflecting scarcity. Same pool size
    # the fix-branch scorecard already uses (line ~842) for the same reason.
    winners = get_question_cited_urls(q["question_id"], days, limit=CANDIDATE_POOL)
    if not winners:
        return triage(q, "no_cited_winners")

    counts = {w["url"]: w["count"] for w in winners}
    facts = get_pages_facts([w["url"] for w in winners])
    for f in facts:
        f["citation_count"] = counts.get(f["url"], 0)

    votes = source_votes(facts)
    voters = sum(votes.values())
    buildable = q["topic"] in BUILDABLE_TOPICS
    ownable = sum(votes.get(b, 0) for b in OWNABLE_SOURCE_BUCKETS)
    vote = {
        "voters": voters,
        "buckets": votes,
        "ownable_share": round(ownable / voters, 2) if voters else 0.0,
        "non_ownable_share": round((voters - ownable) / voters, 2) if voters else 0.0,
    }
    secondary_ownable = _secondary_ownable_signal(facts, vote["ownable_share"], ownable)

    def _lead(bucket_names):
        eligible = {b: w for b, w in votes.items() if b in bucket_names and w}
        return max(eligible.items(), key=lambda kv: kv[1])[0] if eligible else None

    # ── too few voters: a share over a handful of citations is not a verdict ──
    if voters < MIN_VOTING_CITATIONS:
        return triage(q, "insufficient_voters", build_candidate=buildable,
                      winners=facts, vote=vote, dominant=(None, 0.0))

    # ── stage 1b: non-ownable field -> stage 2: which non-ownable bucket leads ──
    if vote["non_ownable_share"] >= SOURCE_TYPE_DOMINANCE:
        bucket = _lead(NON_OWNABLE_SOURCE_BUCKETS)
        common = {"question": q, "winners": facts, "vote": vote,
                  "dominant": (bucket, vote["non_ownable_share"]),
                  "secondary_ownable": secondary_ownable}
        feas, target = _bucket_feasibility(facts, bucket)
        if feas["feasibility"] in ("open", "gated"):
            return {"branch": "reach_out", "reason": "non_ownable_winners",
                    "feasibility": feas, "feasibility_target": target, **common}
        if feas["feasibility"] == "closed":   # wikipedia / .gov - KNOWN unownable
            return {"branch": "build", "reason": "earn_indirect",
                    "feasibility": feas, "feasibility_target": target,
                    "qc_url": None, "genre_mismatch": None, **common}
        return triage(q, "feasibility_unknown", winners=facts, vote=vote,
                      dominant=(bucket, vote["non_ownable_share"]), feasibility=feas)

    # ── neither side clears the bar: a finding for a human, not an auto-build ──
    if vote["ownable_share"] < SOURCE_TYPE_DOMINANCE:
        return triage(q, "fragmented_field", build_candidate=buildable,
                      winners=facts, vote=vote, dominant=(None, vote["ownable_share"]))

    # ── stage 1a: ownable field (competitor + editorial vote together) ──
    bucket = _lead(OWNABLE_SOURCE_BUCKETS)
    common = {"question": q, "winners": facts, "vote": vote,
              "dominant": (bucket, vote["ownable_share"]),
              "secondary_ownable": secondary_ownable}

    cov = diagnose_text_coverage(q["question"], school=q["school"], question_id=q["question_id"])
    qc_url = cov.get("qc_url") if cov.get("verdict") == "have_page" else None
    gm = None
    if qc_url:
        # Has a page - but is it the KIND engines reward? A mismatch SUPPRESSES
        # the feature-diff (the core bug fix); the build branch owns that case.
        gm = format_gap(get_page_facts(qc_url), facts)
        if not gm:
            # ── FIX: same-kind vs same-kind, the feature-diff is legitimate ──
            return {"branch": "fix", "reason": "qc_page_same_kind_still_loses",
                    "qc_url": qc_url, "genre_mismatch": None, **common}

    # missing page, or the wrong kind of page -> BUILD, gated by topic
    if buildable:
        return {"branch": "build",
                "reason": "ownable_wrong_kind_page" if gm else "ownable_no_qc_page",
                "qc_url": qc_url, "genre_mismatch": gm, **common}

    # reputation topic: can't build credibility - pitch the winners or triage
    feas, target = _bucket_feasibility(facts, bucket)
    if feas["feasibility"] in ("open", "gated"):
        return {"branch": "reach_out", "reason": "reputation_reach_out",
                "feasibility": feas, "feasibility_target": target,
                "qc_url": qc_url, "genre_mismatch": gm, **common}
    return triage(q, "reputation_no_channel", winners=facts, vote=vote,
                  dominant=(bucket, vote["ownable_share"]),
                  qc_url=qc_url, genre_mismatch=gm)


# ─────────────────────────────────────────────────────────────────────────────
# Leaf builders: route -> recommendation dicts (existing shape untouched)
# ─────────────────────────────────────────────────────────────────────────────

def _segment_for(q):
    """Question-grained segment (R6): measurement scopes to exactly the
    question the rec targets. Topic stays in detail.router for rollups."""
    return {"dimension": "question", "value": q["question"],
            "question_id": str(q["question_id"])}


def _winner_summary(facts, limit=5):
    """`limit=None` returns every fetched winner - used for the card's full
    citations panel, where truncating to 5 would silently drop pages the
    router actually fetched (up to CANDIDATE_POOL=20, scorecard.py)."""
    facts = sorted(facts or [], key=lambda f: -(f.get("citation_count") or 0))
    if limit is not None:
        facts = facts[:limit]
    return [{"url": f["url"], "page_type": f.get("page_type"),
             "source_type": source_type(f), "format": winner_format(f),
             "citation_count": f.get("citation_count") or 0} for f in facts]


def _abstention_reason(f):
    if f.get("page_type") == "video":
        return "video"
    if registry_brand_type(f.get("domain") or "") == "not_actionable":
        return "not_actionable brand"
    if f.get("status") != "ok":
        return "unfetched-unknown-domain"
    if source_type(f) == "other":
        return "unfetched-unknown-domain"
    return "other"


def _benchmarkable(f):
    """
    Whether a winner may appear on a card as a benchmark/evidence URL - the
    same exclusions the dominance vote applies (source_type "other" abstains:
    videos, unread unclassified pages), plus bare homepages: a domain root with
    no path is a citation artifact, not a page to model content on.
    """
    if source_type(f) == "other":
        return False
    path = urlsplit(f.get("final_url") or f.get("url") or "").path
    return bool(path.strip("/"))


def _card_winners(route):
    """The route's winners that are fit to show on a card (see _benchmarkable).
    May be empty - a card then carries no benchmark list, never junk."""
    return [f for f in route.get("winners") or [] if _benchmarkable(f)]


def _winners_evidence(q, facts, limit=4):
    top = sorted(facts, key=lambda f: -(f.get("citation_count") or 0))[:limit]
    pct = round(q["qc_share"] * 100)
    if not top:
        return (f"For '{q['question']}' QC is cited in {pct}% of "
                f"{q['n_responses']} responses.")
    cited = "; ".join(f"{f.get('domain')} ({f.get('citation_count')}x)" for f in top)
    return (f"For '{q['question']}' engines cite {cited} across {q['n_responses']} responses; "
            f"QC is cited in {pct}% of them.")


def _router_detail(route, group=None):
    q = route["question"]
    bucket, share = route.get("dominant") or (None, None)
    vote = route.get("vote") or {}
    winners = route.get("winners") or []
    source_questions = [{
        "question_id": str(r["question"]["question_id"]),
        "question": r["question"]["question"],
        "topic": r["question"].get("topic"),
        "school": r["question"].get("school"),
    } for r in (group or [route])]
    detail = {
        "branch": route["branch"],
        "reason": route.get("reason"),
        "question_id": str(q["question_id"]),
        "question": q["question"],
        "topic": q.get("topic"),
        "qc_share": q["qc_share"],
        "n_citations": q.get("n_citations"),
        "dominant_source": bucket,
        "dominant_share": share,
        "vote": {
            "voters": vote.get("voters"),
            "ownable_share": vote.get("ownable_share"),
            "non_ownable_share": vote.get("non_ownable_share"),
            "buckets": vote.get("buckets"),
            "cleared_bar": (share or 0.0) >= SOURCE_TYPE_DOMINANCE if share is not None else False,
        },
        "winners": _winner_summary(winners, limit=None),
        "abstentions": [{
            "url": f.get("url"),
            "domain": f.get("domain"),
            "page_type": f.get("page_type"),
            "source_type": source_type(f),
            "fetch_status": f.get("status"),
            "reason": _abstention_reason(f),
        } for f in winners if source_type(f) == "other"],
        "source_questions": source_questions,
    }
    if group:
        detail["grouped_questions"] = [r["question"]["question"] for r in group]
    if route.get("feasibility"):
        detail["outreach_feasibility"] = route["feasibility"]
    if route.get("genre_mismatch"):
        detail["genre_mismatch"] = route["genre_mismatch"]
    if route.get("secondary_ownable"):
        detail["secondary_ownable"] = route["secondary_ownable"]
    return detail



# Prose for each format_gap format, used both standalone ("build X") and to
# name QC's existing wrong-format page ("the existing page is a Y").
_FORMAT_LABEL = {
    "how_to":    "a how-to / step-by-step guide",
    "long_form": "a long-form explainer/career guide",
    "listicle":  "a ranked listicle (\"best X\" roundup)",
    "landing":   "a dedicated course/program page",
}


def _build_rec(route, group):
    """One BUILD rec per dedup group. Singletons fire (a lone question can
    carry independent demand); group size is a priority booster, not a gate."""
    q = route["question"]
    gm = route.get("genre_mismatch")
    secondary = route.get("secondary_ownable")
    bucket = (route.get("dominant") or (None,))[0]
    card_winners = _card_winners(route)
    evidence = _winners_evidence(q, card_winners)
    benchmark = ", ".join(w["url"] for w in _winner_summary(card_winners, limit=2))

    # The genre of the page we're telling QC to build, for the checklist's
    # GEO-feature stratification - derived from format_gap's finer format via
    # FORMAT_TO_GENRE so this stays the exact old informational/commercial
    # value regardless of the format refinement (checklist behavior is
    # unaffected by adding format-specific prose below); inferred from the
    # winning bucket otherwise (the "editorial pages win" / "rival pages win"
    # prose already assumes exactly this mapping). earn_indirect has no QC
    # page and no dominant ownable bucket to infer from - but if competitor/
    # editorial winners have a real (if non-dominant) presence anyway
    # (_secondary_ownable_signal), THEIR format is the best available answer
    # to "what should this be," rather than declining to say.
    # target_format mirrors target_genre's derivation one level finer - each
    # branch already has (or can cheaply vote for) the format, so this never
    # re-derives genre from format or vice versa: FORMAT_TO_GENRE stays the
    # single source of truth relating the two.
    if route["reason"] == "earn_indirect":
        target_genre = secondary["genre"] if secondary else None
        target_format = secondary["format"] if secondary else None
    elif gm:
        target_genre = FORMAT_TO_GENRE[gm["winner_format"]]
        target_format = gm["winner_format"]
    else:
        target_genre = "commercial" if bucket == "competitor" else "informational"
        target_format = _plurality_format(
            [f for f in (route.get("winners") or []) if source_type(f) in OWNABLE_SOURCE_BUCKETS])

    # What the new page needs to actually include - the same checklist
    # machinery that makes Tab 2 fix-cards concrete, run against the winners
    # instead of against a QC page that doesn't exist yet (or exists as the
    # wrong kind). [] when too few comparable winners are readable.
    checklist = build_winner_checklist(route.get("winners") or [], q["question"], target_genre=target_genre)

    # Deterministic, format-templated section plan - None when target_format
    # is unrecognized or too few comparable winners exist (build_page_plan
    # applies the same min_winners/comparable-type gate build_winner_checklist
    # does, via the shared _comparable_target_winners helper), in which case
    # the card falls back to the checklist-only content_brief below.
    page_plan = build_page_plan(route.get("winners") or [], q["question"], target_format, target_genre=target_genre)
    if page_plan:
        page_plan["format_label"] = _FORMAT_LABEL[target_format]

    # action_core is the one-sentence strategy, captured before benchmark/
    # checklist get appended below - it feeds content_brief.action (the
    # card's short headline) while `action` keeps growing into the full
    # backward-compatible string (still used wherever content_brief isn't
    # rendered, e.g. list rows, exports, the raw-evidence toggle). Splitting
    # the two is what lets the UI show "strategy sentence + benchmark chips +
    # numbered checklist" instead of one run-on paragraph with everything
    # comma-joined into it - see ContentBrief.jsx.
    if route["reason"] == "earn_indirect":
        domain = (route.get("feasibility_target") or {}).get("domain") or "the citing sources"
        problem = (f"'{q['question']}' is answered from reference sources QC cannot own or pitch "
                   f"({domain}); QC is cited in {round(q['qc_share'] * 100)}% of responses.")
        if secondary:
            target_label = _FORMAT_LABEL[secondary["format"]]
            problem += (f" {secondary['n_dominant']}/{secondary['n_classified']} format-classifiable "
                        f"competitor/editorial pages also cited here are {target_label}.")
            action_core = (f"No direct channel to {domain} - publish {target_label} answering "
                      f"'{q['question']}' to earn the slot indirectly, matching the format the "
                      f"other cited pages use.")
        else:
            action_core = (f"No direct channel to {domain} - publish the authoritative, citable QC content "
                      f"such sources reference, to earn the slot indirectly.")
        action = action_core
        if benchmark:
            action += f" Benchmark: {benchmark}."
    elif gm:
        target_label = _FORMAT_LABEL[gm["winner_format"]]
        qc_label = _FORMAT_LABEL[gm["qc_format"]]
        if gm["winner_format"] == "landing":
            action_core = (f"Build a dedicated course/program page for '{q['question']}' - the existing "
                      f"page ({route['qc_url']}) is {qc_label}, a different format than the "
                      f"commercial pages engines cite here. Link the two.")
        else:
            action_core = (f"Build {target_label} answering '{q['question']}', separate from the existing "
                      f"page ({route['qc_url']}) - and link the two. Keep tuning that page separately.")
        action = action_core
        problem = (f"QC's page for '{q['question']}' ({route['qc_url']}) is {qc_label}, "
                   f"but {gm['winners_with_format']}/{gm['winners_classified']} format-classifiable "
                   f"cited pages are {target_label} - engines reward a format QC doesn't have here.")
        evidence += (f" QC's covered page is {gm['qc_format']}; {gm['winners_with_format']} of "
                     f"{gm['winners_classified']} classifiable cited pages are {gm['winner_format']}.")
    else:
        problem = f"QC has no page answering '{q['question']}', and engines cite {bucket} pages instead."
        if bucket == "competitor":
            # Only assert "rivals won" over winners verified as rival provider
            # pages - and name them. Editorial that shares the field must not
            # be called a rival (the indeed.com / vet.purdue.edu bug).
            rival_names = ", ".join(dict.fromkeys(
                _root_domain(f.get("domain") or "")
                for f in card_winners if source_type(f) == "competitor"))
            won = (f"rival providers ({rival_names}) won this query with their own pages"
                   if rival_names else "provider pages win this query")
            action_core = f"Create a QC page answering '{q['question']}' - {won}."
            action = action_core
            if benchmark:
                action += f" Benchmark depth and coverage against: {benchmark}."
        else:
            action_core = (f"Build educational content (a guide/hub, not a sales page) answering "
                      f"'{q['question']}' - editorial pages win this query, so a self-serving page "
                      f"won't take the neutral slot.")
            action = action_core
            if benchmark:
                action += f" Model it on: {benchmark}."

    if checklist:
        must_include = ", ".join(
            f"{r['label'].lower()} ({r['winners_pct']}% of cited pages have it)" for r in checklist[:5])
        action += f" Must include: {must_include}."
        evidence += (" Structural checklist: " + "; ".join(
            f"{r['label']} — {r['winners_present']}/{r['winners_total']} ({r['winners_pct']}%) "
            f"cited pages have it" for r in checklist) + ".")

    # Same {heading, action, outline} shape ContentBrief.jsx already renders
    # for competitive_content.py/concern_engine.py recs - a numbered checklist
    # instead of a comma-joined "Must include: ..." clause, and the benchmark
    # renders separately via BenchmarkModule (which reads router.winners
    # directly), so neither needs restating in prose here.
    content_brief = {
        "heading": q["question"],
        "action": action_core,
        "outline": [{"title": r["label"], "detail": f"{r['winners_pct']}% of cited pages have it"}
                    for r in checklist],
    }

    priority = "high" if len(group) >= 2 else "medium"
    school = q.get("school") or (school_for_url(route.get("qc_url")) if route.get("qc_url") else None)
    router_detail = _router_detail(route, group)
    router_detail["content_brief"] = content_brief
    if page_plan:
        router_detail["page_plan"] = page_plan
    return {
        "problem": problem,
        "action": action,
        "priority": priority,
        "school": school,
        "evidence": evidence,
        "action_type": "content",
        "target": q["question"],
        "segment": _segment_for(q),
        "metric_impact": "citation_rate",
        "expected_direction": 1,
        "expected_magnitude": None,
        "effort": "L",
        "confidence": 0.6 if checklist else 0.55,
        "detail": {"router": router_detail,
                   **({"build_checklist": {"target_genre": target_genre, "target_format": target_format,
                                            "gaps": checklist}} if checklist else {})},
    }


def _reach_out_rec(route, group):
    """One REACH-OUT rec per dedup group; the feasibility verdict shapes the
    card (open -> concrete action, gated -> application/partnership framing)."""
    q = route["question"]
    bucket = (route.get("dominant") or (None,))[0]
    feas = route["feasibility"]
    target = route.get("feasibility_target") or {}
    domain = target.get("domain") or "the cited platform"
    gated = feas["feasibility"] == "gated"

    problem = (f"AI engines answer '{q['question']}' from {bucket} sources QC can't own - "
               f"{domain} leads - and QC is cited in {round(q['qc_share'] * 100)}% of responses.")
    action = feas["mechanism"]
    if gated:
        action += " (Requires application/approval - budget lead time.)"
    evidence = _winners_evidence(q, _card_winners(route)) + f" Channel: {feas['evidence']}."

    return {
        "problem": problem,
        "action": action,
        "priority": "medium",
        "school": q.get("school"),
        "evidence": evidence,
        "action_type": "community" if bucket == "ugc" else "outreach",
        "target": target.get("url") or domain,
        "segment": _segment_for(q),
        "metric_impact": "visibility_score" if bucket == "ugc" else "citation_rate",
        "expected_direction": 1,
        "expected_magnitude": None,
        "effort": "M" if gated else "S",
        "confidence": 0.5 if gated else 0.6,
        "detail": {"router": _router_detail(route, group)},
    }


def _secondary_build_rec(route):
    """
    Companion BUILD rec for a reach_out-branch question that ALSO carries a
    real (non-dominant) ownable presence - see _secondary_ownable_signal.
    The reach_out branch's own PRIMARY rec is still the sweep's job
    (reach_out_sweep.py, deliberately cheap/no-LLM); this only fires from the
    on-demand per-question flow, as a companion alongside it, when the
    secondary signal clears its own (lower than SOURCE_TYPE_DOMINANCE) floor -
    "also worth building," not "this is what wins the query." Caller must
    check route.get("secondary_ownable") is truthy before calling.
    """
    q = route["question"]
    secondary = route["secondary_ownable"]
    dominant_bucket = (route.get("dominant") or (None,))[0]
    target_genre = secondary["genre"]
    target_format = secondary["format"]
    target_label = _FORMAT_LABEL[target_format]
    card_winners = _card_winners(route)
    benchmark = ", ".join(w["url"] for w in _winner_summary(card_winners, limit=2))

    checklist = build_winner_checklist(route.get("winners") or [], q["question"], target_genre=target_genre)
    page_plan = build_page_plan(route.get("winners") or [], q["question"], target_format, target_genre=target_genre)
    if page_plan:
        page_plan["format_label"] = target_label

    problem = (f"'{q['question']}' is mostly answered from {dominant_bucket} sources QC can't own, "
               f"but {secondary['n_dominant']}/{secondary['n_classified']} format-classifiable "
               f"competitor/editorial pages also cited here are {target_label} - a slot QC could "
               f"compete for directly.")
    action_core = f"Build {target_label} answering '{q['question']}', matching the format those pages use."
    action = action_core
    if benchmark:
        action += f" Benchmark: {benchmark}."
    if checklist:
        must_include = ", ".join(
            f"{r['label'].lower()} ({r['winners_pct']}% of cited pages have it)" for r in checklist[:5])
        action += f" Must include: {must_include}."

    evidence = (_winners_evidence(q, card_winners) +
                f" {secondary['n_dominant']}/{secondary['n_classified']} classifiable competitor/"
                f"editorial cited pages are {secondary['format']}.")

    router_detail = {**_router_detail(route), "branch": "secondary_build"}
    router_detail["content_brief"] = {
        "heading": q["question"],
        "action": action_core,
        "outline": [{"title": r["label"], "detail": f"{r['winners_pct']}% of cited pages have it"}
                    for r in checklist],
    }
    if page_plan:
        router_detail["page_plan"] = page_plan

    return {
        "problem": problem,
        "action": action,
        "priority": "medium",
        "school": q.get("school"),
        "evidence": evidence,
        "action_type": "content",
        "target": q["question"],
        "segment": _segment_for(q),
        "metric_impact": "citation_rate",
        "expected_direction": 1,
        "expected_magnitude": None,
        "effort": "L",
        "confidence": 0.5,
        "detail": {"router": router_detail,
                   **({"build_checklist": {"target_genre": target_genre, "target_format": target_format,
                                            "gaps": checklist}} if checklist else {})},
    }


def _inclusion_recs(routes):
    """
    Per-winner inclusion opportunities (§5.5): roundups/directories that
    provably list rivals and never QC, surfaced across ALL routed winners and
    feasibility-gated. A page that verifiably lists providers is pitchable by
    construction, so the editorial default here is gated (not unknown) -
    closed targets (e.g. a .gov directory) are skipped, the build branch
    already owns aligning to those.
    """
    seen, out = set(), []
    for route in routes:
        for f in route.get("winners") or []:
            url = f.get("url")
            if url in seen or not inclusion_opportunity(f):
                continue
            seen.add(url)
            feas = outreach_feasibility(f)
            if feas["feasibility"] == "closed":
                continue
            if feas["feasibility"] == "unknown":
                feas = {"channel": "pitch", "feasibility": "gated",
                        "mechanism": "Pitch QC for inclusion - the page provably lists rival providers.",
                        "evidence": "page verified to list competitors and not QC"}
            q = route["question"]
            rivals = ", ".join(sorted(f.get("brand_mentions", {}).keys())[:5])
            is_directory = f.get("page_type") == "directory"
            out.append({
                "problem": (f"{url} is cited {f.get('citation_count')}x for '{q['question']}' and "
                            f"lists {rivals} - but never mentions QC."),
                "action": (f"Submit a QC listing to this directory ({url})." if is_directory else
                           f"Pitch QC for inclusion in this comparison article ({url}) - it already "
                           f"lists {rivals}.") + (" (Requires approval.)" if feas["feasibility"] == "gated" else ""),
                "priority": "high" if (f.get("citation_count") or 0) >= 3 else "medium",
                "school": q.get("school"),
                "evidence": (f"{url} cited {f.get('citation_count')}x; page content verified to "
                             f"list {rivals} and never mention QC. Channel: {feas['evidence']}."),
                "action_type": "citation" if is_directory else "outreach",
                "target": url,
                "segment": _segment_for(q),
                "metric_impact": "citation_rate",
                "expected_direction": 1,
                "expected_magnitude": None,
                "effort": "S",
                "confidence": 0.8,   # the inclusion gate is verified page content
                "detail": {"router": {**_router_detail(route), "branch": "inclusion_opportunity"},
                           "outreach_feasibility": feas,
                           "opportunity": {"url": url, "lists_competitors": rivals.split(", "),
                                           "citation_count": f.get("citation_count") or 0}},
            })
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Dispatch + dedup (§5.6)
# ─────────────────────────────────────────────────────────────────────────────

def _triage_entry(route):
    """Flatten a triage route for surfacing (kept small - no full page facts)."""
    q = route["question"]
    bucket, share = route.get("dominant") or (None, None)
    return {
        "question_id":     q["question_id"],
        "question":        q["question"],
        "topic":           q["topic"],
        "school":          q["school"],
        "qc_share":        q["qc_share"],
        "n_citations":     q["n_citations"],
        "reason":          route["reason"],
        "build_candidate": route.get("build_candidate", False),
        "dominant_source": bucket,
        "dominant_share":  share,
        "vote":            route.get("vote"),
        "qc_url":          route.get("qc_url"),
        "genre_mismatch":  route.get("genre_mismatch"),
        "winners":         _winner_summary(route.get("winners")),
    }


# ─────────────────────────────────────────────────────────────────────────────
# On-demand: one question -> one rec (dashboard question view)
# ─────────────────────────────────────────────────────────────────────────────

def get_question_stats(question_id, days=None):
    """
    One question's routing inputs, same shape as a get_losing_questions row.
    Deliberately NO losing filter: on-demand generation is an explicit human
    request, so selection doesn't gate it - the router's own vote still does.
    None when the question has no mention responses in the window
    (sentiment-only questions have nothing to route).
    """
    date_m = _date_filter(days).replace("AND created_at", "AND m.created_at")
    query = f"""
        SELECT q.id, q.question, q.topic, q.school,
               AVG(CASE WHEN m.qc_cited THEN 1 ELSE 0 END) as qc_share,
               COUNT(*) as n_responses,
               COALESCE(SUM(COALESCE(array_length(m.citations, 1), 0)), 0) as n_citations
        FROM mention_responses m
        JOIN questions q ON q.id = m.question_id
        WHERE q.id = %s {date_m}
        GROUP BY q.id, q.question, q.topic, q.school;
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, [question_id])
            r = cur.fetchone()
    if r is None:
        return None
    return {
        "question_id": r[0], "question": r[1], "topic": r[2], "school": r[3],
        "qc_share": round(float(r[4]), 3), "n_responses": r[5], "n_citations": int(r[6]),
    }


# One rec per COMMUNITY, not per thread: reddit URLs key on the subreddit.
# "[./]" admits both www.reddit.com and the bare https://reddit.com form.
_REDDIT_SUB = re.compile(r"(?:^|[./])reddit\.com/r/([^/?#]+)", re.I)


def _community_key(f):
    """Dedup key for one pitchable winner: r/<subreddit> for reddit URLs,
    the root domain otherwise. Empty string when there's nothing to key on."""
    if not f:
        return ""
    url = f.get("final_url") or f.get("url") or ""
    m = _REDDIT_SUB.search(url)
    if m:
        return f"r/{m.group(1).lower()}"
    return _root_domain(f.get("domain") or "")


def _fanout_rec(route, f, feas, key, key_citations):
    """One companion reach-out rec for a single pitchable winner. Reddit
    communities get participation framing (the cited thread is the entry
    point); other targets carry the channel's own mechanism."""
    q = route["question"]
    bucket = source_type(f)
    n = f.get("citation_count") or 0
    gated = feas["feasibility"] == "gated"
    is_reddit = key.startswith("r/")

    if is_reddit:
        thread_note = (f"the cited thread ({n}x) is the entry point"
                       if key_citations == n else
                       f"{key_citations} citations across its threads; the top one ({n}x) is the entry point")
        problem = (f"AI engines cite {key} when answering '{q['question']}' - "
                   f"QC has no presence in that community.")
        action = (f"Participate in {key} - answer '{q['question']}' as a named QC educator "
                  f"(disclosed affiliation); {thread_note}.")
    else:
        problem = (f"{f.get('domain') or key} is cited {n}x for '{q['question']}' - "
                   f"a {bucket} source QC can't own but can show up on.")
        action = feas["mechanism"]
    if gated:
        action += " (Requires application/approval - budget lead time.)"

    return {
        "problem": problem,
        "action": action,
        "priority": "medium" if (key_citations >= 3 and not gated) else "low",
        "school": q.get("school"),
        "evidence": (f"{f.get('url')} cited {n}x for '{q['question']}' "
                     f"({key}: {key_citations} citations total). Channel: {feas['evidence']}."),
        "action_type": "community" if bucket == "ugc" else "outreach",
        "target": f.get("url"),
        "segment": _segment_for(q),
        "metric_impact": "visibility_score" if bucket == "ugc" else "citation_rate",
        "expected_direction": 1,
        "expected_magnitude": None,
        "effort": "M" if gated else "S",
        "confidence": 0.5 if gated else 0.6,
        "detail": {"router": {**_router_detail(route), "branch": "reach_out_fanout"},
                   "outreach_feasibility": feas},
    }


def _reach_out_fanout(route, taken_keys, limit=3):
    """
    Companion reach-out recs beyond the primary target: one per distinct
    pitchable community/site among the winners, most-cited first. This is
    what keeps cited reddit communities visible even when the question's
    dominant bucket isn't ugc - a winner outside the dominant bucket
    qualifies with >= 2 citations; dominant-bucket winners on the reach_out
    branch qualify unconditionally. Feasibility-gated per target (closed /
    unknown channels are skipped, never forced).
    """
    dominant = (route.get("dominant") or (None,))[0]
    on_reach_branch = route.get("branch") == "reach_out"

    groups = {}   # key -> {"facts": most-cited entry point, "citations": key total}
    winners = sorted(route.get("winners") or [],
                     key=lambda f: -(f.get("citation_count") or 0))
    for f in winners:
        st = source_type(f)
        if st not in NON_OWNABLE_SOURCE_BUCKETS:
            continue
        if not (on_reach_branch and st == dominant) and (f.get("citation_count") or 0) < 2:
            continue
        key = _community_key(f)
        if not key or key in taken_keys:
            continue
        group = groups.setdefault(key, {"facts": f, "citations": 0})
        group["citations"] += f.get("citation_count") or 0

    out = []
    for key, group in sorted(groups.items(), key=lambda kv: -kv[1]["citations"]):
        if len(out) >= limit:
            break
        feas = outreach_feasibility(group["facts"])
        if feas["feasibility"] not in ("open", "gated"):
            continue
        out.append(_fanout_rec(route, group["facts"], feas, key, group["citations"]))
        taken_keys.add(key)
    return out


def _companion_recs(route, taken_keys=None):
    """
    Inclusion opportunities + reach-out fan-out for one routed question -
    the "companion" signals that fire regardless of the question's own
    branch (a build- or fix-branch question can still have winners that are
    verified inclusion opportunities or pitchable communities). `taken_keys`
    seeds already-claimed community keys (the reach_out branch's own primary
    rec seeds its target's key before calling this); pass None to start
    empty.
    """
    taken_keys = set() if taken_keys is None else taken_keys
    inclusion = _inclusion_recs([route])
    inclusion.sort(key=lambda r: -(r["detail"]["opportunity"]["citation_count"]))
    for rec in inclusion:
        host = urlsplit(rec.get("target") or "").hostname or ""
        if host:
            taken_keys.add(_root_domain(host))

    companions = inclusion + _reach_out_fanout(route, taken_keys)
    companions.sort(key=lambda r: -(r.get("confidence") or 0))
    return companions


def _tag_question_plan(recs, question_id, fallback_branch, has_primary=True, source="on_demand"):
    """Stamp detail.question_plan on each rec of one question's plan so the
    plan page can group/label them. `has_primary` controls whether recs[0]
    is tagged "primary" - False for a sweep's fix/build-branch companions,
    where there IS no real primary here (the manual flow owns that rec under
    its own tag), so nothing here should claim the primary role and collide
    with it. `source` distinguishes sweep-produced rows (see
    reach_out_sweep.py) from on-demand ones for cooldown-gating purposes."""
    qid = str(question_id)
    for i, rec in enumerate(recs):
        emitter = ((rec.get("detail") or {}).get("router") or {}).get("branch", fallback_branch)
        role = "primary" if (has_primary and i == 0) else "companion"
        rec.setdefault("detail", {})["question_plan"] = {
            "question_id": qid,
            "role": role,
            "emitter": emitter,
            "source": source,
        }
    return recs


def build_question_recommendations(question_id, days=None):
    """
    Route ONE question on demand and build its full action plan - multiple
    recommendations that coexist, each from an independent signal:
      primary    the routed branch's own rec (fix scorecard / build)
      inclusion  EVERY verified inclusion opportunity among the winners
      community  reach-out fan-out: one rec per distinct pitchable
                 community/site (reddit communities keyed r/<subreddit>)
    Returns (recs, triage_entry). recs is [] with a PRECISE triage reason when
    nothing was actionable (unchanged semantics from the single-rec era:
    qc page unreadable / insufficient winner data / true feature parity, plus
    winner-coverage counts), and ([], None) when the question has no mention
    responses to route. Each rec carries detail.question_plan so the plan
    page can group and label them.

    reach_out is deliberately NOT fabricated here anymore: reach-out primary
    + inclusion + community fan-out for EVERY losing question (regardless of
    its own branch) is the auto sweep's job now (reach_out_sweep.py, run on
    the same "refresh signal recommendations" action) - this manual,
    cooldown-gated per-question flow only ever produces build/fix. The one
    exception: a reach_out-branch question that ALSO clears
    _secondary_ownable_signal's floor (competitor/editorial winners present,
    just not dominant) gets a companion build rec here - the reach_out
    primary itself still doesn't come from this flow, but "also worth
    building" is exactly this flow's territory (LLM-backed prose, topic-
    gated), not the sweep's.
    """
    q = get_question_stats(question_id, days)
    if q is None:
        return [], None
    route = route_question(q, days)
    if route["branch"] == "triage":
        return [], _triage_entry(route)
    secondary = route.get("secondary_ownable")
    if route["branch"] == "reach_out" and not (secondary and q["topic"] in BUILDABLE_TOPICS):
        entry = _triage_entry(route)
        entry["reason"] = "reach_out_auto_covered"
        return [], entry

    primary, sc = None, None

    if route["branch"] == "fix":
        try:
            # A wider, independently-fetched pool than route["winners"] (which
            # is sized for the citation-share vote, not the scorecard): cited
            # pages fail to fetch or turn out non-comparable often enough that
            # asking for exactly TOP_N_WINNERS candidates routinely leaves
            # fewer than that after build_scorecard's readability/genre filter
            # - see scorecard.CANDIDATE_POOL. Deliberately NOT route["winners"]
            # itself - that set must stay exactly what the routing vote
            # measured, not grow just because the scorecard wants more
            # comparison headroom.
            scorecard_cited = get_question_cited_urls(q["question_id"], days, limit=CANDIDATE_POOL)
            counts = {c["url"]: c["count"] for c in scorecard_cited}
            scorecard_winners = get_pages_facts([c["url"] for c in scorecard_cited])
            for f in scorecard_winners:
                f["citation_count"] = counts.get(f["url"], 0)
            sc = build_scorecard(q["topic"] or q["question"], route["qc_url"],
                                 question=q["question"], days=days,
                                 winner_facts=scorecard_winners)
            primary = scorecard_to_recommendation(sc)
        except Exception as e:
            logger.warning(f"On-demand fix branch failed for {route['qc_url']}: {e}")
        if primary is not None:
            primary["detail"]["router"] = _router_detail(route)
    elif route["branch"] == "reach_out":
        # secondary ownable signal cleared its floor and the topic is
        # buildable - a companion build rec alongside the (sweep-owned)
        # reach_out primary, which this on-demand flow still doesn't produce.
        primary = _secondary_build_rec(route)
    else:
        primary = _build_rec(route, [route])

    companions = _companion_recs(route)

    # The plan's first rec is its lead ("primary") even when the branch rec
    # itself came back empty and a companion carries the plan alone.
    recs = ([primary] if primary else []) + companions
    recs = _tag_question_plan(recs, q["question_id"], route["branch"])
    if recs:
        return recs, None

    # Nothing actionable: keep the precise fix-branch triage reasons.
    entry = _triage_entry(route)
    if route["branch"] == "fix":
        entry["reason"] = scorecard_triage_reason(sc) if sc else "fix_no_feature_gaps"
        if sc:
            # Enough for the UI to say WHAT was insufficient, with names.
            entry["scorecard"] = {
                "qc_readable": sc.get("qc_readable"),
                "winners_readable": sc.get("winners_total"),
                "winners_cited_total": sc.get("winners_cited_total"),
                "winners_unreadable": sc.get("winners_unreadable") or [],
            }
    return [], entry
