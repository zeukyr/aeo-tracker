# Recommendations, Two-Tab Redesign — Plan

Reshapes the single Recommendations list into two audience-specific tabs, and replaces
vague LLM prose with **evidence-backed, page-grounded** recommendations.

Companion to `recommendation-evidence-detail-todo.md` (Fix A/B, DONE) and
`recommendation-system-phases-bc.md`. Supersedes the earlier single-list model.

---

## The two tabs

| | **Tab 1 — Strategic Growth** | **Tab 2 — Improve Existing Pages** |
|---|---|---|
| Question | *"What don't we have?"* | *"We have a page. Why isn't AI using it?"* |
| Audience | Marketing manager / owner | Web / content team |
| Shape | Missing *presence* — a new owned page/hub **or** an external mention QC should earn | Section-level edits to an existing QC page |
| Cadence | Infrequent, high-impact | Iterative |
| action_types | `content`(build), `outreach`(seek inclusion), `citation`(submit listing / earn), `strategy`(ecosystem) | `technical`(have_page) |
| Routing | `diagnose_coverage` = `missing_page` → here | `diagnose_coverage` = `have_page` **and** QC not cited → here |

The sitemap is only the **first filter** — it answers "does QC have a page?" It cannot answer
"*should* QC have its own page, or is the better move to be included elsewhere?" That second
question is answered by classifying what AI cites (see Tab 1 engine). Routing between tabs is
deterministic (sitemap verdict); routing *within* Tab 1 comes from page classification.

It also cannot answer "is it the right **kind** of page?" — a topical slug match can hide a
**genre mismatch** (QC's dog-grooming *course* page matches "how to become a dog groomer", but
engines cite how-to *guides* there). Phase 6 makes the verdict three-way: `missing_page` →
build (Tab 1), `have_page` + right genre → fix (Tab 2), `have_page` + **wrong genre** → build
the missing genre alongside the existing page (Tab 1).

---

## Core principle — only claim what we verified

The earlier fabrication ("APDT references Penn Foster") came from inferring a page's
**contents** from citation **co-occurrence** in the AI answer. Every claim is tiered:

- **Tier A — citation facts (we have these):** which URLs engines cite for a topic, how
  often, and whether QC is among them. No fetching.
- **Tier B — page-content facts (require fetching):** "this page has an FAQ section",
  "QC's page lacks a certification section". Only asserted after a fetch confirms it.

**Guardrail:** a recommendation may never assert what's on a page unless a fetched fact
backs it. Tab 1's **basic** form is Tier A (ships without fetching: "AI cites X, not QC").
Tab 1's **smart** form — knowing the *action* fits the page (only "seek inclusion" when the
page actually lists providers) — is Tier B, but reuses the exact fetch Tab 2 needs. Tab 2 is
fully Tier B.

---

## Tab 1 engine — page classification & the two gaps

One generic "pursue inclusion" action can't sit under every cited URL, because the cited URLs
aren't the same kind of thing. "Contact APDT to be listed" is nonsense — APDT maintains no
directory of schools. The action must be **derived from what kind of page AI is citing**, so
the LLM fills in details within a predefined strategy instead of inventing the action.

### Page classification → templated action
Classified per URL (cached in `page_facts`; deterministic hints — TLD, domain lists — plus an
LLM classification for roundup-vs-guide):

| Page type | Example | Templated action |
|---|---|---|
| Competitor (owned commercial) | Penn Foster course page | Compare content → build equivalent (if QC has no page) |
| Editorial roundup (lists providers) | "Best Online Dog Training Courses" | **Seek inclusion** — only when the fetch confirms it lists competitors and not QC |
| Directory | Course/provider directory | Submit listing |
| Association / authority | APDT, AKC | Benchmark content; **don't pitch** (they list no one) |
| Government | Bureau of Labor Statistics (.gov) | Cite as a source; don't pitch |
| Community | Reddit, Quora | Authentic presence only — **no manufactured/anonymous posts** |
| Video | YouTube | Consider video content if strategically relevant |

