"""
Brand registry builder: dedup + rule-classify the LLM-extracted competitor
brand list (mention_response_brands, brand_type='competitor'). Writes two
artifacts, never the DB:

  brand_registry_review.csv          the human review surface (repo root)
  api/knowledge/brand_registry.json  the runtime artifact page_facts consumes:
                                     registry types feed source_type and the
                                     competitor brand list, so a review ruling
                                     here IS the pipeline's classification -
                                     it can no longer silently drift.

Pass 1  variants of one entity collapse to a canonical brand:
        case/punctuation/possessive/®, UK->US spelling, bare domains
        (pennfoster.edu), parenthetical acronyms verified against the name's
        initials, "X ... from/by BRAND" phrasings, and brand-prefix descriptor
        tails ("Penn Foster Pet Grooming Certificate Program" -> Penn Foster).
        n_responses is recomputed as DISTINCT responses across the merged
        variant set, so co-mentioned variants don't double count.

Pass 2  rule classification into competitor | certifying_body | platform |
        not_actionable. Rules only - nothing is hand-marked; what the rules
        can't confidently place keeps needs_review=true.

Pass 3  CSV: canonical_name, variants, n_responses, schools, proposed_type,
        matched_rule, domains, needs_review. Domains come ONLY from variants
        that are literally domains - never derived from brand tokens (that
        tokenization is how "Unity" matched unity.edu in the first place).

    python -m scripts.build_brand_registry
"""

import csv
import json
import os
import re
import unicodedata
from datetime import datetime, timezone

from api.db import get_connection

OUT_PATH = os.path.join(os.path.dirname(__file__), "..", "brand_registry_review.csv")
RUNTIME_PATH = os.path.join(
    os.path.dirname(__file__), "..", "api", "knowledge", "brand_registry.json")

# Tokens that may be LEFT OVER after removing a candidate brand's tokens
# without blocking a merge - function words plus the niche's descriptor
# vocabulary. Deliberately NOT used to reject entities, only to decide
# whether the remainder of a longer name is descriptive fluff.
_DESCRIPTORS = {
    # function words
    "the", "of", "and", "for", "by", "from", "a", "an", "at", "in", "on",
    "with", "or", "to", "s", "its", "her", "his",
    # education / product descriptors
    "school", "schools", "academy", "academies", "college", "colleges",
    "university", "institute", "program", "programs", "course", "courses",
    "class", "classes", "certificate", "certificates", "certification",
    "certifications", "certified", "training", "online", "virtual",
    "distance", "learning", "self", "study", "studies",
    # niche subject words
    "professional", "pet", "pets", "dog", "dogs", "canine", "grooming",
    "groomer", "groomers", "animal", "animals", "behavior", "wedding",
    "weddings", "event", "events", "planning", "planner", "planners",
    "decor", "decorating", "trainer", "trainers", "career", "careers",
    "master", "expert", "partner", "more", "free", "care",
}

_FUNCTION_WORDS = {"the", "of", "and", "for", "a", "an", "or", "to"}

_UK_US = {"behaviour": "behavior", "colour": "color", "centre": "center"}

_DOMAIN_RE = re.compile(r"^[a-z0-9][a-z0-9.-]*\.(com|edu|org|net|online|io|ie|co\.uk|ca|us)$", re.I)
_TLD_PARTS = {"com", "edu", "org", "net", "online", "io", "ie", "co", "uk", "ca", "us", "www"}


def _clean(name):
    name = unicodedata.normalize("NFKC", name).replace("’", "'").replace("–", "-")
    name = name.replace("&", " and ")
    return re.sub(r"[®™©]", "", name).strip()


def _tokens(text):
    toks = [t for t in re.findall(r"[a-z0-9]+", text.lower()) if t != "s"]
    return [_UK_US.get(t, t) for t in toks]


def _squash(tokens):
    return "".join(tokens)


def _initials(tokens):
    return "".join(t[0] for t in tokens if t not in _FUNCTION_WORDS)


