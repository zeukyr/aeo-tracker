# Deterministic Layer for Sentiment / Credibility / Competitive Recs — TODO

Phase 7 (proposed). Extends the deterministic pattern that made Tab 1/Tab 2
trustworthy to the three rec families still authored as LLM prose (backstopped
only by `_fabrication_guard` + the judge): **concerns, credibility, competitive.**

## The recipe (why Tab 1/Tab 2 work, restated as reusable)
1. **Reduce a noisy signal to a small, stable vocabulary.**
2. **Check QC's owned + cited response against it** (sitemap coverage + page_facts + citation contrast).
3. **Route to a templated action**; the LLM only fills slots.
4. **Score severity deterministically** from columns, not model "feel".

The one new prerequisite these three need that topics didn't: the raw signal is
**free text**, and you can't template off free text.

## Data on hand (verified)
- `sentiment_responses`: `concerns_raised[]`, `positives_raised[]`, `qc_sentiment`,
  `qc_verdict` (**captured on every row, surfaced nowhere today**). Concern +
  verdict + sentiment are the **same row** → tight severity joins.
- `mention_responses`: `citations[]`, brands; competitor wins live here. Linked to
  concerns only via `question_id` (same question, looser join).
- `mention_response_brands`: `brand_name`, `brand_type`.
- Existing signals: `get_recurring_concerns`, `get_qc_verdict_distribution` (unused),
  `get_competitor_wins`, `get_qc_buried_positions`, `get_win_reasons`,
  `get_competitor_profile`, `get_citation_contrast`.

---

## TODO

### [x] 0. Taxonomy normalization — DONE 2026-07-07
Implemented: `api/knowledge/concern_taxonomy.json` (8 types, ordered patterns,
addressable/action_type/reframe/probe per type), `api/knowledge/win_reason_taxonomy.json`
(6 types), `api/queries/signal_taxonomy.py` (rules → LLM fallback → cached in
`signal_classifications.json`). Verified on all real data: 160 concerns → 8 types +
3 "other" (accreditation 49, employer_recognition 46, legitimacy_reviews 20,
practical_hands_on 16, …); hands-on variants collapse to one type. ✔ acceptance.
Free-text concerns/win-reasons can't be templated or measured. Build curated
taxonomies + a classify step (deterministic keyword rules → LLM fallback, cached
per raw string), the `geo_features.json` / page-classification pattern.
- `api/knowledge/concern_taxonomy.json`: e.g. `accreditation`, `cost_value`,
  `practical_hands_on`, `job_outcomes`, `legitimacy_scam`, `support_quality`,
  `recognition_employer`. Each tagged **content-addressable vs structural/factual**.
- `api/knowledge/win_reason_taxonomy.json`: e.g. `more_citations`,
  `stronger_reviews`, `price_transparency`, `accreditation`, `content_depth`.
- `classify_concern(raw)` / `classify_win_reason(raw)`: rules first, LLM fallback,
  cached (own artifact, monthly refresh).
- **Payoff beyond determinism:** stable types unlock the closed-loop diff-in-diff
  (see [[recommendation-system-plan]]) — track whether a concern_type's frequency
  drops after the rec ships; impossible with drifting free-text strings.
- **Acceptance:** real `concerns_raised` bucket into ≤~8 stable types; "limited
  hands-on training" and "not enough practical experience" collapse to one type.

### [x] 0b. QC-owned content index — DONE 2026-07-07
Implemented: `concern_engine.qc_content_index()` — sitemap pages (pet/event/careerschool,
noise slugs excluded) ∪ cited QC URLs from BOTH response tables, fetched/cached via
`page_facts`. Cited blog posts (incl. the cost-of-school post) are in. ✔ acceptance.
The objection check is only as good as our index of QC's OWN content. Today
`page_facts` holds ~57 QC pages, fetched **opportunistically** (only pages that got
cited, or got pulled in as match candidates). An objection rebuttal is usually a
**section buried in a page body**, so we must search QC's *whole* published corpus,
not just the pages that happened to get cited — otherwise the check falsely reports
"missing" and recommends building content QC already has (the grooming-guide
trust failure again).

