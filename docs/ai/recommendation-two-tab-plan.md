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

### Phase 4 — Tab 2 scorecard + emergent pass
- [ ] For each weak `have_page` topic: rank cited URLs, take top-N fetchable non-QC winners.
- [ ] Detect features across winners + the QC page (hybrid). Build the scored table.
- [ ] Layer 2 emergent-pattern LLM call.
- [ ] Generate section-level recs from the scored gaps; judge enforces each claim traces to
      a `page_facts` fact.

### Phase 5 — Frontend build-out
- [ ] Tab 1 card: Why / Evidence / Action (action shaped by page type), + ecosystem-pattern cards.
- [ ] Tab 2 card: Page / compared-against / scorecard table / emergent insight / suggested edits.
- [ ] Keep the health summary as a shared header above the tabs.

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

## Open question
- Earlier "3 segments" vs. the settled 2-tab model — treating the health summary as a shared
  header, not a third tab. Revisit if a third stream (e.g. measurement/quick-wins) is wanted.

## Sequencing
**Phase 1 first** — shippable, truthful, de-risks the rest. Phase 2 (fetching + extraction) is
the real investment and unlocks both smart tabs. Phase 3 makes Tab 1 actions page-aware;
Phases 4–5 deliver the strategist-grade Tab 2 and the UI.
