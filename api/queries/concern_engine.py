"""
Concern objection-response engine (Phase 7, items 0b + 1 of
docs/ai/recommendation-deterministic-signals-todo.md).

A recurring concern is an OBJECTION ("limited hands-on learning"). The
deterministic question is not "what should we say" - it is: does QC already
publish content answering this objection, and do engines cite that content
when the objection comes up? Four-step check:

  1. concern_type -> probe (taxonomy carries the objection-as-question +
     keywords). Slug/title matching can't do this job: a rebuttal usually
     lives in body text, and concern-language != marketing-language
     ("limited hands-on" vs "practicum with real dogs").
  2. candidate QC pages by BODY text (content_excerpt + headings) over the
     QC content index.
  3. semantic confirm: one LLM pass per candidate - does this page rebut the
     objection? Requires a QUOTE (Tier-B rule: no claim without a fetched
     fact backing it).
  4. citation half: concerns are raised on specific sentiment responses,
     which carry their own citations - is a confirmed rebuttal cited there?

Three computable states -> templated actions:
  - factual/structural concern (taxonomy: addressable=false) -> NO content
    rec pretending to fix it; at most the taxonomy's honest reframe.
  - no confirmed rebuttal -> "publish OR make prominent" content rec (hedged:
    the index can miss a buried, never-cited blog post - never assert
    "QC has no content on X").
  - confirmed rebuttal exists but engines don't cite it on concern
    questions -> surface/strengthen the existing page.

Severity is computed, not felt: concern count x how often the same response's
sentiment is not positive (same-row join on sentiment_responses).

QC content index (item 0b): there is NO blog sitemap, so the index is
sitemap pages UNION every QC URL engines have ever cited (mention +
sentiment responses) - which captures exactly the blog posts that matter.
Known blind spot: a rebuttal post that is neither in the sitemap nor ever
cited stays invisible; hence the hedged phrasing above.
"""

import os
import json
import re

from openai import OpenAI

from src.logger import logger
from src.parsing.urls import normalize_url
from api.db import get_connection, _date_filter
from api.queries.page_facts import get_pages_facts, QC_DOMAIN_TOKENS, school_for_url
from api.queries.signal_taxonomy import classify_concern, load_taxonomy

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Domains with tracked questions; makeup/design have none, skip their pages.
_INDEX_DOMAINS = ("qcpetstudies.com", "qceventplanning.com", "qccareerschool.com")

_MAX_REBUTTAL_CANDIDATES = 4   # semantic-confirm LLM calls per concern type


# ─────────────────────────────────────────────────────────────────────────────
# Item 0b: QC-owned content index
# ─────────────────────────────────────────────────────────────────────────────

def _cited_qc_urls():
    """Every QC URL engines have cited, from both response tables - the only
    way blog posts enter the index (no blog sitemap exists)."""
    qc_ilike = " OR ".join(f"u ILIKE '%%{t}%%'" for t in QC_DOMAIN_TOKENS)
    query = f"""
        SELECT DISTINCT u FROM (
            SELECT unnest(citations) AS u FROM mention_responses
            UNION ALL
            SELECT unnest(citations) AS u FROM sentiment_responses
        ) x WHERE {qc_ilike};
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query)
            return [r[0] for r in cur.fetchall()]


def qc_content_index():
    """
    Readable page_facts for QC's published corpus: sitemap pages (noise
    slugs excluded) UNION cited QC URLs. Fetches are guarded + cached in
    page_facts; after the first run this is a cache read.
    """
    from api.queries.sitemap_coverage import load_sitemap_cache, _is_page_url, _NOISE_SLUG

    urls = set()
    cache = load_sitemap_cache()
    if cache:
        for domain in _INDEX_DOMAINS:
            for url in cache["domains"].get(domain, []):
                if _is_page_url(url) and not _NOISE_SLUG.search(url):
                    urls.add(url)
    urls.update(u for u in _cited_qc_urls() if not _NOISE_SLUG.search(u))

    facts = get_pages_facts(sorted(urls))
    return [f for f in facts if f.get("status") == "ok"]


# ─────────────────────────────────────────────────────────────────────────────
# Severity: concern rows grouped by type, co-occurring sentiment
# ─────────────────────────────────────────────────────────────────────────────

def concern_severity(days=None):
    """
    {concern_type: {count, not_positive, share_not_positive, schools,
    examples, question_ids, cited_urls}} - everything downstream needs, from
    one query. `cited_urls` are the citations on the exact responses where
    the concern was raised (the step-4 join).
    """
    date_f = _date_filter(days).replace("AND created_at", "AND s.created_at")
    query = f"""
        SELECT s.qc_sentiment::text, s.question_id, s.citations, q.school,
               unnest(s.concerns_raised) AS concern
        FROM sentiment_responses s
        LEFT JOIN questions q ON q.id = s.question_id
        WHERE 1=1 {date_f};
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query)
            rows = cur.fetchall()

    out = {}
    for sentiment, question_id, citations, school, concern in rows:
        ctype = classify_concern(concern)
        if ctype == "other":
            continue
        entry = out.setdefault(ctype, {
            "count": 0, "not_positive": 0, "schools": {}, "examples": [],
            "question_ids": set(), "cited_urls": set(),
        })
        entry["count"] += 1
        if sentiment != "positive":
            entry["not_positive"] += 1
        if school:
            entry["schools"][school] = entry["schools"].get(school, 0) + 1
        if len(entry["examples"]) < 3 and concern not in entry["examples"]:
            entry["examples"].append(concern)
        entry["question_ids"].add(str(question_id))
        entry["cited_urls"].update(normalize_url(u) for u in citations or [])

    for entry in out.values():
        entry["share_not_positive"] = round(entry["not_positive"] / entry["count"], 2)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Steps 2-3: body search + semantic confirm
