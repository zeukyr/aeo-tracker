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

Cache: the `page_facts` table (migrations/004_page_facts_cache.sql), one row
per URL (one authority page serves many topics). Community/video URLs are
classified from the domain alone and never fetched. Fetches respect
robots.txt, a size cap, and a content-type guard; failures are cached too, so
a bad URL isn't re-hit every run (retried after _FAILURE_RETRY_DAYS). Refresh
by passing force=True (aligned with the ~monthly generation cadence).
"""

import os
import re
import json
import urllib.robotparser
from collections import Counter
from datetime import datetime, timezone
from urllib.parse import urlparse

import requests
import trafilatura
from lxml import etree
from lxml import html as lxml_html
from psycopg2.extras import Json

from src.logger import logger
from src.parsing.urls import normalize_url
from src.parsing.domains import QC_BRAND_LIST
from api.db import get_connection

_FETCH_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; qc-ai-tracker page analysis)"}
_FETCH_TIMEOUT = 25
_MAX_BYTES = 2_500_000
_EXCERPT_CHARS = 4000

QC_DOMAIN_TOKENS = (
    "qccareerschool", "qcpetstudies", "qceventplanning",
    "qcdesignschool", "qcmakeupacademy", "qcwellnessstudies",
)

# QC_BRAND_LIST (src/parsing/domains.py) is the reviewed name-alias list -
# it already knows "QC Event School" is QC Event Planning's alias, which a
# separate hardcoded pattern here previously didn't, so a real third-party
# mention using that name (e.g. a roundup blog) was missed as qc_mentioned.
_QC_MENTION_RE = re.compile(
    r"\b(" + "|".join(re.escape(name) for name in QC_BRAND_LIST) + r")\b", re.I)

# Classified from the domain alone - never fetched.
_COMMUNITY_DOMAINS = {
    "reddit.com", "quora.com", "facebook.com", "instagram.com", "tiktok.com",
    "twitter.com", "x.com", "pinterest.com", "medium.com", "linkedin.com",
}
_VIDEO_DOMAINS = {"youtube.com", "youtu.be", "vimeo.com"}

# Distinct product surfaces living under a community/review root, keyed by
# (root domain, first path segment) - the LinkedIn Learning problem: the
# domain-only rule filed linkedin.com/learning/* as "community" (ugc slot,
# "participate in the discussion"), but that subtree is LinkedIn Learning's
# course catalog - a platform slot QC counters by getting listed (review),
# not by joining a discussion. coursera.org/learn/<slug> is an individual
# course product page - the approved Udemy pattern (competitor, ownable
# slot) - unlike coursera's /courses catalog/search pages, which stay review.
# Survey of all cited community/review-domain URLs (2026-07-10): every other
# subpath on these roots is genuinely the root's own surface (facebook
# /groups, reddit /r, instagram profiles).
_SUBPATH_SOURCE_TYPES = {
    ("linkedin.com", "learning"): "review",
    ("coursera.org", "learn"):    "competitor",
    # Social Tables the SaaS product is not_actionable (job-board/e-commerce
    # registry ruling), but socialtables.com/blog/* is a genuine third-party
    # editorial surface (course roundups) - a different slot than their
    # product pages, same shape as the LinkedIn Learning carve-out above.
    # Verified 2026-07-24: this blog's wedding-planner-courses roundup
    # already lists QC by name.
    ("socialtables.com", "blog"): "review",
}


def _first_path_segment(url):
    try:
        segments = [s for s in urlparse(url or "").path.split("/") if s]
    except ValueError:
        return None
    return segments[0].lower() if segments else None


def _subpath_source_type(domain, url):
    return _SUBPATH_SOURCE_TYPES.get((_root_domain(domain), _first_path_segment(url)))

_ROUNDUP_HINT = re.compile(r"\b(best|top[\s-]?\d+|review|compar\w+|\bvs\b|ranked|rating)\b", re.I)
_DIRECTORY_HINT = re.compile(r"\b(director(y|ies)|listings?|find[\s-]a[\s-])\b", re.I)
_QUESTION_HEADING = re.compile(r"^(how|what|why|can|do|does|is|are|should|where|when|which)\b|\?\s*$", re.I)
_PRICING_SIGNAL = re.compile(r"\$\s?\d{2,}|\b(tuition|pricing|cost of|fees?)\b", re.I)


# ─────────────────────────────────────────────────────────────────────────────
# Cache (page_facts table; migrations/004_page_facts_cache.sql)
#
# One row per URL. `facts` jsonb is the full dict we return verbatim; the
# promoted scalar columns are written from that same dict for SQL/dashboards.
# ─────────────────────────────────────────────────────────────────────────────

_UPSERT_SQL = """
    INSERT INTO page_facts
        (url, domain, status, page_type, page_type_source, fetched_at, facts, updated_at)
    VALUES (%s, %s, %s, %s, %s, %s, %s, now())
    ON CONFLICT (url) DO UPDATE SET
        domain           = EXCLUDED.domain,
        status           = EXCLUDED.status,
        page_type        = EXCLUDED.page_type,
        page_type_source = EXCLUDED.page_type_source,
        fetched_at       = EXCLUDED.fetched_at,
        facts            = EXCLUDED.facts,
        updated_at       = now()
"""


def get_cached_fact(url):
    """The facts dict cached for one URL, or None if it isn't cached yet."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT facts FROM page_facts WHERE url = %s", (url,))
            row = cur.fetchone()
    return row[0] if row else None