def _domain_key(name):
    """('pennfoster.edu' -> 'pennfoster') for variants that ARE a domain."""
    if not _DOMAIN_RE.match(name.strip().lower()) or " " in name:
        return None
    parts = [p for p in re.split(r"[.\-]", name.lower()) if p and p not in _TLD_PARTS]
    return "".join(parts) or None


class Entry:
    """One raw brand_name row-group with its normalized forms."""

    def __init__(self, raw, response_ids, schools):
        self.raw = raw
        self.response_ids = response_ids
        self.schools = schools
        base = _clean(raw)

        # Parentheticals: verified acronyms are kept for the acronym-merge
        # pass; anything else in parens is descriptive and dropped.
        self.acronyms = set()
        chunks = re.findall(r"\(([^)]*)\)", base)
        self.paren_text = " ".join(chunks)   # classify() scans this too (HVCC)
        stripped = re.sub(r"\([^)]*\)", " ", base)
        base_tokens = _tokens(stripped)
        for c in chunks:
            ctoks = _tokens(c)
            if ctoks and len(_squash(ctoks)) <= 10 and \
                    _squash(ctoks) == _initials(base_tokens):
                self.acronyms.add(_squash(ctoks))
        if not [t for t in base_tokens if t not in _DESCRIPTORS] and chunks:
            # "Best (Paragon Pet School)": the parens hold the real name
            inner = _tokens(chunks[0])
            if [t for t in inner if t not in _DESCRIPTORS]:
                base_tokens = inner

        self.domain = base.lower() if _domain_key(base) else None
        self.tokens = _tokens(_domain_key(base)) if self.domain else base_tokens
        if self.tokens and self.tokens[0] == "the":
            self.tokens = self.tokens[1:]
        self.key = _domain_key(base) or _squash(self.tokens)
        self.core = [t for t in self.tokens if t not in _DESCRIPTORS] or self.tokens

        # "Dog Trainer Certification Program from Penn Foster" -> penn foster
        self.alt_tokens = None
        for sep in ("from", "by"):
            if sep in self.tokens:
                tail = self.tokens[len(self.tokens) - self.tokens[::-1].index(sep):]
                if [t for t in tail if t not in _DESCRIPTORS]:
                    self.alt_tokens = tail

    @property
    def n(self):
        return len(self.response_ids)


class Group:
    def __init__(self, entry):
        self.entries = [entry]

    def absorb(self, other):
        self.entries.extend(other.entries)

    @property
    def response_ids(self):
        return set().union(*(e.response_ids for e in self.entries))

    @property
    def n(self):
        return len(self.response_ids)

    @property
    def schools(self):
        return sorted(set().union(*(e.schools for e in self.entries)))

    @property
    def acronyms(self):
        return set().union(*(e.acronyms for e in self.entries))

    @property
    def domains(self):
        return sorted({e.domain for e in self.entries if e.domain})

    @property
    def rep(self):
        """Shortest-core entry = the bare brand name (merge needle)."""
        return min(self.entries, key=lambda e: (len(e.core), len(e.tokens)))

    @property
    def canonical(self):
        """Display name: most-cited variant, preferring non-domain, tidy-case."""
        def rank(e):
            ugly = bool(e.domain) or e.raw == e.raw.lower() or e.raw == e.raw.upper()
            return (-e.n, ugly, len(e.raw))
        return min(self.entries, key=rank).raw

    @property
    def variants(self):
        return sorted({e.raw for e in self.entries}, key=str.lower)

    @property
    def all_text(self):
        return " ".join(
            " ".join(e.tokens) + " " + e.paren_text for e in self.entries)


def _contains_seq(haystack, needle):
    return any(haystack[i:i + len(needle)] == needle
               for i in range(len(haystack) - len(needle) + 1))


def _descriptor_tail(s):
    """Is a squashed remainder ("careerschool") a chain of descriptor words?"""
    while s:
        hit = next((d for d in _DESCRIPTORS if s.startswith(d)), None)
        if not hit:
            return False
        s = s[len(hit):]
    return True