# ─────────────────────────────────────────────────────────────────────────────

def _rebuttal_candidates(probe, index, limit=_MAX_REBUTTAL_CANDIDATES):
    """QC pages whose BODY text hits the probe keywords, ranked by hits."""
    scored = []
    for facts in index:
        haystack = " ".join([
            facts.get("title") or "",
            " ".join(facts.get("headings") or []),
            facts.get("content_excerpt") or "",
        ]).lower()
        hits = sum(1 for kw in probe["keywords"] if kw.lower() in haystack)
        if hits:
            scored.append((hits, facts))
    scored.sort(key=lambda s: -s[0])
    return [f for _h, f in scored[:limit]]


def _confirm_rebuttal(probe, facts):
    """
    Semantic confirm with a mandatory quote - the page only counts as a
    rebuttal if the model can point at the sentence. Fails closed (None).
    """
    prompt = f"""OBJECTION raised about QC (an online school): {probe["question"]}

Page title: {facts.get("title")}
Page text (excerpt):
{(facts.get("content_excerpt") or "")[:3500]}

Does this page substantively address/rebut the objection? Answer true only if it does,
and quote the exact sentence(s) from the text that do it.

Return JSON: {{"rebuts": true|false, "quote": "verbatim sentence or empty"}}"""
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=200,
            messages=[
                {"role": "system", "content": "You inspect web-page content. Respond with valid JSON only."},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
        )
        r = json.loads(resp.choices[0].message.content)
        quote = (r.get("quote") or "").strip()
        if r.get("rebuts") and quote:
            return quote
    except Exception as e:
        logger.warning(f"Rebuttal confirm failed for {facts.get('url')}: {e}")
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Item 1: analyze + templated recommendation
# ─────────────────────────────────────────────────────────────────────────────

def analyze_concern(ctype, severity_entry, index):
    """
    State for one concern type:
      factual   - taxonomy says content can't fix it (reframe only)
      missing   - no QC page confirmed to rebut it
      invisible - confirmed rebuttal exists, but not cited where the concern arises
      covered   - confirmed rebuttal is already cited on concern responses
    """
    spec = next(t for t in load_taxonomy("concern") if t["id"] == ctype)
    analysis = {
        "concern_type": ctype,
        "label": spec["label"],
        "addressable": spec["addressable"],
        "action_type": spec.get("action_type"),
        "count": severity_entry["count"],
        "share_not_positive": severity_entry["share_not_positive"],
        "examples": severity_entry["examples"],
        "schools": severity_entry["schools"],
        "reframe": spec.get("reframe"),
        "rebuttals": [],
    }
    if not spec["addressable"]:
        analysis["state"] = "factual"
        return analysis

    probe = spec.get("probe")
    if probe:
        for facts in _rebuttal_candidates(probe, index):
            quote = _confirm_rebuttal(probe, facts)
            if quote:
                analysis["rebuttals"].append({
                    "url": facts.get("final_url") or facts["url"],
                    "title": facts.get("title"),
                    "quote": quote[:300],
                })

    if not analysis["rebuttals"]:
        analysis["state"] = "missing"
        return analysis

    concern_cited = {u.lower() for u in severity_entry["cited_urls"]}
    cited_rebuttals = [
        r for r in analysis["rebuttals"]
        if any(r["url"].lower().rstrip("/") in c or c.rstrip("/") in r["url"].lower()
               for c in concern_cited)
    ]
    analysis["state"] = "covered" if cited_rebuttals else "invisible"
    return analysis


