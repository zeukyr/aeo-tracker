"""
Sitemap coverage diagnosis for recommendations (Phase B follow-up).

Turns the "is this a missing page or a weak page?" ambiguity into a code
branch by matching against QC's own sitemap URLs. Two entry points:

  - diagnose_coverage(segment): evaluates coverage per underlying QUESTION
    (real user intent), because a segment LABEL like "How to Become" is a
    bucket spanning dog grooming, dog training and event planning - each a
    different QC page. Returns covered / uncovered intents.
  - diagnose_text_coverage(text): binary have_page/missing_page for one
    specific intent string - used to set a rec's action_type from its target.

Matching drops only function/role words (NOT subject nouns like "training"),
stems morphology (trainer/training -> train), and weights tokens by IDF so a
shared word like "dog" can't carry a match to the wrong page.

Competitor sitemaps are deliberately NOT fetched - the competitor pages that
matter are the cited URLs already stored in mention_responses.citations.

The sitemap snapshot is cached as a static artifact in api/knowledge/
(same pattern as geo_playbook.md) and refreshed manually ~monthly, aligned
with the generation cooldown:

    python -m api.queries.sitemap_coverage
"""

import os
import json
import re
import math
import difflib
from datetime import datetime, timezone
from xml.etree import ElementTree

import requests

from src.logger import logger
from api.db import get_connection

CACHE_PATH = os.path.join(os.path.dirname(__file__), "..", "knowledge", "qc_sitemaps.json")

QC_DOMAINS = [
    "qccareerschool.com",
    "qcpetstudies.com",
    "qceventplanning.com",
    "qcdesignschool.com",
    "qcmakeupacademy.com",
]

# Recs carry a school name; restrict matching to that sub-brand's domain
# when we know it, so an event-planning topic never "matches" a pet page.
SCHOOL_DOMAINS = {
    "QC Pet Studies":     ["qcpetstudies.com", "qccareerschool.com"],
    "QC Event Planning":  ["qceventplanning.com", "qccareerschool.com"],
    "QC Design School":   ["qcdesignschool.com", "qccareerschool.com"],
    "QC Makeup Academy":  ["qcmakeupacademy.com", "qccareerschool.com"],
}

_FETCH_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; qc-ai-tracker sitemap refresh)"}
_MAX_CHILD_SITEMAPS = 15

# Only function words, intent verbs, and role/qualifier words are dropped -
# NOT domain subject nouns. The old list stripped "training"/"grooming"/
# "certification", i.e. the exact words that distinguish a dog-training page
# from a dog-grooming one, so "how to become a dog trainer" collapsed to
# {dog} and matched the wrong page. Ubiquitous words like "course" or "dog"
# are handled by IDF weighting (below) instead of being stopworded.
_STOPWORDS = {
    # function words
    "a", "an", "and", "or", "the", "of", "to", "for", "in", "on", "with", "your",
    "my", "me", "how", "what", "why", "who", "which", "is", "are", "do", "does",
    "can", "should", "you", "it", "as", "at", "by", "from", "about",
    # intent verbs / phrasing that wrap the real subject
    "become", "becoming", "get", "getting", "start", "starting", "want", "need",
    "take", "takes", "long", "old", "make", "making", "guide", "steps", "step",
    # role / qualifier words - recur across subjects, not a subject themselves
    "professional", "certified", "certificate", "certification", "expert",
    "specialist", "best", "top", "good", "online", "qc",
}

# Suffix rules that collapse morphology so trainer/training/train,
# groomer/grooming and planner/planning share a root. Applied to both
# questions and slugs; the roots only need to agree with each other.
_SUFFIXES = ("ational", "ations", "ation", "ings", "ing", "ers", "er", "ies", "ied", "es", "al", "s")


def _stem(word):
    for suf in _SUFFIXES:
        if word.endswith(suf) and len(word) - len(suf) >= 3:
            return word[: -len(suf)]
    return word


# ─────────────────────────────────────────────────────────────────────────────
# B1: fetch + cache QC sitemaps
# ─────────────────────────────────────────────────────────────────────────────

# Sitemaps also list images/assets (e.g. cdn.qccareerschool.com/...teaser.jpg);
# only real pages count as coverage.
_ASSET_EXT = re.compile(r"\.(jpe?g|png|gif|webp|svg|ico|pdf|mp[34]|webm|css|js|zip)(\?|#|$)", re.I)


def _is_page_url(url):
    host = re.sub(r"^https?://", "", url).split("/")[0]
    return not _ASSET_EXT.search(url) and not host.startswith("cdn.")


def _extract_locs(xml_text):
    """All <loc> values, namespace-agnostic; works for urlsets and indexes."""
    try:
        root = ElementTree.fromstring(xml_text)
    except ElementTree.ParseError:
        return [], False
    is_index = root.tag.endswith("sitemapindex")
    locs = [el.text.strip() for el in root.iter() if el.tag.endswith("loc") and el.text]
    return locs, is_index


