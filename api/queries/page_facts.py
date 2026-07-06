"""
Page-content layer (Phase 2 of docs/ai/recommendation-two-tab-plan.md).

Fetches the pages AI engines cite, extracts what's actually ON them, and
caches the result as per-URL "page facts". This is what lets recommendations
assert page contents truthfully (Tier B):

  - page_type classification -> which templated action fits (seek inclusion
    vs benchmark vs community strategy), so we never "pitch APDT" (an
    association that lists no schools).
  - brand_mentions -> the "seek inclusion" gate: only fires when the page
    provably names a competitor and not QC.
  - deterministic feature detections (schema, question headings, tables,
    pricing signals) -> half of the Tab 2 scorecard. Semantic features
    (direct-answer-first, certification section) are detected later by the
    scorecard's LLM pass over `content_excerpt`.

Cache: api/knowledge/page_facts.json, keyed per URL (one authority page
serves many topics). Community/video URLs are classified from the domain
alone and never fetched. Fetches respect robots.txt, a size cap, and a
content-type guard; failures are cached too, so a bad URL isn't re-hit
every run. Refresh by passing force=True (aligned with the ~monthly
generation cadence).
"""

import os
import re
import json
import urllib.robotparser
from datetime import datetime, timezone
from urllib.parse import urlparse

import requests
import trafilatura
from lxml import html as lxml_html

from src.logger import logger
from api.db import get_connection

CACHE_PATH = os.path.join(os.path.dirname(__file__), "..", "knowledge", "page_facts.json")

_FETCH_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; qc-ai-tracker page analysis)"}
_FETCH_TIMEOUT = 25
_MAX_BYTES = 2_500_000
_EXCERPT_CHARS = 4000

QC_DOMAIN_TOKENS = (
    "qccareerschool", "qcpetstudies", "qceventplanning",
    "qcdesignschool", "qcmakeupacademy",
)

# Classified from the domain alone - never fetched.
_COMMUNITY_DOMAINS = {
    "reddit.com", "quora.com", "facebook.com", "instagram.com", "tiktok.com",
    "twitter.com", "x.com", "pinterest.com", "medium.com", "linkedin.com",
}
_VIDEO_DOMAINS = {"youtube.com", "youtu.be", "vimeo.com"}

_ROUNDUP_HINT = re.compile(r"\b(best|top[\s-]?\d+|review|compar\w+|\bvs\b|ranked|rating)\b", re.I)
_DIRECTORY_HINT = re.compile(r"\b(director(y|ies)|listings?|find[\s-]a[\s-])\b", re.I)
_QUESTION_HEADING = re.compile(r"^(how|what|why|can|do|does|is|are|should|where|when|which)\b|\?\s*$", re.I)
_PRICING_SIGNAL = re.compile(r"\$\s?\d{2,}|\b(tuition|pricing|cost of|fees?)\b", re.I)


# ─────────────────────────────────────────────────────────────────────────────
# Cache
# ─────────────────────────────────────────────────────────────────────────────

def load_cache():
    try:
        with open(CACHE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {"version": 1, "pages": {}}


def _save_cache(cache):
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=1)


# ─────────────────────────────────────────────────────────────────────────────
# Competitor brand list (for brand-mention detection)
# ─────────────────────────────────────────────────────────────────────────────

_brands_cache = None

# The extraction pipeline stores some generic phrases as competitor "brands"
# ("Certification", "Online Courses"). A name made only of these words isn't
# a brand and would false-positive on almost any page in the niche.
_GENERIC_BRAND_WORDS = {
    "certification", "certifications", "certificate", "certificates",
    "course", "courses", "class", "classes", "program", "programs",
    "training", "online", "school", "schools", "academy", "college",
    "professional", "certified", "the", "of", "and", "for", "a", "an", "in",
}


def _is_generic_brand(name):
    tokens = re.split(r"[^a-z0-9]+", name.lower())
    return all(t in _GENERIC_BRAND_WORDS for t in tokens if t)