def get_cached_facts(urls):
    """{url: facts} for the subset of `urls` already cached (one query).
    Keys are normalized URLs - the table stores one row per normalized URL."""
    urls = list(dict.fromkeys(normalize_url(u) for u in urls))
    if not urls:
        return {}
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT url, facts FROM page_facts WHERE url = ANY(%s)", (urls,))
            return {u: f for u, f in cur.fetchall()}


def _upsert_params(facts):
    return (facts["url"], facts.get("domain"), facts.get("status"),
            facts.get("page_type"), facts.get("page_type_source"),
            facts.get("fetched_at"), Json(facts))


def _upsert_fact(facts, conn=None):
    """Write one facts dict, keyed on url (insert or overwrite). Pass an open
    `conn` to reuse it across a batch; otherwise one is opened and closed."""
    own = conn is None
    conn = conn or get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(_UPSERT_SQL, _upsert_params(facts))
        conn.commit()
    finally:
        if own:
            conn.close()


def _store(facts, _cache):
    """Persist a freshly-computed fact and mirror it into the batch preload."""
    _upsert_fact(facts)
    if _cache is not None:
        _cache[facts["url"]] = facts
    return facts


# ─────────────────────────────────────────────────────────────────────────────
# Brand registry (api/knowledge/brand_registry.json - built by
# scripts/build_brand_registry.py)
#
# The reviewed brand->type mapping is the AUTHORITY on what a brand is:
# competitor | platform | certifying_body | not_actionable. The runtime used
# to re-derive "competitor" from the raw LLM-extracted brand list + domain
# rules, so a registry ruling (skillshare=platform, careervillage=job board)
# changed nothing at runtime - the registry was decorative. Now registry
# types feed both the competitor brand list and source_type.
# ─────────────────────────────────────────────────────────────────────────────

_BRAND_REGISTRY_PATH = os.path.join(
    os.path.dirname(__file__), "..", "knowledge", "brand_registry.json")

_registry_rows = None


def _load_brand_registry():
    """Registry rows with match tokens precomputed, highest-volume first
    (the build sorts by n desc; first match wins a contested domain).
    [] when the artifact is missing - consumers fall back to the old
    registry-less behavior."""
    global _registry_rows
    if _registry_rows is None:
        try:
            with open(_BRAND_REGISTRY_PATH, encoding="utf-8") as f:
                raw = json.load(f)["brands"]
        except (OSError, ValueError, KeyError):
            logger.warning("brand_registry.json missing/unreadable - "
                           "registry layer disabled, using raw brand list")
            raw = []
        _registry_rows = [{
            "name": r["name"],
            "type": r["type"],
            "names": [r["name"]] + (r.get("variants") or []),
            "tokens": {t for t in (_brand_token(n) for n in
                                   [r["name"]] + (r.get("variants") or []))
                       if len(t) >= 6},
            "domains": set(r.get("domains") or []),
        } for r in raw]
    return _registry_rows


def registry_brand_type(domain):
    """The registry's type for the brand that owns `domain` - literal registry
    domain (exact or parent) or label-boundary token match - or None when no
    row claims it."""
    if not domain:
        return None
    for row in _load_brand_registry():
        if any(domain == d or domain.endswith("." + d) for d in row["domains"]) \
                or any(_token_matches_domain(t, domain) for t in row["tokens"]):
            return row["type"]
    return None


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
    Brand names treated as competitors - for the domain match and on-page
    mention detection (the "seek inclusion" gate). Registry-typed: only rows
    the brand registry types 'competitor' contribute, so platforms,
    certifying bodies, universities and job boards in the noisy extracted
    list can no longer stamp pages competitor. Falls back to the raw
    mention_response_brands list when the registry artifact hasn't been
    built. Very short names are dropped - substring noise ("PPG") isn't
    worth the false positives in page text - as are names made purely of
    generic words.
    """
    global _brands_cache
    if _brands_cache is not None:
        return _brands_cache
    registry = _load_brand_registry()
    if registry:
        names = [n for row in registry if row["type"] == "competitor"
                 for n in row["names"]]
    else:
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
# Structural ratio metrics (geo_features.json: detection="ratio")
#
# Computed from a SECOND, structure-preserving trafilatura pass
# (include_formatting/include_tables/include_links, output_format="xml") over
# the same raw HTML, rather than from the raw lxml tree `_extract_structure`
# uses - the raw tree still contains nav/sidebar/footer chrome, which would
# inflate link density and emphasis density with boilerplate that isn't part
# of the actual article. trafilatura's XML schema (v2.1): <head rend="h1..">
# for headings, <list rend="ul|ol"><item> for lists, <table><row><cell>,
# <quote> for blockquotes, <hi rend="#b|#i"> for bold/italic, <ref target=...>
# for links (already resolved to absolute URLs when `url=` is passed).
# ─────────────────────────────────────────────────────────────────────────────

_HEADING_LEVEL = re.compile(r"^h[1-6]$")

_EMPTY_STRUCTURE_METRICS = {
    "internal_linking_density": None,
    "heading_hierarchy_depth": 0,
    "structured_content_ratio": None,
    "paragraph_length_conformance": None,
    "emphasis_density": None,
}


def _el_word_count(el):
    return len(" ".join(el.itertext()).split())


def _structure_metrics(raw_html, final_url):
    """Ratio-based GEO metrics (geo_features.json ids: internal_linking_density,
    heading_hierarchy_depth, structured_content_ratio, paragraph_length_conformance,
    emphasis_density). Returns _EMPTY_STRUCTURE_METRICS (all None/0) when the page
    has no extractable main content - callers must treat None as "not measurable",
    never as zero."""
    try:
        xml = trafilatura.extract(
            raw_html, url=final_url, include_formatting=True,
            include_tables=True, include_links=True, output_format="xml",
        )
    except Exception:
        return dict(_EMPTY_STRUCTURE_METRICS)
    if not xml:
        return dict(_EMPTY_STRUCTURE_METRICS)
    return _metrics_from_xml(xml, final_url)


def _metrics_from_xml(xml, final_url):
    """The arithmetic half of _structure_metrics, over an already-extracted
    trafilatura XML string - split out so it can be unit-tested against a
    hand-built XML fixture, independent of trafilatura's own content-quality/
    boilerplate heuristics (which are a third-party concern, not this repo's)."""
    try:
        main = etree.fromstring(xml.encode("utf-8")).find(".//main")
    except Exception:
        return dict(_EMPTY_STRUCTURE_METRICS)
    if main is None:
        return dict(_EMPTY_STRUCTURE_METRICS)

    total_words = _el_word_count(main)
    if total_words == 0:
        return dict(_EMPTY_STRUCTURE_METRICS)

    heading_levels = {h.get("rend") for h in main.iter("head")
                       if h.get("rend") and _HEADING_LEVEL.match(h.get("rend"))}

    structured_words = sum(_el_word_count(el) for tag in ("list", "table", "quote")
                            for el in main.iter(tag))
    emphasis_words = sum(_el_word_count(el) for el in main.iter("hi"))

    para_lengths = [n for n in (_el_word_count(p) for p in main.iter("p")) if n > 0]
    paragraph_conformance = (
        round(100 * sum(1 for n in para_lengths if 150 <= n <= 300) / len(para_lengths))
        if para_lengths else None
    )

    page_domain = _root_domain(_domain_of(final_url))
    internal, external = 0, 0
    for ref in main.iter("ref"):
        target = ref.get("target") or ""
        if not target or target.startswith(("mailto:", "tel:", "javascript:")):
            continue
        link_domain = _root_domain(_domain_of(target))
        if not link_domain:
            continue
        internal += 1 if link_domain == page_domain else 0
        external += 0 if link_domain == page_domain else 1
    total_links = internal + external

    return {
        "internal_linking_density": round(100 * internal / total_links) if total_links else None,
        "heading_hierarchy_depth": len(heading_levels),
        "structured_content_ratio": round(100 * structured_words / total_words),
        "paragraph_length_conformance": paragraph_conformance,
        "emphasis_density": round(100 * emphasis_words / total_words),
    }


_QUERY_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "can", "do", "does",
    "for", "from", "how", "if", "in", "into", "is", "it", "of", "on", "or",
    "that", "the", "this", "to", "was", "what", "when", "where", "which",
    "who", "why", "will", "with", "you", "your", "i", "my", "me", "we",
    "our", "should", "would", "could", "did", "have", "has", "had",
}