# Known-good sitemap URLs, hit directly to skip the redirect (bare domain ->
# www) and multi-path probing below. Add an entry here whenever a domain's
# exact location is confirmed instead of leaving it to guesswork.
_KNOWN_SITEMAP_URLS = {
    "qceventplanning.com": "https://www.qceventplanning.com/sitemap.xml",
    "qcpetstudies.com":    "https://www.qcpetstudies.com/sitemap.xml",
}

# Not every QC property serves /sitemap.xml (qcmakeupacademy is Yoast-style);
# domains without a _KNOWN_SITEMAP_URLS entry probe these in order.
_SITEMAP_PATHS = ("sitemap.xml", "sitemap_index.xml", "wp-sitemap.xml")


def _fetch_sitemap_urls(domain):
    """Page URLs from the domain's sitemap, following one level of index nesting."""
    urls = []
    known_url = _KNOWN_SITEMAP_URLS.get(domain)
    candidates = [known_url] if known_url else [f"https://{domain}/{path}" for path in _SITEMAP_PATHS]

    resp = None
    for url in candidates:
        try:
            resp = requests.get(url, headers=_FETCH_HEADERS, timeout=30)
            resp.raise_for_status()
            break
        except requests.RequestException as e:
            logger.warning(f"Sitemap fetch failed for {url}: {e}")
            resp = None
    if resp is None:
        logger.error(f"No sitemap found for {domain} at any known path")
        return urls

    locs, is_index = _extract_locs(resp.text)
    if not is_index:
        return locs

    for child in locs[:_MAX_CHILD_SITEMAPS]:
        try:
            child_resp = requests.get(child, headers=_FETCH_HEADERS, timeout=30)
            child_resp.raise_for_status()
            child_locs, child_is_index = _extract_locs(child_resp.text)
            if not child_is_index:
                urls.extend(child_locs)
        except requests.RequestException as e:
            logger.error(f"Child sitemap fetch failed ({child}): {e}")
    return urls


def refresh_sitemap_cache():
    """Fetch all QC domains' sitemaps and write the knowledge artifact."""
    snapshot = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "domains": {},
    }
    for domain in QC_DOMAINS:
        urls = _fetch_sitemap_urls(domain)
        snapshot["domains"][domain] = sorted({u for u in urls if _is_page_url(u)})
        logger.info(f"Sitemap refresh: {domain} -> {len(snapshot['domains'][domain])} URLs")

    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, indent=2)
    return snapshot