def load_competitor_brands(min_len=4):
    """
    Distinct competitor brand names seen in mention_response_brands. Very
    short names are dropped - substring noise ("PPG") isn't worth the false
    positives in page text - as are names made purely of generic words.
    """
    global _brands_cache
    if _brands_cache is not None:
        return _brands_cache
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT DISTINCT brand_name FROM mention_response_brands WHERE brand_type = 'competitor'"
            )
            names = [r[0] for r in cur.fetchall()]
    _brands_cache = sorted({
        n.strip() for n in names
        if n and len(n.strip()) >= min_len and not _is_generic_brand(n)
    })
    return _brands_cache


def _brand_token(name):
    """'Penn Foster' -> 'pennfoster' - for matching brands against domains."""
    return re.sub(r"[^a-z0-9]", "", name.lower())


def detect_brand_mentions(text, brands):
    """{brand: count} for brands appearing in text (word-boundary, case-insensitive)."""
    mentions = {}
    for brand in brands:
        pattern = re.compile(r"\b" + re.escape(brand) + r"\b", re.I)
        count = len(pattern.findall(text))
        if count:
            mentions[brand] = count
    return mentions


# ─────────────────────────────────────────────────────────────────────────────
# Fetch guards
# ─────────────────────────────────────────────────────────────────────────────

_robots_cache = {}


def _robots_allowed(url):
    """robots.txt check, cached per host. Unreachable robots -> assume allowed."""
    host = urlparse(url).netloc
    if host not in _robots_cache:
        rp = urllib.robotparser.RobotFileParser()
        try:
            resp = requests.get(f"https://{host}/robots.txt", headers=_FETCH_HEADERS, timeout=10)
            rp.parse(resp.text.splitlines() if resp.status_code == 200 else [])
        except requests.RequestException:
            rp.parse([])
        _robots_cache[host] = rp
    return _robots_cache[host].can_fetch(_FETCH_HEADERS["User-Agent"], url)


def _fetch_html(url):
    """(html, final_url, error_status): guarded fetch - robots, content-type, size cap."""
    if not _robots_allowed(url):
        return None, url, "blocked_robots"
    try:
        with requests.get(url, headers=_FETCH_HEADERS, timeout=_FETCH_TIMEOUT, stream=True) as resp:
            resp.raise_for_status()
            ctype = resp.headers.get("Content-Type", "")
            if "html" not in ctype:
                return None, resp.url, "not_html"
            chunks, size = [], 0
            for chunk in resp.iter_content(chunk_size=65536):
                size += len(chunk)
                if size > _MAX_BYTES:
                    return None, resp.url, "too_large"
                chunks.append(chunk)
            encoding = resp.encoding or "utf-8"
            return b"".join(chunks).decode(encoding, errors="replace"), resp.url, None
    except requests.RequestException as e:
        logger.warning(f"page_facts fetch failed for {url}: {e}")
        return None, url, "fetch_failed"


# ─────────────────────────────────────────────────────────────────────────────
# Extraction: main text, headings, JSON-LD schema, deterministic features
# ─────────────────────────────────────────────────────────────────────────────

def _collect_schema_types(node, found):
    if isinstance(node, dict):
        t = node.get("@type")
        if isinstance(t, str):
            found.add(t)
        elif isinstance(t, list):
            found.update(x for x in t if isinstance(x, str))
        for v in node.values():
            _collect_schema_types(v, found)
    elif isinstance(node, list):
        for item in node:
            _collect_schema_types(item, found)