def query_term_coverage(question, text):
    """Share of the tracked question's significant (non-stopword) terms that
    appear verbatim (word-boundary, case-insensitive) in `text`
    (geo_features.json id: query_term_coverage). Question-specific, so - unlike
    the other ratio metrics - this is computed at scorecard time from cached
    content, not baked into the per-URL page_facts cache row (one page can
    serve many questions). None when there's no question/text or no
    significant terms to check."""
    if not question or not text:
        return None
    terms = {t for t in re.findall(r"[a-z0-9]+", question.lower())
             if t not in _QUERY_STOPWORDS and len(t) > 2}
    if not terms:
        return None
    text_lower = text.lower()
    present = sum(1 for t in terms if re.search(r"\b" + re.escape(t) + r"\b", text_lower))
    return round(100 * present / len(terms))


# ─────────────────────────────────────────────────────────────────────────────
# Page classification (plan taxonomy)
# ─────────────────────────────────────────────────────────────────────────────

def _domain_of(url):
    return re.sub(r"^www\.", "", urlparse(url).netloc.lower())


def _root_domain(domain):
    return ".".join(domain.split(".")[-2:]) if "." in domain else domain


def _domain_labels(domain):
    """Dot-separated hostname labels, each squashed to [a-z0-9]
    ('w-edx-university.selar.com' -> ['wedxuniversity', 'selar', 'com'])."""
    return [re.sub(r"[^a-z0-9]", "", part) for part in domain.lower().split(".") if part]


def _token_matches_domain(token, domain):
    """
    Does a brand token name this domain on LABEL boundaries? True when the
    token equals a label (pennfoster.edu, caninecollege.akc.org,
    posheventscourse.thinkific.com), is a prefix of one (pennfostergroup.com,
    jessronacourses.com), or equals a squashed trailing label chain - the
    domain-form brands whose token keeps the TLD ('nyiad.edu' -> nyiadedu,
    'calmcanines.academy' -> calmcaninesacademy, 'cvent.com' matching
    community.cvent.com). Never an arbitrary substring: a hypothetical
    "edX University" token must not claim wedxuniversity.selar.com, and
    'eventplanning.com' must not claim qceventplanning.com.
    """
    labels = _domain_labels(domain)
    if any(label == token or label.startswith(token) for label in labels):
        return True
    return any("".join(labels[i:]) == token for i in range(len(labels)))