"Seek inclusion" only fires when a fetch confirms the page names ≥1 competitor and not QC —
the same `page_facts` brand-mention detection Tab 2 uses. This is the guardrail that killed the
"pitch a page that lists no one" problem.

### Three kinds of evidence (aggregate before routing)
A topic's citations are a **mix** (authority + competitor + community + video at once), so
classify every cited page, then roll up — don't emit one card per URL:

1. **Specific opportunities** (roundups, directories that list rivals, not QC) → *seek inclusion / submit listing.*
2. **Authority patterns** (associations, government) → *benchmark & align content* (a **Tab 2 input** if QC has a page; a spec for the new page if QC doesn't).
3. **Ecosystem patterns** (aggregate composition — "Reddit = 42% of cited sources", "67% are associations", "8/10 cited pages are educational guides, not sales pages") → *adjust broader strategy* (community presence; build educational content; pursue placement over pages). These don't depend on any single URL.

### The two gaps inside Tab 1
"No QC page" splits two ways — conflating them is what produced the bad APDT rec:

- **Gap A — missing owned content.** No QC page, and the winners are mostly competitor-owned
  commercial pages → an owned page *can* win → **build one.**
- **Gap B — missing external presence.** No QC page, and the winners are mostly third-party
  impartial pages (roundups, directories, association guides) → an owned QC "best courses" page
  would be self-serving and won't take the neutral slot → **earn placement** (inclusion / listing /
  presence) **or** build owned content of a *different genre* (an educational hub, not a sales page).

**Build-vs-earn decision rule (computable):** look at the composition of cited pages. Winners
mostly **competitor-owned commercial** → Gap A (build). Winners mostly **third-party impartial**
→ Gap B (earn / educational content). "Did competitors win with their own pages, or did neutral
third parties win?" is a ratio over the same classifications — not a judgment call.

### Routing within Tab 1
```
Weak topic → QC has a page? ──yes──► Tab 2
                 │no
                 ▼
        Classify what AI cites → composition:
          mostly competitor-owned commercial → Gap A: build a page
          mostly third-party impartial       → Gap B: earn inclusion / educational hub
          community-dominated                → ecosystem: authentic presence
          authority/government-dominated     → benchmark → spec the new page
```

---

## Tab 2 engine — the intersection filter

Neither approach alone is good enough:
- **Competitor-copying** ("Penn Foster has a tuition calculator, build one") → narrow, cargo-cult.
- **Generic GEO** ("add FAQ schema, use H2s") → advice you could give without looking at QC's data.

The recommendation is the **intersection**: a GEO-important feature that the pages AI
actually cites consistently have, and QC lacks.

```
AI is citing these pages
        ↓  rank cited URLs for the topic by frequency; drop QC-owned, YouTube/Reddit/PDF
Top N cited pages (competitors AND authorities — APDT, AKC count too)
        ↓  fetch + extract features (Tier B)
Feature prevalence among winners  ─┐
GEO importance (playbook prior)    ─┼→  score
QC page's own features             ─┘
        ↓
Recommend feature when: prevalence high AND QC missing AND geo_weight above floor
```

**Compare against the top cited pages regardless of competitor vs. authority** — they
all shape the AI answer. Tab 2 is about matching the information architecture AI rewards,
not beating competitors.

### The scorecard (Layer 1 — fixed checklist)
A fixed, curated feature taxonomy scored identically against every page so columns line up:

| Feature | GEO importance | Winning pages | QC | Recommend? |
|---|---|---|---|---|
| Direct answer first | High | 5/5 | No | ✅ |
| FAQ schema | Medium | 5/5 | No | ✅ |
| Tuition section | Medium | 4/5 | No | ✅ |
| Career outcomes | High | 5/5 | No | ✅ |
| Instructor bios | Medium | 5/5 | Yes | ❌ (QC has it) |
| Organization schema | Low | 2/5 | No | ❌ (not distinguishing) |

- **GEO importance is a veto/floor, not the ranker.** Prevalence ranks; the weight only
  stops recommending high-prevalence-but-worthless features (every page has a footer — 5/5,
  zero GEO value).