def _needles(group):
    """Candidate brand forms for merging, from EVERY variant: the distinctive
    core AND the full token sequence (a domain-form rep like "pennfoster" must
    not hide "penn foster"; "MSI Certified" must offer its full 2-word form,
    not just the 1-word core [msi])."""
    seen = []
    for e in group.entries:
        for cand in (list(e.core), list(e.tokens)):
            if cand and any(t not in _DESCRIPTORS for t in cand) and cand not in seen:
                seen.append(cand)
    return seen


def _identity_squashes(group):
    """Squashed names that VERIFIABLY denote this group's brand: its
    parenthetical-verified acronyms plus each variant's computed initials."""
    ids = set(group.acronyms)
    for e in group.entries:
        ids.add(_initials(e.tokens))
    return {i for i in ids if len(i) >= 3}


# Name-prefix words shared across unrelated brands. A multi-word needle made
# ONLY of these (+descriptors) - "New York", "American ..." - identifies a
# place, not a brand, and must not self-confirm a merge.
_GENERIC_NAME_WORDS = {
    "new", "york", "american", "america", "us", "usa", "uk", "international",
    "national", "global", "world", "city", "state", "best", "top",
}


def _domain_verified(group, other, needle_squash):
    """A domain-form variant on either side spells out the brand core -
    unity.edu confirms [unity], nyiad.edu confirms [nyiad]."""
    return any(e.domain and e.key == needle_squash
               for e in group.entries + other.entries)


def _merges_into(group, other):
    """
    Does `other` look like `group`'s brand plus descriptive fluff?

    Merges on a ONE-word brand core are only accepted when independently
    confirmed: the full names are identical after normalization, a domain
    variant spells the core out, or the leftover is the brand's verified
    acronym. A shared adjective ("American ...") must never fold two schools'
    citation counts together - a bad merge is worse than a split.
    """
    identity = _identity_squashes(group)
    for needle in _needles(group):
        nsq = _squash(needle)
        for cand in (other.rep.tokens, other.rep.alt_tokens):
            if not cand:
                continue
            if _squash(cand) == nsq:      # the same full name, just reformatted
                return True
            distinctive = any(t not in _GENERIC_NAME_WORDS and t not in _DESCRIPTORS
                              for t in needle)
            confirmed = ((len(needle) >= 2 and distinctive)
                         or _domain_verified(group, other, nsq)
                         or nsq in identity)   # needle IS the verified acronym
            if _contains_seq(cand, needle):
                leftover = [t for t in cand if t not in needle]
                if any(t in group.acronyms for t in leftover):
                    confirmed = True      # verified initials name the brand
                if confirmed and all(t in _DESCRIPTORS or t in group.acronyms
                                     for t in leftover):
                    return True
            # run-together forms: "Posheventscourse" vs [posh, events]
            if confirmed and len(nsq) >= 6 and _squash(cand).startswith(nsq) \
                    and _descriptor_tail(_squash(cand)[len(nsq):]):
                return True
    return False


def dedup(entries):
    # Stage A: exact normalized key (case, punctuation, domains, the-, UK/US)
    by_key = {}
    for e in entries:
        if e.key in by_key:
            by_key[e.key].absorb(Group(e))
        else:
            by_key[e.key] = Group(e)

    # Stage B: bare-acronym groups ("NYIAD", "CCPDT", "KPA-CTP") -> the unique
    # group whose verified parenthetical acronym or computed initials match
    # (ambiguous ones - "ABC" - stay put). Runs BEFORE containment so a
    # group's verified acronym can confirm 1-word merges there ("NAPPS
    # Certification" needs NAPPS already inside its owner group).
    pooled, acronym_owners = [], {}
    for g in by_key.values():
        for a in g.acronyms | {_initials(g.rep.tokens)}:
            if len(a) >= 3:
                acronym_owners.setdefault(a, []).append(g)
    for g in by_key.values():
        # "NYIAD" but also hyphen-split acronyms ("KPA-CTP" -> [kpa, ctp])
        if len(g.rep.tokens) <= 2 and len(g.rep.key) <= 8:
            owners = [o for o in acronym_owners.get(g.rep.key, [])
                      if o is not g and len(o.rep.tokens) > 1]
            if len(owners) == 1:
                owners[0].absorb(g)
                continue
        pooled.append(g)

    # Stage C: brand + descriptor-tail containment, shortest brands first so
    # "Penn Foster" exists as a target before its long variants are visited.
    groups = sorted(pooled, key=lambda g: (len(g.rep.core), len(g.rep.tokens), -g.n))
    merged = []
    for g in groups:
        target = next((m for m in merged if _merges_into(m, g)), None)
        (target.absorb(g) if target else merged.append(g))
    return merged