def _classify_by_domain(url, competitor_brands):
    """
    Classes decidable from the URL alone; None means content is needed.

    "competitor" here is PROVISIONAL: the brand list is LLM-extracted from
    responses and noisy (it contains job boards, universities and insurers -
    "Purdue", "unity.edu", "US Career Institute", "Pet Care Ins"), so a
    brand-token domain match is only trusted outright for pages we could not
    read. For fetched pages the content classifier decides (its "provider"
    class maps back to competitor when the page really is a rival's own).

    All rules match on domain-label boundaries, never substrings - a squat
    host like wedxuniversity.selar.com must not inherit a brand's class from
    a token buried in its subdomain.
    """
    domain = _domain_of(url)
    root = _root_domain(domain)
    labels = _domain_labels(domain)
    if any(label in QC_DOMAIN_TOKENS for label in labels):
        return "qc_owned"
    if root in _VIDEO_DOMAINS:
        return "video"
    if root in _COMMUNITY_DOMAINS and not _subpath_source_type(domain, url):
        # carved-out subpaths (linkedin.com/learning) are product surfaces:
        # fall through so the page is fetched and content-classified
        return "community"
    if domain.endswith(".gov"):
        return "government"
    for brand in competitor_brands:
        token = _brand_token(brand)
        if len(token) >= 6 and _token_matches_domain(token, domain):
            return "competitor"
    return None


def _classify_editorial_llm(url, title, headings, excerpt):
    """
    LLM disambiguation for editorial pages: roundup vs directory vs
    association resource vs guide vs provider. "provider" (an organization
    selling its OWN courses/training - a rival school not in the brand list,
    e.g. icti.org) maps to page_type "competitor": that type's downstream
    semantics (comparable page, commercial slot, ownable) are exactly right
    for a rival provider's page. Falls back to 'editorial' on any failure -
    callers treat that as "don't assert the page's genre".
    """
    from openai import OpenAI
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    prompt = f"""Classify this web page into exactly one category:
- "roundup": an article comparing/ranking multiple providers, courses, or schools ("best X", "top 10 X")
- "directory": a searchable/browsable listing of providers or programs
- "association": a professional association's or industry body's resource/guidance page
- "guide": an editorial how-to or career guide that does not rank providers
- "provider": the website of a school/company selling ITS OWN courses, training programs, or services
- "other": anything else

URL: {url}
TITLE: {title or "(none)"}
HEADINGS: {json.dumps(headings[:15])}
FIRST PARAGRAPHS: {excerpt[:1500]}

Return JSON: {{"page_type": "roundup|directory|association|guide|provider|other"}}"""
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
        if page_type == "provider":
            return "competitor", "llm"
        if page_type in ("roundup", "directory", "association", "guide", "other"):
            return page_type, "llm"
    except Exception as e:
        logger.warning(f"page_facts LLM classification failed for {url}: {e}")
    return "editorial", "fallback"


def _classify_editorial(url, title, headings, excerpt, llm_ok=True):
    """Heuristic hints first; LLM only when the hints disagree or say nothing.
    llm_ok=False (bulk populate) stores the ambiguity instead of resolving it:
    ("editorial", "deferred") - a provisional row the next normal read
    upgrades via _upgrade_deferred."""
    haystack = f"{url} {title or ''} {' '.join(headings[:10])}"
    roundup = bool(_ROUNDUP_HINT.search(haystack))
    directory = bool(_DIRECTORY_HINT.search(haystack))
    if roundup and not directory:
        return "roundup", "heuristic"
    if directory and not roundup:
        return "directory", "heuristic"
    if not llm_ok:
        return "editorial", "deferred"
    return _classify_editorial_llm(url, title, headings, excerpt)


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

# Failed fetches (403/404/robots/timeout) are cached too, so a dead URL isn't
# re-hit every run - but they must not be permanently dead: hosts unblock,
# pages come back. A failure entry older than this window is treated as a
# cache miss and refetched. Success entries ("ok") and domain-only
# classifications ("not_fetched") never expire this way (monthly force
# refresh covers those).
_FAILURE_RETRY_DAYS = 14


def _is_stale_failure(facts):
    if facts.get("status") in ("ok", "not_fetched"):
        return False
    try:
        fetched = datetime.fromisoformat(facts.get("fetched_at", ""))
    except (TypeError, ValueError):
        return True  # a failure entry with no readable timestamp: retry
    if fetched.tzinfo is None:
        fetched = fetched.replace(tzinfo=timezone.utc)
    age = datetime.now(timezone.utc) - fetched
    return age.days >= _FAILURE_RETRY_DAYS


_STRUCTURAL_METRIC_KEYS = (
    "internal_linking_density", "heading_hierarchy_depth", "structured_content_ratio",
    "paragraph_length_conformance", "emphasis_density",
)


def _missing_structural_metrics(facts):
    """True for a status='ok' row cached before the geo_features.json 'ratio'
    metrics existed. Unlike a deferred LLM tiebreak, these can't be backfilled
    from the cached text alone - internal-link density, list/table ratios etc.
    need the raw HTML, which isn't cached - so such a row must be treated as a
    cache miss and refetched, not returned as-is with the new keys silently
    absent (which would read as "unmeasurable" downstream, not "not yet
    computed")."""
    if facts.get("status") != "ok":
        return False
    return not any(k in (facts.get("features") or {}) for k in _STRUCTURAL_METRIC_KEYS)


def _upgrade_deferred(facts, _cache=None):
    """
    Run the LLM tiebreak a defer_llm populate skipped, reusing the cached
    fetch (title/headings/content_excerpt) - no network refetch. Deferred rows
    are always status "ok" (failed fetches classify without the LLM), and
    carry one of two provisional types: "competitor" (brand-token domain
    match, content never confirmed) or "editorial" (hints silent). The domain
    verdict is recomputed to pick the same branch the eager path would take.
    On LLM failure the row STAYS deferred - unlike the eager path's terminal
    "fallback"/"domain" stamp - so the next winner pass retries instead of
    freezing the guess.
    """
    facts = dict(facts)
    domain_type = _classify_by_domain(facts["url"], load_competitor_brands())
    title = facts.get("title")
    headings = facts.get("headings") or []
    excerpt = facts.get("content_excerpt") or ""
    if domain_type == "competitor":
        page_type, source = _classify_editorial_llm(facts["url"], title, headings, excerpt)
    else:
        page_type, source = _classify_editorial(facts["url"], title, headings, excerpt)
    if source == "fallback":
        page_type = "competitor" if domain_type == "competitor" else "editorial"
        source = "deferred"
    facts["page_type"], facts["page_type_source"] = page_type, source
    return _store(facts, _cache)