def _top_school(schools):
    return max(schools, key=schools.get) if schools else None


def concern_to_recommendation(analysis):
    """
    Templated rec (mirror of scorecard_to_recommendation) - or None when the
    right answer is no rec (covered, or factual with no severity). Every claim
    traces to a verified fact: counts from the DB, quotes from fetched pages.
    """
    n = analysis["count"]
    label = analysis["label"].lower()
    examples = "; ".join(f'"{e}"' for e in analysis["examples"][:2])
    school = _top_school(analysis["schools"])
    priority = "high" if (n >= 10 and analysis["share_not_positive"] >= 0.5) else "medium"
    base = {
        "priority": priority,
        "school": school,
        "segment": {"dimension": "school", "value": school} if school else {"dimension": "global", "value": "all"},
        "metric_impact": "positive_sentiment_rate",
        "expected_direction": 1,
        "expected_magnitude": None,
        "effort": "M",
        "confidence": 0.6,
        "detail": {"concern": {k: v for k, v in analysis.items() if k != "schools"}},
    }

    if analysis["state"] == "factual":
        if not analysis.get("reframe") or n < 5:
            return None  # pure business insight; nothing GEO should claim to fix
        return {**base,
            "problem": (f"Engines raise '{label}' on {n} responses ({analysis['share_not_positive']:.0%} "
                        f"with non-positive sentiment), e.g. {examples}. This is a structural fact - "
                        f"content cannot resolve it."),
            "action": analysis["reframe"],
            "action_type": "strategy",
            "target": analysis["concern_type"],
            "confidence": 0.5,
        }

    if analysis["state"] == "missing":
        # The taxonomy knows what KIND of fix answers this objection: "content"
        # -> publish an answer on QC's site; "citation" -> the rebuttal is
        # third-party by nature (independent reviews), publishing won't help.
        if analysis.get("action_type") == "citation":
            action = (f"Earn independent third-party proof: solicit reviews on platforms engines "
                      f"trust (Trustpilot, Google Reviews, BBB reviews) and surface them - "
                      f"self-hosted testimonials are what triggered '{label}'.")
            action_type = "citation"
        else:
            action = (f"Publish - or make prominent, if it exists outside the sitemap and cited set - "
                      f"content that directly answers '{label}', structured so engines can quote it "
                      f"(direct answer first, specifics, not marketing copy).")
            action_type = "content"
        return {**base,
            "problem": (f"Engines raise '{label}' on {n} responses (e.g. {examples}) and no QC page "
                        f"in the indexed corpus was confirmed to answer it."),
            "action": action,
            "action_type": action_type,
            "target": analysis["concern_type"],
        }

    if analysis["state"] == "invisible":
        top = analysis["rebuttals"][0]
        return {**base,
            "problem": (f"Engines raise '{label}' on {n} responses (e.g. {examples}). QC already has a "
                        f"confirmed rebuttal at {top['url']} (\"{top['quote'][:140]}...\") - but engines "
                        f"do not cite it when the concern comes up."),
            "action": (f"Surface the existing rebuttal: strengthen and internally link {top['url']}, "
                       f"give the rebuttal its own crawlable section/heading, and earn third-party "
                       f"references to it so engines find it when this objection arises."),
            "action_type": "technical",
            "target": top["url"],
            "confidence": 0.7,
        }

    return None  # covered


def build_concern_recommendations(days=None, min_count=3, max_recs=3):
    """
    Deterministic concern recs for the most-raised concern types. Bounded:
    index is cached, <= _MAX_REBUTTAL_CANDIDATES LLM calls per addressable type.
    """
    severity = concern_severity(days)
    ranked = sorted(severity.items(), key=lambda kv: -kv[1]["count"])
    index = None
    out = []
    for ctype, entry in ranked:
        if len(out) >= max_recs:
            break
        if entry["count"] < min_count:
            continue
        if index is None:
            index = qc_content_index()
        try:
            analysis = analyze_concern(ctype, entry, index)
            rec = concern_to_recommendation(analysis)
        except Exception as e:
            logger.warning(f"Concern engine failed for {ctype}: {e}")
            rec = None
        if rec:
            out.append(rec)
    return out


if __name__ == "__main__":
    import io, sys
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    recs = build_concern_recommendations()
    print(f"{len(recs)} concern recs")
    for r in recs:
        d = r.pop("detail", {})
        print(json.dumps(r, indent=1, default=str))
        c = d.get("concern", {})
        print("  state:", c.get("state"), "| rebuttals:", [x["url"] for x in c.get("rebuttals", [])])
        print()