- **Recommend rule:** `prevalence_high AND qc_missing AND geo_weight > floor`.

### The emergent pass (Layer 2 — discovered patterns)
The fixed list can't anticipate topic-specific architecture. One extra LLM call: *"what
content/ordering patterns do these cited pages share that QC lacks?"* Catches insights like:

> Cited pages explain certification pathways (CCPDT, APDT) before describing programs;
> QC opens with the course description. Add a Certification Requirements section after
> the intro.

Labeled **lower-confidence / qualitative**, kept separate from the scorecard.

### Recommendation granularity — section level, not paragraph
"Add a Certification Requirements section", not "rewrite paragraph 3." Durable (survives
page edits) and measurable (a trackable unit of work for the closed-loop diff-in-diff).

---

## Reliability rules (Tier B)
1. **QC-side detection precision > winner-side.** Same detector, same page-cleaning for QC
   and winners; **conservatively biased on QC** — when unsure QC has a feature, don't
   recommend adding it. A false "you're missing X" burns trust.
2. **Minimum N.** After dropping YouTube/Reddit/PDF/QC-owned, require ≥3 fetchable winners
   or the topic falls back to generic GEO advice. Report prevalence coarsely (most/some/few).
3. **Hybrid detection, fixed checklist.** Deterministic parse for schema/structural features
   (FAQPage/Organization JSON-LD, video embeds); LLM checklist for semantic ones
   (direct-answer-first — fed the topic's representative question, certification section,
   tuition). Cache features **per URL**, not per topic.
4. **Degrade, never fabricate.** Comparison runs on whatever fetched; every comparative
   claim names which fetched pages show the pattern; too few pages → Tier-A fallback.
5. **Recommendations are hypotheses.** Matching architecture correlates with citation, it
   doesn't guarantee it (authority/backlinks matter too). UI reads them as informed bets;
   the existing measurement loop validates them.

---

## Phases

### Phase 1 — Two-stream split, Tier A only (no fetching) — **DONE (2026-07-03)**
- [x] Derive `work_stream` (`strategic` / `on_page`): `_work_stream()` in
      `recommendations_synthesis.py`, returned by `get_saved_recommendations()`
      (`technical` → on_page — set deterministically by the coverage diagnosis — else strategic).
- [x] Tab 1 recs: citation-verifiable claims only. Generation prompt now forbids asserting a
      third-party page's contents (who it lists/ranks/mentions); judge scores
      `evidence_grounding <= 2` for any page-content claim.
- [x] Frontend: type dropdown in `Recommendations.jsx` replaced with two work-stream tabs
      (counts + question subtitles + per-stream note); Active + priority sections filter by tab.
- [x] Verified: live API returns `work_stream` (current batch: 5 recs, all strategic —
      on_page fills after the next generation run produces `technical` recs); `npm run build` passes.

### Phase 2 — Page-content layer (`page_facts` cache) — **DONE (2026-07-03)**
- [x] `api/queries/page_facts.py`: guarded fetch (robots.txt, 25s timeout, 2.5MB size cap,
      content-type guard), cached per URL in `api/knowledge/page_facts.json`. Failures cached
      too (Penn Foster 403s → status `fetch_failed`, domain-level classification only, no
      content claims possible). Community/video URLs classified from domain, never fetched.
- [x] Main-content extraction via **trafilatura** (new dep, pinned in requirements.txt);
      headings filtered to those surviving in the extracted main text so nav chrome doesn't
      pollute the scorecard.
- [x] Per-URL facts: page classification (qc_owned / competitor / roundup / directory /
      association / government / community / video / guide — domain rules → heuristics → LLM
      for editorial disambiguation), brand mentions (DB competitor list, generic pseudo-brands
      like "Certification" filtered out), QC-mention flag, deterministic feature detections
      (FAQPage/Course/Org schema, question headings, tables, video, pricing signals),
      word count + 4k-char content excerpt for the later semantic passes.
      `inclusion_opportunity(facts)` implements the seek-inclusion gate: page read AND
      roundup/directory AND names ≥1 competitor AND never mentions QC.