# ─────────────────────────────────────────────────────────────────────────────
# Pass 2: rule classification
# ─────────────────────────────────────────────────────────────────────────────

# udemy, skillshare and alison are NOT platforms here (approved 2026-07):
# engines cite their own class/course product pages as places to take the
# course instead of QC - they behave as competitors, not review/catalog
# surfaces. (skillshare's cited slot is an individual class page; alison SELLS
# its own courses, unlike a marketplace hosting other providers'.)
_PLATFORMS = {
    "coursera", "edx", "linkedinlearning", "masterclass",
    "futurelearn", "coursehorse", "udacity",
}

_COMPETITOR_EXPLICIT = {
    "udemy": "approved: marketplace cited via course product pages (competitor)",
    "skillshare": "approved: cited via its own class product pages (competitor)",
    "alison": "approved: sells its own courses, cited as the place to take them (competitor)",
    # fearfree sells its certification program directly (its cited page is the
    # program's own sales page) - a certifying body in name, a course seller
    # in practice (approved 2026-07-10).
    "fearfree": "approved: sells its own certification program (competitor)",
    # cvent.com proper holds ownable vendor slots (page_facts already treated
    # it so); community.cvent.com stays ugc via the community-subdomain rule
    # (approved 2026-07-10).
    "cvent": "approved: vendor's own pages hold ownable slots (competitor)",
}

_JOB_ECOM_SAAS = {
    "indeed", "ziprecruiter", "glassdoor", "rover", "printify", "thimble",
    "alibaba", "shopify", "etsy", "woocommerce", "ankorstore", "makersrow",
    "munbyn", "weddingwire", "eventbrite", "socialtables", "moego",
    "timetopet", "revelationpets", "wagbar", "perfectvenue", "designfiles",
    "careervillage", "collegeraptor", "usnews", "topuniversities", "calcareers",
    "careershifters", "eventective", "cvlinens", "easybusypets",
    "petcareins",   # insurer whose blog the extractor mistook for a school
}

# Universities whose brand rows don't SAY university/college ("Purdue",
# "Emory University's ..." variants aside) plus bare campus acronyms.
_KNOWN_UNIVERSITIES = {
    "purdue", "emory", "ucdavis", "gwu", "nyu", "csulb", "uga", "fgcu",
    "fiu", "hvcc", "uno", "waketech", "uclaextension",
}

# Known certifying bodies the name-pattern rules might miss. fearfree moved
# to _COMPETITOR_EXPLICIT (approved 2026-07-10): it sells its own program.
_CERTIFYING_EXPLICIT = {
    "americankennelclub", "petsittersinternational",
    "eventindustrycouncil", "petindustryfederation", "thebridalsociety",
    "bridalsociety", "certifiedweddingplannersociety", "cwpsociety",
}

# Bare credential acronyms we can vouch for (everything else short + capsy
# gets flagged instead of trusted). KPA-CTP is deliberately absent: its group
# is Karen Pryor Academy, a school, not the credential.
_CREDENTIAL_ACRONYMS = {
    "ccpdt", "apdt", "capdt", "iacp", "iaabc", "ndgaa", "ipg", "napps",
    "paccc", "cmg", "csep", "cmp", "aacwp", "wpga", "mpi", "ilea", "cpps",
    "ppg", "psi",
}