def get_page_facts(url, force=False, defer_llm=False, _cache=None):
    """
    Facts for one cited URL, from cache unless force=True. Always returns a
    dict with at least {url, status, page_type}; status != "ok" means no
    content facts are available (and no content claim may be made). Cached
    failures are retried once they're older than _FAILURE_RETRY_DAYS.

    defer_llm=True (bulk pre-populate) never calls the LLM: pages the
    deterministic layers can't classify are stored provisionally
    (page_type_source "deferred", page_type "editorial" - or "competitor"
    when the domain matched a brand token). The first normal read of such a
    row upgrades it in place from the cached fetch, so the tiebreak is paid
    only for URLs something actually consumes (router winners), not per
    populated URL.

    _cache: an optional {url: facts} preload dict (from get_cached_facts) that
    lets a batch skip per-URL reads; freshly-computed facts are mirrored into
    it. Pass None for a standalone single-URL lookup.

    The URL is normalized first (tracking params stripped, https, no www, no
    trailing slash) - the normalized form is the cache key, the fetch target,
    and the "url" in the returned facts, so ?utm_source variants of one page
    share one cache row and one classification.
    """
    url = normalize_url(url)
    if not force:
        cached = _cache.get(url) if _cache is not None else get_cached_fact(url)
        if cached is not None and not _is_stale_failure(cached) and not _missing_structural_metrics(cached):
            if not defer_llm and cached.get("page_type_source") == "deferred":
                return _upgrade_deferred(cached, _cache)
            return cached

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
        return _store(facts, _cache)

    raw_html, final_url, error = _fetch_html(url)
    if error:
        facts["status"] = error
        facts["page_type"] = domain_type or "editorial"
        return _store(facts, _cache)

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
                        or bool(_QC_MENTION_RE.search(text)),
        "features": {**_deterministic_features(structure, text),
                     **_structure_metrics(raw_html, final_url)},
    })

    if domain_type == "competitor":
        # Brand-token domain match, but the page WAS read: content decides.
        # Straight to the LLM (no roundup/directory heuristics - a rival's
        # "Best Online X Course" sales page would false-positive as roundup);
        # its "provider" class maps to competitor, so a real rival's page
        # keeps the label while a job board's career guide loses it.
        if defer_llm:
            page_type, source = "competitor", "deferred"
        else:
            page_type, source = _classify_editorial_llm(
                url, structure["title"], structure["headings"], facts["content_excerpt"]
            )
            if source == "fallback":   # LLM unavailable - the domain match stands
                page_type, source = "competitor", "domain"
        facts["page_type"], facts["page_type_source"] = page_type, source
    elif domain_type:
        facts["page_type"] = domain_type
    else:
        facts["page_type"], facts["page_type_source"] = _classify_editorial(
            url, structure["title"], structure["headings"], facts["content_excerpt"],
            llm_ok=not defer_llm,
        )

    return _store(facts, _cache)


def get_pages_facts(urls, force=False, defer_llm=False):
    """Batch variant: one preload query, then per-URL lookups against it."""
    preload = {} if force else get_cached_facts(urls)
    return [get_page_facts(u, force=force, defer_llm=defer_llm, _cache=preload)
            for u in urls]


def inclusion_opportunity(facts):
    """
    The "seek inclusion" gate (plan: Tab 1 engine). True only when the page
    was actually read and provably lists at least one competitor while never
    mentioning QC - and is the kind of non-ownable page that lists providers
    at all. Competitor-owned pages stay on the fix/build side of the pipeline
    even if they look directory-like.
    """
    source = source_type(facts)
    return (
        facts.get("status") == "ok"
        and facts.get("page_type") in ("roundup", "directory")
        and source in ("ugc", "review", "reference", "certifying_body")
        and bool(facts.get("brand_mentions"))
        and not facts.get("qc_mentioned")
    )


# ─────────────────────────────────────────────────────────────────────────────
# Content genre (informational vs commercial) - the "wrong kind of page" axis
# ─────────────────────────────────────────────────────────────────────────────
#
# Genre is orthogonal to page_type: page_type says who owns/what format a page
# is (competitor, roundup, guide); genre says what INTENT it serves - does it
# educate (how-to guide, career guide) or sell (course/program page). This is
# what resolves the sitemap gray area: QC can HAVE a topically-matching page
# (the dog-grooming course page) while engines reward the OTHER genre for the
# query (a how-to guide). Slug matching can't see that; genre can.

# page_types whose genre is implied by the format itself. Ownership types
# (competitor, qc_owned) and unconfirmed ones (editorial) don't imply a genre -
# a competitor's page might be their sales page OR their how-to guide, and
# that difference is exactly the signal we're after.
PAGE_TYPE_GENRE = {
    "guide":       "informational",
    "association": "informational",
    "government":  "informational",
    "roundup":     "commercial",   # "best X courses" serves buying intent
    "directory":   "commercial",
}

# URL section hints work even for pages that couldn't be fetched (403s degrade
# to a URL-level genre read instead of no read at all). Informational is
# checked FIRST: a "/blog/best-certifications" slug is editorial content about
# certifications, not a certification sales page.
_INFORMATIONAL_URL_HINT = re.compile(
    r"/(blog|resources?|resource-center|articles?|advice|career-advice|guides?|learn|how[\s-]to)(/|$|-)", re.I)