**There is no blog sitemap** (the Next.js `/sitemap.xml` omits the WP blog and we're
not relying on a Yoast probe). Build the best index we can without one:
- **Index = sitemap pages ∪ every QC URL found in `mention_responses.citations`.**
  The cited-QC set captures the blog posts that matter — they're the ones engines
  already surface (e.g. `/blog/…/how-much-does-dog-grooming-school-cost`, cited 7×,
  directly answers the `cost_value` concern). Fetch + cache text for the union via
  `get_pages_facts` (already guarded/cached).
- **Known blind spot:** a blog post that rebuts a concern but is *neither* in the
  sitemap *nor* ever cited won't be indexed. Mitigation, not elimination:
  phrase every "missing" concern rec as **"publish OR make prominent content
  addressing X"** — never assert "QC has no content on X" — so an unseen buried post
  doesn't make the rec wrong, just less precise.
- **Acceptance:** the union index includes cited QC blog URLs (verify the
  cost-of-school post is present); body search over it can locate an in-page rebuttal.

### [x] 1. Concern objection-response engine — DONE 2026-07-07
Implemented in `api/queries/concern_engine.py`: `concern_severity()` (same-row
sentiment co-occurrence), `analyze_concern()` (probe → body search → semantic
confirm with mandatory quote → citation half → state), `concern_to_recommendation()`
(templated; missing-state honors the taxonomy action_type — legitimacy_reviews
correctly emits a `citation` "earn independent reviews" rec, not content),
`build_concern_recommendations()` (top types, min_count 3, cap 3). Wired into
`generate_recommendations`; the LLM prompt forbids concern-based recs. Verified
live: accreditation (49×, 90% non-positive) → **factual** strategy rec with the
honest "content cannot resolve it" framing; employer_recognition → **missing**
content rec (hedged "publish or make prominent"); legitimacy_reviews → **missing**
citation rec. ✔ acceptance.
A recurring concern is an **objection**. Deterministic question: does QC publish
content answering it, and do engines cite that content when the objection arises?