# University-word hits that are really vocational schools selling training -
# they keep type=competitor outright. georgiancollege and southtexascollege
# approved 2026-07-10: real colleges, but their cited pages are vocational
# program pages a QC student would genuinely choose between (the content
# classifier reads them as provider).
_UNIVERSITY_COMPETITOR_OVERRIDES = {
    "animalbehaviorcollege", "iapcareercollege", "oxfordhomestudycollege",
    "oxfordhomestudy", "britishcollegeofcaninestudies", "caninecollege",
    "thecanineuniversity", "canineuniversity",
    "georgiancollege", "southtexascollege",
}

_UNIVERSITY_RE = re.compile(
    r"\b(university|universities|college|colleges|community college|state|"
    r"extension|cuny|boces|school of business)\b", re.I)
# "Institute of ..." is anchored: mid-name hits ("New York Institute of Art
# and Design") are schools, not industry bodies.
_CERTIFYING_RE = re.compile(
    r"\b(association|council|federation|guild|society)\b|"
    r"^(the )?institute of\b|\bcertification council\b", re.I)
# Subject words suggesting a university SELLS a standalone certificate here.
_CERT_SELLER_HINT_RE = re.compile(
    r"\b(certificate|certification|event|wedding|planning|planner|canine|"
    r"pet|dog|grooming|animal|career training)\b", re.I)

# A "generic noun" non-entity: every token is niche vocabulary, no proper
# noun. Entity-ish suffixes (Institute, Academy, Society) are excluded from
# this vocabulary - "Wedding Planning Institute" is a named entity even though
# each word is generic, while "Professional grooming school" is not.
_GENERIC_VOCAB = (_DESCRIPTORS - {"institute", "academy", "academies"}) | {
    "apprenticeship", "apprenticeships", "mentorship", "mentorships",
    "vocational", "local", "community", "caterer", "caterers", "chamber",
    "chambers", "commerce", "youtube", "tutorial", "tutorials", "academic",
    "behaviorist", "accelerated", "trade", "hands", "private", "person",
    "short", "term", "basic", "comprehensive", "veterinary", "technician",
    "photographer", "walking", "walker", "business", "owner", "art", "arts",
    "studio", "studios", "sitter", "boarder", "path", "paths", "bather",
    "stylist", "corporate", "offered", "hospitality", "concentration",
    "concentrations", "physical", "therapist", "education", "programs",
}


def _is_generic(group):
    return all(t in _GENERIC_VOCAB for e in group.entries for t in e.tokens)


def _school_word(text):
    return bool(re.search(
        r"\b(school|academy|training|institute|course|courses|grooming|"
        r"college|studies|certification program)\b", text, re.I))


def classify(group):
    """(proposed_type, matched_rule, needs_review)"""
    key = group.rep.key
    squashed_all = {_squash(e.tokens) for e in group.entries} | {key}
    text = group.all_text
    entry_names = [" ".join(e.tokens) for e in group.entries]

    for k, why in _COMPETITOR_EXPLICIT.items():
        if k in squashed_all:
            return "competitor", why, False
    if squashed_all & _PLATFORMS:
        return "platform", "platform list (course marketplace)", False
    if squashed_all & _JOB_ECOM_SAAS:
        return "not_actionable", "job board / e-commerce / SaaS list", False
    if _is_generic(group):
        return "not_actionable", "generic noun - no proper noun", False

    # Known certifying bodies outrank the university word-match (American
    # Kennel Club "Canine College" is still the AKC).
    if squashed_all & _CERTIFYING_EXPLICIT:
        return "certifying_body", "known certifying body", False

    if squashed_all & _UNIVERSITY_COMPETITOR_OVERRIDES:
        return "competitor", "university-word override: vocational school", False
    if _UNIVERSITY_RE.search(text) or squashed_all & _KNOWN_UNIVERSITIES:
        if _CERT_SELLER_HINT_RE.search(text):
            return ("not_actionable", "university - but may sell a standalone "
                    "certificate (flagged)", True)
        return "not_actionable", "university / college", False

    if any(_CERTIFYING_RE.search(n) for n in entry_names) \
            or _CERTIFYING_RE.search(group.rep.paren_text.lower()):
        return "certifying_body", "association/council/institute-of pattern", False
    if _tokens(group.canonical)[:1] == ["certified"]:
        return "certifying_body", "credential name (Certified ...)", False
    if key in _CREDENTIAL_ACRONYMS or (group.acronyms & _CREDENTIAL_ACRONYMS):
        return "certifying_body", "known credential acronym", False
    if len(group.rep.tokens) == 1 and len(key) <= 6 and group.rep.raw.isupper():
        return "certifying_body", "bare acronym - UNVERIFIED", True

    if _school_word(text):
        return "competitor", "named school/program word", False
    return "competitor", "default (no rule matched)", True