def _extract_structure(raw_html, main_text=""):
    """
    Title, headings, JSON-LD schema types, and structural flags from raw HTML.
    Headings are filtered to those that survive in the extracted main text,
    so nav/footer chrome ("ABOUT US +") doesn't pollute the scorecard.
    """
    try:
        tree = lxml_html.fromstring(raw_html)
    except Exception:
        return {"title": None, "headings": [], "schema_types": [], "table_count": 0, "video_embed": False}

    title = tree.findtext(".//title")
    headings = [
        " ".join(h.text_content().split())
        for h in tree.xpath(".//h1 | .//h2 | .//h3")
    ]
    main_lower = main_text.lower()
    headings = [h for h in headings if h and (not main_lower or h.lower() in main_lower)][:40]

    schema_types = set()
    for script in tree.xpath('.//script[@type="application/ld+json"]'):
        try:
            _collect_schema_types(json.loads(script.text or ""), schema_types)
        except (json.JSONDecodeError, TypeError):
            continue

    video_embed = bool(tree.xpath(
        './/iframe[contains(@src, "youtube") or contains(@src, "vimeo")] | .//video'
    ))

    return {
        "title": " ".join(title.split()) if title else None,
        "headings": headings,
        "schema_types": sorted(schema_types),
        "table_count": len(tree.xpath(".//table")),
        "video_embed": video_embed,
    }