**The check (four steps)** — reuses `page_facts` bodies + the Item 0b index; slug/
title matching alone won't find a rebuttal because it lives in body text and
concern-language ≠ marketing-language ("limited hands-on" vs "practicum with real
dogs"):
1. **Concern → probe.** Each `concern_type` carries a probe in the taxonomy artifact:
   the objection as a question + a keyword set (`practical_hands_on` → "does QC offer
   hands-on/in-person training?" + `{hands-on, practicum, in-person, real dogs}`).
2. **Candidate QC pages by BODY text.** Search `content_excerpt` + `headings` across
   the Item 0b index for the keyword set → shortlist. (Not slug/title.)
3. **Semantic confirm.** One LLM pass per candidate (the Tab 2 `_semantic_features`
   pattern): "does this page rebut the objection? yes/no + **quote**". The quote
   requirement enforces the Tier-B no-claim-without-a-fetched-fact rule.
4. **Citation half → which state.** Concerns are raised on specific sentiment-response
   `question_id`s; check whether a confirmed rebuttal page appears in `citations` on
   those same questions.

Three computable states:
- **No QC content confirms it** → `content`: publish/surface content answering it.
- **Confirmed rebuttal exists but isn't cited on the concern-questions** →
  `technical`/`citation`: surface/strengthen the existing rebuttal.
- **Concern is factual/structural** (taxonomy tag) → **no GEO rec**; flag as a
  business insight or reframe (cost → "publish transparent value content";
  accreditation → do NOT pretend content fixes it). **Highest-value guardrail** —
  stops "add FAQ schema to fix the not-accredited concern".

**Design calls:**
- **Bias when unsure → assume QC DOES cover it.** Missing a real gap is cheaper than
  telling someone to write a page they already have (the fastest trust-eroder). This
  mirrors the Tab 2 "QC-side precision > winner-side" rule.
- **Section retrieval on long pages.** We store a 4k-char excerpt; on a 3k-word page
  the relevant section can fall outside it. Either widen the excerpt or retrieve the
  heading/paragraph matching the concern keywords before the semantic pass.

**Severity (deterministic):** `GROUP BY concern_type` × fraction co-occurring with
negative `qc_verdict`/`qc_sentiment` on the same row → priority number, not feel.

`analyze_concern(concern_type)` → state + evidence; `concern_to_recommendation()`
templates the rec (mirror of `scorecard_to_recommendation`); supersede the LLM's
concern rec for that concern_type in `generate_recommendations`.
- **Acceptance:** a factual concern produces no content rec (or a flagged insight);
  a content-addressable one with no confirmed rebuttal produces a targeted rec naming
  the concern (phrased "publish OR surface", per the blind-spot mitigation);
  guard/judge no longer the only backstop for concern recs.

### [x] 2. Credibility layer — DONE 2026-07-07 (keyed on `qc_sentiment`, not verdict)
Design amendment discovered in the data: `qc_verdict` is **free text**, not an enum —
so the deterministic spine is the `qc_sentiment` enum on the same row;
`qc_verdict` is used only as verbatim quotable evidence. Implemented in
`api/queries/credibility.py`: `analyze_credibility()` (distribution + external
domains cited on positive vs non-positive rows — same-row, since sentiment_responses
carry their own citations) and `credibility_to_recommendation()` (fires only at
n≥20 and non-positive share ≥0.5; community-dominated negatives → ecosystem
template, else → strengthen the specific positive-correlated domains). Verified
live: 78 rows, 67% non-positive, community sources dominate → community-presence
strategy rec with real counts + verdict quote. ✔ acceptance.
Credibility recs = citation-contrast **keyed on verdict** instead of mention_rate.
Wire the unused column in; no bespoke engine.
- Surface `get_qc_verdict_distribution` into the evidence bundle.
- **What backs each verdict:** citations present when verdict is positive vs
  negative (same contrast machinery). Positive ⇢ accreditation/review sites →
  earn/strengthen those (`citation`/`outreach`). Negative ⇢ Reddit/scam threads →
  **reuse the Tab 1 ecosystem template** (authentic community presence, no
  manufactured posts).
- **Acceptance:** a weak verdict distribution yields a rec targeting the specific
  authority domains that correlate with positive verdicts, or a community-presence
  rec pointed at where negatives originate — not generic "improve credibility".

### [x] 3. Competitive as priority/routing — DONE 2026-07-07
Implemented: `get_competitive_loss_topics()` in recommendation_signals;
`_apply_competitive_boost()` in synthesis (topic rec in a loss topic → priority
bumped one level + loss count/competitors appended to evidence);
`build_tab1_recommendations` enriches gap-build recs with the lead rival's
`domains_citing_rival_not_qc` (citation targets in evidence + `detail.rival_backed_domains`);
prompt forbids standalone "competitor beats QC" / generic "improve credibility" recs.
✔ acceptance (full dry run: no standalone competitive cards).
Argue AGAINST a parallel competitive rec generator — "Penn Foster beats you on X"
is only actionable as "build/fix the QC page for X", which is already Tab 1/Tab 2.
- **Routing:** competitor win on topic X → `diagnose_coverage` → Tab 1 build or
  Tab 2 scorecard. Competitive intel is a *source of weak topics*, not an output.
- **Priority boost (deterministic):** weak segment AND competitive loss → computed
  multiplier on that topic's existing rec (the plan's "compounding evidence" rule),
  not a new card.
- **Target enrichment:** `get_competitor_profile` domains → feed into the Tab 1
  rec's citation/outreach *targets* ("earn citations on these domains that vouch
  for the rival but not QC"). Link via `question_id` (looser than same-row).
- **Acceptance:** no standalone "competitor wins" cards; competitive signals show
  up as boosted priority + concrete citation targets on topic recs.

---

## Sequencing
0 (taxonomy) → 0b (QC content index — required before 1) → 1 (concerns, biggest
quality win) → 2 (credibility plumbing) → 3 (fold competitive in / delete the weak
family). End state: every rec family shares one shape — normalized signal →
owned+cited check → templated action → deterministic severity — and the LLM's role
everywhere is phrasing over a locked skeleton.

**No blog sitemap** — the QC content index (0b) is `sitemap ∪ cited-QC-URLs`, which
covers the blog posts engines actually surface; buried-and-uncited posts are an
accepted blind spot, hedged by phrasing missing-concern recs as "publish OR surface".

## Related
- [[recommendation-system-plan]] — closed-loop engine; taxonomy types are what the
  diff-in-diff measures.
- `recommendation-two-tab-plan.md` Phase 4/6 — the `*_to_recommendation` +
  supersede pattern these mirror.
- `recommendation-accuracy-todo.md` — items 1–3 (content-aware matching,
  bucket-scope filter, cross-metric guard), done 2026-07-07.