def load_sitemap_cache():
    """The cached snapshot, or None if it hasn't been fetched yet."""
    try:
        with open(CACHE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


# ─────────────────────────────────────────────────────────────────────────────
# B2: diagnose_coverage - fuzzy-match a segment topic against QC's pages
# ─────────────────────────────────────────────────────────────────────────────

def _tokens(text):
    words = re.split(r"[^a-z0-9]+", text.lower())
    return {
        _stem(w) for w in words
        if len(w) >= 3 and w not in _STOPWORDS and not w.isdigit()
    }


def _slug_tokens(url):
    path = re.sub(r"^https?://[^/]+", "", url)
    return _tokens(path)


_MATCH_THRESHOLD = 0.55


def _slug_df(slug_token_sets):
    """token -> number of slugs containing it (document frequency)."""
    df = {}
    for toks in slug_token_sets:
        for t in toks:
            df[t] = df.get(t, 0) + 1
    return df


def _idf(token, df, n_slugs):
    """Ubiquitous tokens (dog, course) -> ~0; rare or unseen -> high. +1 smoothing."""
    return math.log((n_slugs + 1) / (df.get(token, 0) + 1))


def _matches(t, slug_tokens):
    return t in slug_tokens or any(
        difflib.SequenceMatcher(None, t, u).ratio() >= 0.85 for u in slug_tokens
    )


def _best_page(q_tokens, pages, df, n_slugs):
    """
    (url, coverage, precision) for the page best covering the question.
    coverage = IDF-weighted fraction of question tokens matched, so landing a
    distinctive token ("train", "behavior") counts far more than a shared one
    ("dog") - which is what stops "professional dog trainer" matching the
    grooming page. precision (matched / slug tokens) breaks ties toward the
    cleanest slug (/dog-training over /dog-training/500-off).
    """
    total_w = sum(_idf(t, df, n_slugs) for t in q_tokens)
    if total_w <= 0:
        return None, 0.0, 0.0
    best = (None, 0.0, 0.0)
    for url, slug_tokens in pages:
        if not slug_tokens:
            continue
        matched = [t for t in q_tokens if _matches(t, slug_tokens)]
        if not matched:
            continue
        coverage = sum(_idf(t, df, n_slugs) for t in matched) / total_w
        precision = len(matched) / len(slug_tokens)
        if (coverage, precision) > (best[1], best[2]):
            best = (url, coverage, precision)
    return best


def _segment_questions(segment):
    """
    (school, question) rows for the actual user intents behind a segment.
    A bucket like "How to Become" only makes sense to match at the question
    level - the label itself is not a topic QC has a page about.
    """
    dimension = (segment or {}).get("dimension")
    value = (segment or {}).get("value")
    if not value:
        return []
    if dimension in (None, "topic"):
        where, params = "q.topic = %s", [value]
    elif dimension == "category":
        where, params = "q.question_type = %s", [value]
    elif dimension == "school":
        where, params = ("q.school IS NULL", []) if value == "General" else ("q.school = %s", [value])
    else:
        return []
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT q.school, q.question FROM questions q WHERE {where}", params)
            return cur.fetchall()


def _pages_for_school(cache, school):
    domains = SCHOOL_DOMAINS.get(school, QC_DOMAINS)
    pages = []
    for domain in domains:
        for url in cache["domains"].get(domain, []):
            if _is_page_url(url):
                pages.append((url, _slug_tokens(url)))
    return pages


def diagnose_coverage(segment, school=None):
    """
    Coverage verdict for a segment, evaluated per underlying QUESTION (real
    user intent) rather than the bucket LABEL. "How to Become" mixes dog
    grooming, dog training and event planning - each a different QC page - so
    matching the label is meaningless; we match each question's distinctive,
    stemmed tokens against QC's sitemap slugs (IDF-weighted).

    Returns:
      verdict:   have_all | partial | missing_all | unknown
      covered:   [{intent, qc_url, score}]  - distinct QC pages that exist (fix these -> Tab 2)
      uncovered: [{intent, score}]          - intents with no QC page (build these -> Tab 1)
      qc_url / match_score: the best covered page (back-compat for earlier callers)
    """
    cache = load_sitemap_cache()
    questions = _segment_questions(segment)
    if not questions:
        # No questions to read (e.g. a synthetic/global segment) - fall back to
        # matching the label itself, as the original implementation did.
        questions = [(school, (segment or {}).get("value") or "")]
    if cache is None:
        return {"verdict": "unknown", "covered": [], "uncovered": [], "qc_url": None, "match_score": None}

    pages_by_school, all_slug_sets = {}, []
    for sch, _q in questions:
        if sch not in pages_by_school:
            pages_by_school[sch] = _pages_for_school(cache, sch)
            all_slug_sets.extend(toks for _u, toks in pages_by_school[sch])
    df = _slug_df(all_slug_sets)
    n_slugs = max(len(all_slug_sets), 1)

    covered, uncovered, seen = [], [], set()
    for sch, question in questions:
        q_tokens = _tokens(question)
        if not q_tokens:
            continue
        url, coverage, _p = _best_page(q_tokens, pages_by_school.get(sch, []), df, n_slugs)
        if url and coverage >= _MATCH_THRESHOLD:
            if url not in seen:
                seen.add(url)
                covered.append({"intent": question, "qc_url": url, "score": round(coverage, 2)})
        else:
            uncovered.append({"intent": question, "score": round(coverage, 2)})

    if not covered and not uncovered:
        verdict = "unknown"
    elif not uncovered:
        verdict = "have_all"
    elif not covered:
        verdict = "missing_all"
    else:
        verdict = "partial"

    best = max(covered, key=lambda c: c["score"], default=None)
    return {
        "verdict": verdict,
        "covered": covered,
        "uncovered": uncovered,
        "qc_url": best["qc_url"] if best else None,
        "match_score": best["score"] if best else None,
    }


def diagnose_text_coverage(text, school=None):
    """
    Binary coverage for ONE specific intent string (a recommendation's target
    or query), used to set action_type deterministically: does QC already have
    a page for THIS exact thing? Unlike diagnose_coverage, this doesn't read a
    segment's questions - it matches the string you give it, so a rec targeting
    "dog behavior specialist" is judged on that, not on its "How to Become"
    bucket. Returns {verdict: have_page | missing_page | unknown, qc_url, score}.
    """
    cache = load_sitemap_cache()
    q_tokens = _tokens(text or "")
    if cache is None or not q_tokens:
        return {"verdict": "unknown", "qc_url": None, "score": None}
    pages = _pages_for_school(cache, school)
    df = _slug_df([toks for _u, toks in pages])
    url, coverage, _p = _best_page(q_tokens, pages, df, max(len(pages), 1))
    if url and coverage >= _MATCH_THRESHOLD:
        return {"verdict": "have_page", "qc_url": url, "score": round(coverage, 2)}
    return {"verdict": "missing_page", "qc_url": None, "score": round(coverage, 2)}


if __name__ == "__main__":
    result = refresh_sitemap_cache()
    for d, urls in result["domains"].items():
        print(f"{d}: {len(urls)} URLs")
    print(f"Saved to {os.path.abspath(CACHE_PATH)}")
