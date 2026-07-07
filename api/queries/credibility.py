"""
Credibility layer (Phase 7, item 2 of
docs/ai/recommendation-deterministic-signals-todo.md).

`qc_verdict` is captured on every sentiment response and was surfaced nowhere.
It is free text, so the deterministic spine is the `qc_sentiment` enum on the
same row, with `qc_verdict` used only as verbatim, quotable evidence.

Credibility recs are a specialization of citation-contrast, keyed on sentiment
instead of mention_rate: sentiment_responses carry their OWN citations, so
"which domains do engines consult when they judge QC positively vs not" is a
same-row group-by, not an inference. The action then templates itself:
strengthen QC's presence on the domains that correlate with positive
judgments; if community sources dominate the negative side, reuse the Tab 1
ecosystem playbook (authentic presence, no manufactured posts).
"""

import re

from src.logger import logger
from api.db import get_connection, _date_filter
from api.queries.page_facts import QC_DOMAIN_TOKENS

_COMMUNITY_ROOTS = ("reddit.com", "quora.com", "facebook.com", "instagram.com", "youtube.com", "tiktok.com")

# Below this many sentiment rows, a distribution split is noise.
_MIN_SAMPLE = 20
# Fire only when at least half the judgments are not positive.
_WEAK_SHARE = 0.5


def _domain_of(url):
    return re.sub(r"^https?://(www\.)?", "", url).split("/")[0].lower()


def _is_qc(domain):
    return any(t in domain for t in QC_DOMAIN_TOKENS)


def analyze_credibility(days=None):
    """
    Sentiment distribution + the external domains cited on positive vs
    non-positive rows + example verdicts (verbatim). All same-row facts.
    """
    date_f = _date_filter(days).replace("AND created_at", "AND s.created_at")
    query = f"""
        SELECT s.qc_sentiment::text, s.qc_verdict, s.citations
        FROM sentiment_responses s
        WHERE 1=1 {date_f};
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query)
            rows = cur.fetchall()
    if not rows:
        return None

    dist = {"positive": 0, "neutral": 0, "negative": 0}
    pos_domains, neg_domains = {}, {}
    example_verdicts = {"positive": [], "not_positive": []}
    for sentiment, verdict, citations in rows:
        dist[sentiment] = dist.get(sentiment, 0) + 1
        bucket = pos_domains if sentiment == "positive" else neg_domains
        for url in citations or []:
            d = _domain_of(url)
            if not _is_qc(d):
                bucket[d] = bucket.get(d, 0) + 1
        key = "positive" if sentiment == "positive" else "not_positive"
        if verdict and len(example_verdicts[key]) < 2:
            example_verdicts[key].append(verdict.strip())

    n = len(rows)
    top = lambda d: sorted(d.items(), key=lambda kv: -kv[1])[:8]
    return {
        "sample_n": n,
        "distribution": dist,
        "share_not_positive": round((n - dist.get("positive", 0)) / n, 2),
        "positive_domains": [{"domain": d, "count": c} for d, c in top(pos_domains)],
        "not_positive_domains": [{"domain": d, "count": c} for d, c in top(neg_domains)],
        "example_verdicts": example_verdicts,
    }


def credibility_to_recommendation(analysis):
    """
    At most ONE templated credibility rec, only on a clear signal. Two
    deterministic variants:
      - community sources dominate the citations behind non-positive
        judgments -> ecosystem play (authentic community presence);
      - otherwise -> strengthen QC's presence on the specific authority
        domains engines consult when they judge QC positively.
    """
    if not analysis or analysis["sample_n"] < _MIN_SAMPLE:
        return None
    if analysis["share_not_positive"] < _WEAK_SHARE:
        return None

    dist = analysis["distribution"]
    verdict_quote = (analysis["example_verdicts"]["not_positive"] or [""])[0][:180]
    problem = (
        f"Across {analysis['sample_n']} sentiment responses, engines judge QC positively only "
        f"{dist.get('positive', 0)} times ({dist.get('neutral', 0)} neutral, "
        f"{dist.get('negative', 0)} negative). Example verdict: \"{verdict_quote}\"."
    )

    neg = analysis["not_positive_domains"]
    neg_total = sum(d["count"] for d in neg) or 1
    community = sum(d["count"] for d in neg if any(r in d["domain"] for r in _COMMUNITY_ROOTS))

    base = {
        "priority": "high",
        "school": None,
        "segment": {"dimension": "global", "value": "credibility"},
        "metric_impact": "positive_sentiment_rate",
        "expected_direction": 1,
        "expected_magnitude": None,
        "effort": "M",
        "confidence": 0.6,
        "problem": problem,
        "detail": {"credibility": analysis},
    }

    if community / neg_total >= 0.5:
        top_comm = ", ".join(f"{d['domain']} ({d['count']}x)" for d in neg
                             if any(r in d["domain"] for r in _COMMUNITY_ROOTS))[:200]
        return {**base,
            "action": ("Community sources dominate what engines consult when judging QC "
                       "unfavorably - establish an authentic, named QC presence there "
                       "(expert answers, transparent responses to criticism); never "
                       "manufactured or anonymous posts."),
            "evidence": (f"Domains cited on non-positive judgments: {top_comm}. "
                         f"{analysis['share_not_positive']:.0%} of judgments are not positive."),
            "action_type": "strategy",
            "target": "community credibility",
        }

    pos = analysis["positive_domains"]
    pos_names = ", ".join(f"{d['domain']} ({d['count']}x)" for d in pos[:5])
    return {**base,
        "action": (f"Strengthen QC's footprint on the sources engines consult when they judge QC "
                   f"positively - earn or refresh listings/reviews/mentions on: {pos_names}."),
        "evidence": (f"Domains cited on positive judgments: {pos_names or 'none'}. Domains cited on "
                     f"non-positive judgments: "
                     f"{', '.join(f'{d['domain']} ({d['count']}x)' for d in neg[:5]) or 'none'}. "
                     f"{analysis['share_not_positive']:.0%} of {analysis['sample_n']} judgments are not positive."),
        "action_type": "citation",
        "target": pos[0]["domain"] if pos else "third-party authority coverage",
    }


def build_credibility_recommendation(days=None):
    try:
        return credibility_to_recommendation(analyze_credibility(days))
    except Exception as e:
        logger.warning(f"Credibility layer failed: {e}")
        return None


if __name__ == "__main__":
    import io, sys, json
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    a = analyze_credibility()
    print(json.dumps({k: v for k, v in a.items()}, indent=1, default=str))
    rec = build_credibility_recommendation()
    print("\nrec:", json.dumps({k: v for k, v in (rec or {}).items() if k != "detail"}, indent=1, default=str))