- [x] Feature taxonomy artifact `api/knowledge/geo_features.json`: 12 features tagged
      deterministic-vs-semantic + geo_weight (documented as a veto floor, not a ranker).
- Verified live on real cited URLs: APDT → guide, gate False (don't pitch — the exact case
  that motivated this); petsittertraining.com "best certifications" → roundup listing NAPPS/
  Fear Free/PSI, no QC, gate **True**; AKC → guide (mentions Karen Pryor Academy in passing,
  gate correctly stays False); reddit → community, not fetched; QC dog-grooming page →
  qc_owned with Course schema + tuition + FAQ heading but **no FAQPage schema** and no
  certification-pathway section — the exact gap profile Tab 2's scorecard will formalize.

### Phase 3 — Tab 1 smart actions (page classification) — **DONE (2026-07-06)**
- [x] `api/queries/tab1_strategy.py`: `analyze_strategic_topic(segment)` pulls the top external
      cited URLs for the topic (`get_topic_cited_urls`, QC-owned excluded), classifies them via
      `page_facts`, and rolls them into the three evidence types + a build-vs-earn verdict.
      `PAGE_TYPE_ACTIONS` maps each page type to a templated action.
- [x] Templated action per classified page type; "seek inclusion" fires only through
      `inclusion_opportunity()` (roundup/directory AND names a competitor AND no QC).
- [x] Three evidence types: `specific_opportunities` (verified inclusion gates),
      `authority_patterns` (association/government/guide → benchmark, never pitch),
      `ecosystem` (coarse most/some/few composition, no single URL). `sufficient` flags
      <3 classified pages so the caller can fall back instead of asserting a mix.
- [x] Build-vs-earn: `gap` = "build" when competitor-owned commercial pages dominate,
      "earn" when impartial third parties do — computed from cited-page composition.
- [x] Wired into `build_evidence()`: for the weakest topics whose coverage verdict is not
      `have_page`, a `## STRATEGIC GROWTH ANALYSIS` section is added. New `strategy` action_type;
      generation prompt requires Tab 1 actions to follow the analysis; judge now permits a
      page-content claim only when it matches that URL's `page_type`/`lists_competitors`.
- Verified live: "How to Become" → gap `build` (6/8 competitor-owned), APDT/AKC surfaced as
  benchmark-don't-pitch authorities, zero fabricated inclusion opps (empty & respected);
  full `generate_recommendations()` dry run routes content/outreach/strategy → strategic and
  technical → on_page. Penn Foster/Indeed 403s degrade to domain-level classification.

### Phase 4 — Tab 2 scorecard + emergent pass — **DONE (2026-07-06)**
- [x] `api/queries/tab2_scorecard.py`: `build_scorecard(topic, qc_url, question)` ranks cited
      URLs, takes top-N fetchable comparable winners, detects the 12 `geo_features` across QC's
      page + winners (deterministic from page_facts + one semantic LLM pass per page), and scores
      each: prevalence among winners × QC-has × geo_weight veto → recommend.
- [x] Emergent-pattern LLM call (`_emergent_pattern`): what cited pages share that QC lacks.
- [x] `scorecard_to_recommendation` builds the Tab 2 rec **deterministically** from the scorecard
      (names the page + missing sections) — not LLM prose — so it can't come out generic.
      `build_tab2_recommendations` drives it for the weakest `have_page` topics; wired into
      `generate_recommendations` (replaces any generic LLM `technical` rec for the same topic).
- [x] The scorecard rides on the rec's new `detail` jsonb column (migration 003, applied).
- Verified: a real run produced a scorecard rec targeting QC's own page, comparing against the
  cited winners, flagging the certification/pathway + primary-source sections it lacks, with
  concrete section-level edits; `detail` round-trips through the DB.

### Phase 5 — Frontend build-out — **DONE (2026-07-06)**
- [x] Tab 2 card: `Scorecard` component in `Recommendations.jsx` renders page URL / compared-against
      cited pages / scorecard table (feature × GEO × cited-page prevalence × QC × recommend) /
      emergent insight / section-level edits, styled from the dashboard tokens.