_COMMERCIAL_URL_HINT = re.compile(
    r"/(courses?|certification[^/]*|programs?|enroll\w*|pricing|tuition|admissions?)(/|$)", re.I)
_HOWTO_TITLE = re.compile(
    r"\b(how to|guide|steps? to|tips|what (is|does)|career)\b", re.I)


def _url_genre(url):
    """URL-only genre hint - all we have for pages that blocked the fetch."""
    if _INFORMATIONAL_URL_HINT.search(url or ""):
        return "informational"
    if _COMMERCIAL_URL_HINT.search(url or ""):
        return "commercial"
    return None


def page_genre(facts):
    """
    "informational" (educates: how-to / career-guide architecture) vs
    "commercial" (sells: course/program page) for a FETCHED page, from
    deterministic signals only. None when the page wasn't read or the signals
    don't clearly separate - callers must not guess in that case.

    pricing_signals is deliberately the weakest commercial vote: career guides
    quote salary figures, which the pricing regex also matches - a lone
    pricing signal must not out-vote an informational URL section or title.
    """
    if facts.get("status") != "ok":
        return None
    f = facts.get("features") or {}
    url = facts.get("final_url") or facts.get("url") or ""
    title = facts.get("title") or ""

    commercial = 0
    informational = 0
    if f.get("course_schema"):
        commercial += 2
    if f.get("pricing_signals"):
        commercial += 1
    if _COMMERCIAL_URL_HINT.search(url):
        commercial += 1
    if _INFORMATIONAL_URL_HINT.search(url):
        informational += 2
    if _HOWTO_TITLE.search(title):
        informational += 2
    if "HowTo" in (facts.get("schema_types") or []):
        informational += 2
    if (f.get("question_headings") or 0) >= 3:
        informational += 1

    if commercial > informational:
        return "commercial"
    if informational > commercial:
        return "informational"
    return None


def winner_genre(facts):
    """Genre of one cited page: format-implied types first, content signals for
    ownership types, URL hints for pages that blocked the fetch. Unread
    competitor pages with no URL hint default to commercial (a rival's cited
    page is overwhelmingly their sales/course page)."""
    page_type = facts.get("page_type")
    url = facts.get("final_url") or facts.get("url")
    if page_type in PAGE_TYPE_GENRE:
        return PAGE_TYPE_GENRE[page_type]
    if page_type == "competitor":
        return page_genre(facts) or _url_genre(url) or "commercial"
    if page_type in ("community", "video"):
        return None  # their own ecosystem signal; they don't vote on genre
    return page_genre(facts) or _url_genre(url)


_GENRE_DOMINANCE = 0.6  # same "most" bar the composition rules use