def build():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT b.brand_name, b.mention_response_id,
                       COALESCE(q.school::text, 'General')
                FROM mention_response_brands b
                JOIN mention_responses m ON m.id = b.mention_response_id
                LEFT JOIN questions q ON q.id = m.question_id
                WHERE b.brand_type = 'competitor'
            """)
            rows = cur.fetchall()

    raw = {}
    for name, rid, school in rows:
        d = raw.setdefault(name, {"ids": set(), "schools": set()})
        d["ids"].add(rid)
        d["schools"].add(school)
    entries = [Entry(name, d["ids"], d["schools"]) for name, d in raw.items()]

    groups = dedup(entries)

    out = []
    for g in groups:
        ptype, rule, _rule_review = classify(g)
        # Volume gate: 1-2 responses cannot swing a dominance vote. Such
        # brands abstain (not_actionable) and skip review entirely - the rule
        # verdict is preserved in matched_rule so they can be promoted later
        # if they accumulate volume. Review effort goes to n >= 3 only.
        if g.n <= 2:
            rule = f"low volume (n<=2) - abstains; rule said {ptype}: {rule}"
            ptype = "not_actionable"
            review = False
        else:
            review = True
        out.append({
            "canonical_name": g.canonical,
            "variants": "; ".join(g.variants),
            "n_responses": g.n,
            "schools": "; ".join(g.schools),
            "proposed_type": ptype,
            "matched_rule": rule,
            "domains": "; ".join(g.domains),
            "needs_review": review,
        })
    out.sort(key=lambda r: (-r["n_responses"], r["canonical_name"].lower()))

    path = os.path.abspath(OUT_PATH)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0].keys()))
        w.writeheader()
        w.writerows(out)

    # The runtime artifact: same rows, machine shape, sorted by n desc so the
    # highest-volume brand wins when two rows both claim a domain.
    runtime_path = os.path.abspath(RUNTIME_PATH)
    with open(runtime_path, "w", encoding="utf-8") as f:
        json.dump({
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source": "scripts/build_brand_registry.py",
            "brands": [{
                "name": r["canonical_name"],
                "type": r["proposed_type"],
                "rule": r["matched_rule"],
                "n": r["n_responses"],
                "variants": r["variants"].split("; "),
                "domains": [d for d in r["domains"].split("; ") if d],
            } for r in out],
        }, f, indent=1, ensure_ascii=False)

    n_raw = len(entries)
    print(f"{n_raw} raw brand rows -> {len(out)} canonical brands "
          f"({n_raw - len(out)} variants collapsed)")
    types = {}
    for r in out:
        types[r["proposed_type"]] = types.get(r["proposed_type"], 0) + 1
    print("types:", types)
    print("needs_review:", sum(1 for r in out if r["needs_review"]))
    print(f"wrote {path}")
    print(f"wrote {runtime_path}")
    return out


if __name__ == "__main__":
    build()