- [x] Tab 1 card: `StrategicEvidence` component renders the truthful citation-bar block (what AI
      cites for the topic + counts, vs QC's own count), fed by `strategic_evidence()` on the rec's
      `detail`. Degrades to the plain card when the segment has no citation data. `npm run build` passes.
- [x] Health summary kept as a shared header above the tabs.
- Note: Tab 1 "seek-inclusion / benchmark / ecosystem" *variant* cards from the mockup are not
  separate components — the single evidence card covers all strategic recs. Revisit if the
  variant-specific layouts are wanted.

### Phase 6 — Deterministic Tab 1 + the wrong-genre gray area — **DONE (2026-07-07)**

**6a — content genre (`have_wrong_genre`).** Slug matching says "QC has a page on this topic";
it can't say "QC has the right *kind* of page". Genre is a second, orthogonal axis over the same
verified facts:
- [x] `page_facts.page_genre(facts)`: **informational** (how-to / career-guide architecture) vs
      **commercial** (course/program page), from deterministic signals only — Course schema,
      pricing, URL section (`/blog/`, `/resources/`, `/courses/`…), HowTo schema, title. Ambiguity
      → None, never a guess. `pricing_signals` is deliberately the weakest commercial vote (career
      guides quote salaries, which the pricing regex also matches — the bug the first live sweep
      caught on QC's own `/resources/your-dog-grooming-career`).
- [x] `_winner_genre`: format-implied types map directly (guide/association/government →
      informational; roundup/directory → commercial); ownership types (competitor) read content
      signals, then URL hints (403'd Penn Foster `/blog/how-to-*` pages still vote informational
      from the URL), then default commercial. Community/video don't vote.
- [x] `genre_gap(qc_facts, winner_facts)`: mismatch only when QC's genre is clear, ≥3 winners
      carry a clear genre, and ≥60% share a genre QC's page doesn't have — same "most" bar as
      build-vs-earn. `tab1_strategy.genre_check` / `coverage_genre_mismatches` run it per covered
      intent over cached page_facts.
- [x] Routing: `_apply_coverage_diagnosis` gives genre_check a **veto over the technical flip** —
      a `content` rec for a covered-but-wrong-genre intent stays `content` (Tab 1) instead of
      being forced to `technical`. `build_evidence` analyzes a strategic topic when it has
      uncovered intents **or** genre mismatches, and the prompt forbids phrasing a mismatch as
      "restructure the existing page".
- The mismatch doesn't cancel the Tab 2 tune-up — QC keeps and improves the course page *and*
  builds the guide; the wrong-genre rec is the leveraged move.

**6b — Tab 1 recs are templated, not LLM-authored.** The mirror of Phase 4's
`scorecard_to_recommendation`: `analyze_strategic_topic` already computed everything the LLM was
re-deriving as prose, so the LLM's version added phrasing and subtracted trust.
- [x] `strategy_to_recommendations(analysis)`: every field derived from verified analysis facts,
      ordered most-specific-first — (1) verified inclusion opportunities (`outreach`/`citation`,
      target = the gated URL, evidence quotes `lists_competitors`), (2) wrong-genre builds
      (`content`, target = the exact intent), (3) gap builds/earns (`content`, target = the top
      uncovered intent, authorities as the benchmark spec; skipped when `sufficient` is False),
      (4) ecosystem `strategy` rec only when community share is "most". Priority/effort/confidence
      are rules (citation volume, gap kind), not model feel. Capped at 3 per topic.
- [x] `build_tab1_recommendations(days)`: same weak-topic selection as Tab 2's builder, opposite
      coverage branch (uncovered intents or wrong-genre covered ones), bounded to 2 topics.
- [x] `generate_recommendations`: deterministic Tab 1 recs **supersede** the LLM's
      content/outreach/citation/strategy recs for the same topic segments (exactly the Tab 2
      pattern), and bypass the judge — nothing in them is unverified. `detail` carries
      `evidence` (+ `genre_mismatch`/`opportunity`), so the existing Tab 1 card renders unchanged.
- Verified live: genre classifiers pass all known cases (QC course page → commercial, QC career
  resource → informational, APDT guide → informational, unread PF blog → informational via URL,
  NYIAD course page → commercial); `build_tab1_recommendations` produced the exact motivating
  rec — QC's grooming course page flagged `have_wrong_genre` (6/8 cited pages informational) →
  "build a standalone how-to/career guide, keep the course page" — plus two gap-build recs with
  truthful domain-count evidence and zero invented inclusion opportunities. Full
  `generate_recommendations` dry run: LLM strategic prose for analyzed topics superseded, other
  segments' LLM recs untouched.
- Follow-up (optional): render `detail.genre_mismatch` / `detail.opportunity` as their own card
  variants in `Recommendations.jsx`; today they display via the shared evidence card.

---

### Coverage matcher fix — question-driven (2026-07-06)
`diagnose_coverage` matched the segment **label** against the sitemap. Bucket labels like
"How to Become" span dog grooming / dog training / dog behavior / event planning — each a
different QC page — so the label matched nothing useful (all stopwords → `unknown`). Fixed:
- [x] Matches the segment's actual **questions** (real intent), per-intent, returning
      `covered` (QC has the page → Tab 2 fix) vs `uncovered` (no page → Tab 1 build).
      Verdicts are now `have_all` / `partial` / `missing_all` / `unknown`.
- [x] Matcher hardened: dropped subject-noun stopwords (the old list stripped "training",
      collapsing "dog trainer" to `{dog}` → matched the grooming page), added stemming
      (trainer/training → train), and IDF weighting so shared tokens ("dog") can't carry a
      false match. `diagnose_text_coverage(text)` gives a binary verdict for one intent string,
      used by `_apply_coverage_diagnosis` to route a rec by its specific target, not its bucket.
- Verified: "professional dog trainer" → dog-training (was: grooming), "dog behavior specialist"
  → dog-behavior, genuinely-absent intents (event decorator, canine care expert) → uncovered;
  well-named "Dog Grooming" still `have_all` (no regression).

## Pre–Phase-4 validation (2026-07-06)

**Two tabs is final** — no third tab. (The earlier "3 segments" idea is dropped.)

**Judge hardening — the original bug is now prevented deterministically.** Stress-testing the
LLM judge with planted fabrications ("APDT lists Penn Foster", "eventbrite ranks Coursera",
"competitors are cited more") showed it caught **0 of 3** — an LLM can't reliably police an
LLM's fabrications. Added `_fabrication_guard()` in `recommendations_synthesis.py`, a
deterministic pre-filter that runs before the LLM judge:
- a page-contents claim ("[page/domain] lists/ranks/names/omits X", matched by *adjacency* so
  an honest "QC ranks below competitors" doesn't trip it) is dropped unless the domain is a
  page_facts-**verified** roundup/directory (`inclusion_opportunity`); QC's own domains are
  exempt (verified separately);
- a comparative claim about competitors with no supporting number is dropped.
- Verified: all 3 planted fabrications dropped 0/3 survive; 2 legit recs survive 3/3; a real
  7-rec generation batch passes with zero false drops.

**Fetch feasibility (gates Phase 4).** Across the mention-topics with enough sample, **3 of 4**
have ≥3 fetchable non-QC pages to compare; ~58% of cited URLs fetch, ~29% block (Penn Foster,
Indeed) and degrade to domain-level classification. Workable, **but the topic universe is tiny
(4 topics)** — the elaborate Tab 2 scorecard would run on ~3 topics. **Recommendation: defer
Phase 4** until the tracked-topic set grows; the citation + coverage recs already serve these
few topics well. Revisit when there are more weak topics with fetchable winners.

## Sequencing
**Phase 1 first** — shippable, truthful, de-risks the rest. Phase 2 (fetching + extraction) is
the real investment and unlocks both smart tabs. Phase 3 makes Tab 1 actions page-aware;
Phases 4–5 deliver the strategist-grade Tab 2 and the UI.
