# Recommendation Accuracy — Follow-up TODO

Post–Phase-6 work items from the 2026-07-07 diagnosis. Sequenced to **improve
existing pages (Tab 2) first**; the sitemap-completeness fix is deferred because
it mostly affects Tab 1 missing-page verdicts, not page improvement.

## Diagnosis recap (what's actually broken)

Traced live against real data:

1. **Slug matching has hit its ceiling.** "how to become a certified/professional
   dog groomer" reduces to tokens `{dog, groom}` (become/professional/certified/how
   are stopwords; "rm" is under the 3-char floor). Three QC pages tie at
   cov=1.00 — `/certification-courses/dog-grooming`, `/certification-courses/rm/
   become-a-professional-dog-groomer`, `/videos/dog-grooming` — broken only by
   iteration order. **The genuinely correct page, `/grooming-career-guide`
   (title: "How to Become a Professional Dog Groomer"), loses** because "guide"
   is a stopword and its slug lacks "dog". The distinguishing signal lives in
   page **titles/headings/genre** we already fetch — not in the slug.

2. **Genre false positive downstream of #1.** Yesterday's "build a how-to career
   guide for dog grooming" rec was wrong — QC already has that page
   (`/grooming-career-guide`). The genre layer worked; the matcher fed it the
   wrong QC page to compare against.

3. **Category-segment recs are unactionable.** The rec the user flagged
   ("Low citation rate … general course visibility", cross-metric nonsense
   "mention rate 3.9 vs citation rate 14.8") is scoped to
   `{dimension: category, value: "general"}`. "general" spans 29 of 58 questions
   (How to Become, Starting a Business, Career Exploration, Course Discovery).
   Every deterministic mechanism (coverage, genre, templated recs) only fires on
   **topic**-dimension segments; category/school/engine segments are still 100%
   LLM prose, so they slip through the guard/judge whenever they contain a number.

4. **(Deferred) Sitemap is blind to the blog.** Engines' top QC citations are all
   `/blog/…` posts, but the sitemap cache has **zero** blog URLs across all five
   domains — the Next.js `/sitemap.xml` omits the WordPress blog, whose Yoast
   sitemap lives at `/blog/sitemap_index.xml` (confirmed 200). Coverage therefore
   reports "missing page" for intents the blog already answers.

---

## TODO

### [x] 1. Content-aware page matching (do first) — Tab 2 accuracy — DONE 2026-07-07
Keep slug matching as a cheap **candidate filter** (top-K QC pages by IDF token
coverage), then **rerank candidates by fetched title + headings + genre** via
`page_facts`, not by slug alone.
- Titles alone fix the motivating case: `/grooming-career-guide` titled "How to
  Become a Professional Dog Groomer" matches the intent verbatim; the course
  lander does not.
- Only QC pages that are already candidates get fetched (bounded); cache per URL
  in `page_facts`, monthly refresh like the rest.
- Break the current exact-tie problem: prefer the page whose title/headings best
  match the intent, then genre-appropriate, then cleanest slug (existing
  precision tie-break stays as the final tiebreaker).
- **Acceptance:** for "how to become a professional dog groomer", matcher returns
  `/grooming-career-guide` (informational) — not `/certification-courses/dog-grooming`
  or the `/rm/` lander — and the genre layer stops firing a false "build a guide"
  rec for it.
- **Implemented** (`sitemap_coverage.py`): `_scored_pages` → candidates ≥0.35 slug cov
  (max 15) → `page_facts` fetch (cached) → `_title_score` rerank, informational-genre
  tie-break, ≥0.5 title floor to override slugs; verdict score = max(slug, title).
  Two extra defects found & fixed during verification:
  - **Subject guard:** a title only scores if it covers ALL the intent's subject
    tokens — otherwise "Become a Professional Dog Groomer" (the `/rm/` lander)
    out-ranked the dog-training page for the *trainer* intent on function words alone.
  - **Noise slugs:** `/NNN-off` promo clones, `/get-a-*` lead-gen funnels,
    `course-preview`/`course-outline`/`assignments`, `/videos/`, email-preferences,
    thank-you pages excluded from coverage candidates (`_NOISE_SLUG`).
  - Verified: acceptance case passes; trainer → `/certification-courses/dog-training`
    (true-positive genre mismatch — a training career guide genuinely doesn't exist);
    behavior/decorator regressions hold; grooming false positive gone from
    `build_tab1_recommendations`.

### [x] 2. Scope recs to actionable intents, not buckets — DONE 2026-07-07
Category/school/engine buckets should be **diagnostic rollups, not rec scopes.**
- Category/school weakness stays as *context* in the evidence bundle, but a rec
  must be scoped to a topic/intent the deterministic pipeline can serve (has a
  target page or a build target).
- Drop or down-rank LLM recs whose `segment.dimension` is `category`/`engine`/
  `school` and that carry no concrete page/intent target — or re-scope them to a
  specific weak intent inside the bucket.
- **Acceptance:** the "general course visibility" rec no longer generates; a run
  produces no rec whose only target is a bucket label.
- **Implemented** (`recommendations_synthesis.py`): `_is_actionable()` — a
  content/technical rec on a category/engine/school/global segment is dropped unless
  its target is a concrete URL; citation/outreach/strategy may stay bucket-scoped.
  Generation prompt updated with the same rule. Verified on the flagged rec shape
  (dropped) + three keep-cases (topic build, bucket+URL, ecosystem strategy).

### [x] 3. Guard the cross-metric nonsense claim — DONE 2026-07-07
The flagged rec compares "mention rate 3.9" to "citation rate 14.8" — two
different metrics — and passes because it contains numbers.
- Add a check (extend `_fabrication_guard` or the judge criteria) that flags a
  comparative claim juxtaposing two *different* metric names as if comparable.
- **Acceptance:** planted "mention rate X vs citation rate Y" claim is dropped;
  legitimate single-metric evidence survives.
- **Implemented** (`_fabrication_guard`): `_CROSS_METRIC` regex — two *different*
  metric terms joined by an explicit comparator ("compared to/with", "versus",
  "vs", "relative to", "against") within one sentence → drop. Gap pattern admits
  decimals ("3.9") without crossing sentence boundaries. Same-metric comparisons
  and comparator-free juxtaposition ("mention rate 40%, citation rate 5%" — the
  legit mentioned-but-not-cited insight) survive. All three guard tests pass.

### [ ] 4. (DEFERRED) Sitemap completeness — Tab 1 missing-page accuracy
Not blocking page improvement; revisit after 1–3.
- In `sitemap_coverage._fetch_sitemap_urls`, also probe `/blog/sitemap_index.xml`
  (Yoast) per domain and merge; the root `sitemap_index.xml` 404s, so add
  `/blog/sitemap_index.xml` to `_KNOWN_SITEMAP_URLS` or the probe list.
- Refresh the cache (`python -m api.queries.sitemap_coverage`).
- **Acceptance:** `/blog/…` URLs appear in the cache; coverage stops reporting
  "missing page" for blog-answered intents (e.g. "how much does dog grooming
  school cost" → `/blog/2021/05/how-much-does-dog-grooming-school-cost`).

---

## Notes
- Items 1–2 are the ones that would have prevented both bad recs the user saw.
- Genre layer (Phase 6) is correct as built; it's only as good as the QC page the
  matcher hands it — which is exactly what item 1 fixes.