def _deterministic_features(structure, text):
    """The scorecard features detectable without an LLM (geo_features.json: detection=deterministic)."""
    return {
        "faq_schema":        "FAQPage" in structure["schema_types"],
        "course_schema":     "Course" in structure["schema_types"],
        "org_schema":        "Organization" in structure["schema_types"],
        "question_headings": sum(1 for h in structure["headings"] if _QUESTION_HEADING.search(h)),
        "comparison_table":  structure["table_count"] > 0,
        "video_embed":       structure["video_embed"],
        "pricing_signals":   bool(_PRICING_SIGNAL.search(text[:20000])),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Page classification (plan taxonomy)
# ─────────────────────────────────────────────────────────────────────────────

def _domain_of(url):
    return re.sub(r"^www\.", "", urlparse(url).netloc.lower())


def _root_domain(domain):
    return ".".join(domain.split(".")[-2:]) if "." in domain else domain


def _classify_by_domain(url, competitor_brands):
    """Classes decidable from the URL alone; None means content is needed."""
    domain = _domain_of(url)
    root = _root_domain(domain)
    if any(tok in domain for tok in QC_DOMAIN_TOKENS):
        return "qc_owned"
    if root in _VIDEO_DOMAINS:
        return "video"
    if root in _COMMUNITY_DOMAINS:
        return "community"
    if domain.endswith(".gov"):
        return "government"
    domain_squashed = re.sub(r"[^a-z0-9]", "", domain)
    for brand in competitor_brands:
        token = _brand_token(brand)
        if len(token) >= 6 and token in domain_squashed:
            return "competitor"
    return None


def _classify_editorial_llm(url, title, headings, excerpt):
    """
    LLM disambiguation for editorial pages: roundup vs directory vs
    association resource vs guide. Falls back to 'editorial' on any failure -
    callers treat that as "don't assert the page's genre".
    """
    from openai import OpenAI
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    prompt = f"""Classify this web page into exactly one category:
- "roundup": an article comparing/ranking multiple providers, courses, or schools ("best X", "top 10 X")
- "directory": a searchable/browsable listing of providers or programs
- "association": a professional association's or industry body's resource/guidance page
- "guide": an editorial how-to or career guide that does not rank providers
- "other": anything else

URL: {url}
TITLE: {title or "(none)"}
HEADINGS: {json.dumps(headings[:15])}
FIRST PARAGRAPHS: {excerpt[:1500]}

Return JSON: {{"page_type": "roundup|directory|association|guide|other"}}"""
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=50,
            messages=[
                {"role": "system", "content": "You classify web pages. Respond with valid JSON only."},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
        )
        page_type = json.loads(response.choices[0].message.content).get("page_type")
        if page_type in ("roundup", "directory", "association", "guide", "other"):
            return page_type, "llm"
    except Exception as e:
        logger.warning(f"page_facts LLM classification failed for {url}: {e}")
    return "editorial", "fallback"


def _classify_editorial(url, title, headings, excerpt):
    """Heuristic hints first; LLM only when the hints disagree or say nothing."""
    haystack = f"{url} {title or ''} {' '.join(headings[:10])}"
    roundup = bool(_ROUNDUP_HINT.search(haystack))
    directory = bool(_DIRECTORY_HINT.search(haystack))
    if roundup and not directory:
        return "roundup", "heuristic"
    if directory and not roundup:
        return "directory", "heuristic"
    return _classify_editorial_llm(url, title, headings, excerpt)


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def get_page_facts(url, force=False, _cache=None):
    """
    Facts for one cited URL, from cache unless force=True. Always returns a
    dict with at least {url, status, page_type}; status != "ok" means no
    content facts are available (and no content claim may be made).
    """
    cache = _cache if _cache is not None else load_cache()
    if not force and url in cache["pages"]:
        return cache["pages"][url]

    brands = load_competitor_brands()
    facts = {
        "url": url,
        "domain": _domain_of(url),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "status": "ok",
        "page_type": None,
        "page_type_source": "domain",
    }

    domain_type = _classify_by_domain(url, brands)
    if domain_type in ("community", "video"):
        facts["status"] = "not_fetched"
        facts["page_type"] = domain_type
        cache["pages"][url] = facts
        if _cache is None:
            _save_cache(cache)
        return facts

    raw_html, final_url, error = _fetch_html(url)
    if error:
        facts["status"] = error
        facts["page_type"] = domain_type or "editorial"
        cache["pages"][url] = facts
        if _cache is None:
            _save_cache(cache)
        return facts

    text = trafilatura.extract(raw_html, url=final_url, include_comments=False) or ""
    structure = _extract_structure(raw_html, main_text=text)

    facts.update({
        "final_url": final_url,
        "title": structure["title"],
        "headings": structure["headings"],
        "schema_types": structure["schema_types"],
        "word_count": len(text.split()),
        "content_excerpt": text[:_EXCERPT_CHARS],
        "brand_mentions": detect_brand_mentions(text, brands),
        "qc_mentioned": any(tok in text.lower().replace(" ", "") for tok in QC_DOMAIN_TOKENS)
                        or bool(re.search(r"\bQC (Career School|Pet Studies|Event Planning|Design School|Makeup Academy)\b", text, re.I)),
        "features": _deterministic_features(structure, text),
    })

    if domain_type:
        facts["page_type"] = domain_type
    else:
        facts["page_type"], facts["page_type_source"] = _classify_editorial(
            url, structure["title"], structure["headings"], facts["content_excerpt"]
        )

    cache["pages"][url] = facts
    if _cache is None:
        _save_cache(cache)
    return facts


def get_pages_facts(urls, force=False):
    """Batch variant: one cache load/save around N lookups."""
    cache = load_cache()
    results = [get_page_facts(u, force=force, _cache=cache) for u in urls]
    _save_cache(cache)
    return results


def inclusion_opportunity(facts):
    """
    The "seek inclusion" gate (plan: Tab 1 engine). True only when the page
    was actually read and provably lists at least one competitor while never
    mentioning QC - and is the kind of page that lists providers at all.
    """
    return (
        facts.get("status") == "ok"
        and facts.get("page_type") in ("roundup", "directory")
        and bool(facts.get("brand_mentions"))
        and not facts.get("qc_mentioned")
    )


if __name__ == "__main__":
    import sys
    urls = sys.argv[1:]
    if not urls:
        print("usage: python -m api.queries.page_facts <url> [<url> ...]")
        raise SystemExit(1)
    for f in get_pages_facts(urls, force=True):
        printable = {k: v for k, v in f.items() if k != "content_excerpt"}
        print(json.dumps(printable, indent=2)[:2500])
        print(f"inclusion_opportunity: {inclusion_opportunity(f)}\n")