def genre_gap(qc_facts, winner_facts, min_classified=3):
    """
    The "have a page, wrong page" detector. Returns a mismatch dict when QC's
    page has a clear genre, enough cited winners carry a clear genre, and the
    dominant winner genre differs from QC's - i.e. engines reward a KIND of
    page QC doesn't have for this topic, so the fix is to build the missing
    genre (Tab 1), not just tune the existing page (Tab 2). None otherwise -
    ambiguity never asserts a mismatch.
    """
    qc_genre = page_genre(qc_facts)
    if not qc_genre:
        return None
    genres = [g for g in (winner_genre(f) for f in winner_facts) if g]
    if len(genres) < min_classified:
        return None
    dominant = max(set(genres), key=genres.count)
    share = genres.count(dominant) / len(genres)
    if share < _GENRE_DOMINANCE or dominant == qc_genre:
        return None
    return {
        "qc_genre":            qc_genre,
        "winner_genre":        dominant,
        "winners_with_genre":  genres.count(dominant),
        "winners_classified":  len(genres),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Content FORMAT (how_to / long_form / listicle / landing) - a refinement of
# genre for the BUILD branch's prose. Two pages can share genre="informational"
# (a how-to guide and a long-form career explainer) while being different
# formats to actually build - genre can't see that, format can. Buckets nest
# inside the existing genre split (how_to/long_form -> informational;
# listicle/landing -> commercial) so FORMAT_TO_GENRE recovers the exact old
# genre value - target_genre (which gates GEO-feature applicability in
# scorecard.py) is unaffected by this refinement.
#
# "comparison" and "alternatives" were dropped from the original 6-bucket
# proposal: a calibration pass over the 27 live losing questions' cited
# winners never classified a single one into either bucket (this niche's
# competitive content just doesn't produce them at meaningful volume) - two
# structurally-empty buckets would only have made the plurality easier to
# win by default in the remaining four.
# ─────────────────────────────────────────────────────────────────────────────

FORMAT_TO_GENRE = {
    "how_to":    "informational",
    "long_form": "informational",
    "listicle":  "commercial",
    "landing":   "commercial",
}

_HOWTO_URL_HINT = re.compile(r"how[\s-]to", re.I)


def _is_howto_signal(facts):
    f = facts.get("features") or {}
    return (bool(_HOWTO_TITLE.search(facts.get("title") or ""))
            or "HowTo" in (facts.get("schema_types") or [])
            or (f.get("question_headings") or 0) >= 3)


def page_format(facts):
    """
    how_to | long_form | listicle | landing for a FETCHED page. Roundup/
    directory fold straight to listicle AHEAD of the genre vote (their genre
    was already pinned "commercial" by PAGE_TYPE_GENRE for an unrelated
    reason - buying intent, not format - so reusing page_genre here would
    wrongly merge them with landing pages). Everything else defers to
    page_genre and only splits its "informational" verdict into how_to vs
    long_form using the same how-to signals page_genre already voted with.
    None when unread or genre itself is ambiguous - never guess.
    """
    if facts.get("status") != "ok":
        return None
    page_type = facts.get("page_type")
    if page_type in ("roundup", "directory"):
        return "listicle"
    if page_type in ("association", "government"):
        return "long_form"
    genre = page_genre(facts)
    if genre is None:
        return None
    if genre == "commercial":
        return "landing"
    return "how_to" if _is_howto_signal(facts) else "long_form"


def winner_format(facts):
    """Format of one cited page - mirrors winner_genre's fallback ladder
    (format-implied page_types first, content signals via page_format for
    ownership types, URL hints for pages that blocked the fetch) so a 403'd
    page still votes instead of silently abstaining. An unread competitor
    page with no format-specific URL hint defaults to landing, same default
    winner_genre uses (a rival's cited page is overwhelmingly its sales
    page)."""
    page_type = facts.get("page_type")
    url = facts.get("final_url") or facts.get("url") or ""
    if page_type in ("roundup", "directory"):
        return "listicle"
    if page_type in ("association", "government"):
        return "long_form"
    if page_type in ("community", "video"):
        return None
    fmt = page_format(facts)
    if fmt:
        return fmt
    url_genre = _url_genre(url)
    if url_genre == "commercial":
        return "landing"
    if url_genre == "informational":
        return "how_to" if _HOWTO_URL_HINT.search(url) else "long_form"
    if page_type == "competitor":
        return "landing"
    return None


# Calibrated against the router's real losing-question winner sets (27
# questions, CANDIDATE_POOL=20 winners each): margin, not floor, turned out to
# be the binding constraint - across floor 2-4 the pass rate barely moved once
# margin was fixed at 2, so the floor mainly exists to keep a lone winner or a
# 2-0 split from counting as a plurality, not to set the real bar.
_FORMAT_FLOOR = 3
_FORMAT_MARGIN = 2


def format_gap(qc_facts, winner_facts):
    """
    The "have a page, wrong FORMAT" detector - format_gap's plurality-based
    replacement for genre_gap's fixed 60%-share bar. Splitting genre into 4
    format buckets dilutes any fixed-percentage dominance bar (more buckets
    to split votes across, so a real signal can end up under 60% just from
    fragmentation) - the guard here is a raw PLURALITY instead: the leading
    format must clear _FORMAT_FLOOR classified winners AND beat the
    runner-up by _FORMAT_MARGIN. Returns None (insufficient signal) rather
    than asserting a mismatch on a near-tied vote - ambiguity never asserts.
    """
    qc_format = page_format(qc_facts)
    if not qc_format:
        return None
    formats = [f for f in (winner_format(wf) for wf in winner_facts) if f]
    if len(formats) < _FORMAT_FLOOR:
        return None
    ranked = Counter(formats).most_common()
    dominant, top_count = ranked[0]
    second_count = ranked[1][1] if len(ranked) > 1 else 0
    if top_count < _FORMAT_FLOOR or (top_count - second_count) < _FORMAT_MARGIN or dominant == qc_format:
        return None
    return {
        "qc_format":            qc_format,
        "winner_format":        dominant,
        "winners_with_format":  top_count,
        "winners_classified":   len(formats),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Source-type rollup (question-router plan §5.2) - who OWNS the winning slot
# ─────────────────────────────────────────────────────────────────────────────
#
# A router-level layer over page_type - no new page_type values (so
# _COMPARABLE_TYPES and the genre maps are untouched).
# Domain rules run first because a review platform like coursera.org would
# otherwise read as "competitor" via brand-token match; then the existing
# page_type maps onto ownability buckets:
#   ownable      editorial / competitor - QC could hold this slot with a page
#   non-ownable  ugc / review / reference / certifying_body - the slot belongs
#                to a third party
#   other        doesn't vote (video, qc_owned, unclassified)

# udemy.com is deliberately NOT here: engines cite its individual course
# product pages as places to take the course instead of QC (a competitive
# loss, ownable slot), so it classifies competitor via the brand-token match.
# skillshare.com and alison.com likewise (approved 2026-07-10, pinned in the
# registry). Coursera stays: its cited slots are mostly catalog/search pages
# ("courses?query=..."), where "get listed" is the right counter - except
# /learn/<slug> product pages, carved out via _SUBPATH_SOURCE_TYPES.
_REVIEW_DOMAINS = {
    "g2.com", "capterra.com", "trustpilot.com", "coursera.org",
    "classcentral.com", "coursereport.com",
    "switchup.org", "careerkarma.com",
}
_REFERENCE_DOMAINS = {"wikipedia.org", "wikidata.org", "britannica.com"}

# Vendor-hosted forums (community.cvent.com/discussion/...) classify as
# "competitor" at page_type level - the brand token wins the domain match -
# but the SLOT is user-generated discussion, not the vendor's editorial page.
# The subdomain says so deterministically.
_UGC_SUBDOMAIN = re.compile(r"^(community|forums?|discuss(ions?)?|boards?)\.", re.I)

_PAGE_TYPE_TO_SOURCE = {
    "community":   "ugc",
    "competitor":  "competitor",
    "guide":       "editorial",
    "editorial":   "editorial",
    # An industry body's page (CCPDT, NDGAA) is not a slot QC can out-publish:
    # engines cite it for its AUTHORITY, not its content depth. Non-ownable;
    # routes to reach-out (listing / accreditation), default gated.
    "association": "certifying_body",
    "roundup":     "editorial",
    "directory":   "editorial",
    "government":  "reference",
    "video":       "other",
    "qc_owned":    "other",
}

SOURCE_TYPE_DOMINANCE = 0.6  # same "most" bar as genre_gap / composition rules

# The router's first branching decision is one bit - can QC own the winning
# slot or not. competitor and editorial route identically (ownable: build/fix),
# so they must not split the vote against each other; WHICH non-ownable bucket
# leads does change behavior (ugc -> participate, review -> claim,
# reference -> align, certifying_body -> pursue listing/accreditation),
# so that's asked second.
OWNABLE_SOURCE_BUCKETS     = ("competitor", "editorial")
NON_OWNABLE_SOURCE_BUCKETS = ("ugc", "review", "reference", "certifying_body")

# How a registry brand type pins the bucket for pages on that brand's domain.
# not_actionable is deliberately absent: "not a rival" doesn't say what the
# page IS (indeed.com's career guide is still an editorial slot), it only
# vetoes the competitor verdict - handled at the end of source_type().
_REGISTRY_SOURCE_BUCKETS = {
    "competitor":      "competitor",
    "platform":        "review",
    "certifying_body": "certifying_body",
    "not_actionable":  "other",
}


def _registry_source_type(domain):
    """The registry override bucket for `domain`, or None when unpinned."""
    registry_type = registry_brand_type(domain)
    if registry_type is None:
        return None
    return _REGISTRY_SOURCE_BUCKETS.get(registry_type)


# The registry answers "is this ORG a rival" (domain-level default); whether
# THIS PAGE is the org's own sales content or a neutral multi-provider
# comparison is a page-level question page_type already answers (LLM-verified
# roundup/directory classification) - a competitor's content-marketing "best
# X courses" roundup naming several OTHER schools is not the same slot as
# their own course page, even though both live on the same domain. Threshold
# deliberately generous (>=3 distinct brand_mentions keys): a competitor's own
# single-product page can still self-mention under 1-2 name variants ("Wedding
# Academy" / "V Wedding Academy") without being a genuine comparison.
_MIN_ROUNDUP_BRANDS = 3


def _is_multi_provider_roundup(facts):
    return (facts.get("page_type") in ("roundup", "directory")
            and len(facts.get("brand_mentions") or {}) >= _MIN_ROUNDUP_BRANDS)


def source_type(facts):
    """Ownability bucket for one cited page: ugc | review | reference |
    certifying_body | editorial | competitor | other. Domain rules override
    page_type - a
    community.* / forum.* subdomain is ugc even when the root domain matched
    a competitor brand token.

    The brand registry outranks everything below the subdomain/subpath rules:
    a domain owned by a registry-typed brand buckets by that type (competitor/
    platform/certifying_body pin the bucket; not_actionable vetoes only a
    competitor verdict, so a stale competitor stamp on a job board's page
    abstains instead of swinging the vote) - EXCEPT a competitor pin on a page
    that's itself a multi-provider roundup/directory (_is_multi_provider_roundup):
    the registry says the ORG is a rival, but a "best X courses" comparison
    page naming several OTHER schools is a different slot than that rival's
    own course page, and page_type (LLM-verified) already knows which one this
    is. Falls through to the page_type-based mapping below in that case.

    A page we FAILED to read whose domain matched no rule carries the
    "editorial" page_type as a fallback guess, not a classification - it
    buckets as "other" so it abstains from the dominance vote. Domain-derived
    types (competitor brand token, .gov, community/video - and the ugc/review/
    reference rules above) still vote when unfetched: their type came from
    the domain, not the page body. Subpath carve-outs (_SUBPATH_SOURCE_TYPES)
    are equally deterministic - URL structure, not page body - so they too
    vote regardless of fetch outcome.
    """
    domain = facts.get("domain", "")
    if _UGC_SUBDOMAIN.match(domain):
        return "ugc"
    subpath = _subpath_source_type(domain, facts.get("final_url") or facts.get("url"))
    if subpath:
        return subpath
    registry_bucket = _registry_source_type(domain)
    if registry_bucket is not None and not (
            registry_bucket == "competitor" and _is_multi_provider_roundup(facts)):
        return registry_bucket
    root = _root_domain(domain)
    if root in _REVIEW_DOMAINS:
        return "review"
    if root in _REFERENCE_DOMAINS:
        return "reference"
    page_type = facts.get("page_type")
    if page_type == "editorial" and facts.get("status") not in ("ok", "not_fetched"):
        return "other"
    bucket = _PAGE_TYPE_TO_SOURCE.get(page_type, "other")
    if bucket == "competitor" and registry_brand_type(domain) == "not_actionable":
        return "other"   # registry veto: not a rival - abstain, don't swing
    return bucket


def source_votes(winner_facts):
    """
    Citation-weighted vote per source bucket over a question's cited winners;
    "other" pages abstain (they neither confirm nor deny ownability). Weights
    come from facts["citation_count"] (attached by the caller); a URL cited
    40x outweighs one cited once.
    """
    votes = {}
    for f in winner_facts:
        bucket = source_type(f)
        if bucket == "other":
            continue
        votes[bucket] = votes.get(bucket, 0) + (f.get("citation_count") or 1)
    return votes


# Which QC school a QC-owned URL belongs to (shared by the rec builders).
SCHOOL_BY_DOMAIN_TOKEN = {
    "qcpetstudies":    "QC Pet Studies",
    "qceventplanning": "QC Event Planning",
    "qcdesignschool":  "QC Design School",
    "qcmakeupacademy": "QC Makeup Academy",
}


def school_for_url(url):
    for token, name in SCHOOL_BY_DOMAIN_TOKEN.items():
        if token in (url or ""):
            return name
    return None


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
