# Recommendation Evidence Detail — To-Do

Phase B refinement. The generation pipeline produces recommendations whose `evidence`
field is too vague — e.g. *"Competitors' citations and mention rates are higher."* We want
concrete, quotable evidence like *"Coursera is cited from eventbrite.com (5×) and coursera.org
(4×); QC has only 2 third-party citations in this segment."* and a way to tell apart
**"we don't have the page"** from **"we have the page but engines don't cite it."**

Companion to `recommendation-system-phases-bc.md` (Phase B is otherwise DONE) and
`recommendation-page-design.md` (UI). Nothing here blocks Phase C.

---

## Root cause (why evidence is thin today)

The specific data already exists in the bundle — it just never reaches the `evidence` string:

1. `evidence` is free-text the LLM writes, and the generation prompt
   (`recommendations_synthesis.py` `generate_recommendations()`) never requires it to quote
   specific domains/counts → the model paraphrases to a safe, vague summary.
2. The detailed functions aren't scoped to the rec's **segment**: `get_competitor_profile()`
   is global (brand name only, all responses); `get_citation_gaps()` groups by *school*, not
   topic/category. So there's no pre-computed "for THIS query, X is cited and QC isn't."
3. No explicit contrast number (QC's third-party citation count vs the competitor's) is
   computed anywhere, so the model can't quote one.

---

## Fix A — per-segment citation-contrast signal — **do first**

Low risk, no new infra, fixes the immediate complaint on the next generation run.

### A1. New signal `get_citation_contrast(segment, competitor=None, days=None)` — DONE
- [x] Add to `api/queries/recommendation_signals.py`. Scoped to a segment
      (`{dimension, value}`) via a join on `questions.topic` / `question_type` / `school`
      (`_segment_clause_params` helper; also handles engine + `school='General'`).
- [x] Returns:
  - `qc_external_citations`: `[{domain, count}]` — non-QC-owned domains that cite QC here
  - `qc_owned_citations`: `[{domain, count}]` — added so the model can quote "both from
    qceventplanning.com (owned)"
  - `qc_owned_only`: bool — QC cited only from its own domains in this segment
  - `qc_third_party_count`: int — headline "we only have N third-party mentions" number
  - `competitor_citations`: `[{domain, count}]` — domains cited when the competitor appears **in this segment**
  - `domains_citing_rival_not_qc`: `[{domain, count}]` — the actionable gap list
  - Lists are capped (`limit=10`, totals computed pre-cap) to keep the bundle token-bounded.
- [x] Reuse existing building blocks: the domain-extraction regex from
      `get_competitor_profile` + the QC-owned/external `CASE` from `get_top_citation_domains`;
      just add the segment filter.

### A2. Wire into `build_evidence()` — DONE
- [x] For the top 1–2 weak citation segments (mention-kind weakest topics with
      `sample_n >= 5`, leading competitor from momentum), call `get_citation_contrast`
      and add a labeled `## CITATION CONTRAST (per segment)` section to the bundle.

### A3. Tighten the generation prompt — DONE
- [x] Require the `evidence` field to **name specific domains and counts** from the contrast
      section (explicit `evidence:` bullet with a worked example in the generation prompt).
- [x] Judge (`critique_recommendations`) now scores `evidence_grounding <= 2` when the
      evidence makes a comparative claim without quoting a domain/count.

### A4. Verify — DONE (2026-07-03)
- [x] Ran `get_citation_contrast` live against Supabase for the real weakest segment
      (topic "How to Become", competitor Penn Foster): owned+external totals match a
      direct recount (18 = 18); school-dimension and no-competitor calls behave.
- [x] One real end-to-end `generate_recommendations()` dry run (not saved): evidence now
      quotes domains + counts, e.g. *"Engines cite animalbehaviorcollege.com (22x) but QC
      earns only 32 citations from its own domains."* Judge dropped one vague rec.

**Before → After (target):**
> Before: "Competitors' citations and mention rates are higher."
>
> After: "For 'event planning online course', engines cite eventbrite.com (5×),
> coursera.org (4×), thebalancemoney.com (3×) — none cite QC Event Planning. QC earns
> only 2 citations here, both from qceventplanning.com (owned). Zero third-party sites
> vouch for QC in this segment."

---

## Fix B — sitemap coverage diagnosis (create-page vs fix-page) — **Phase B follow-up**

Resolves the "sometimes it's the site structure, sometimes we're missing a page we need"
ambiguity by turning it into a code branch. Key realization: **we do NOT need competitor
sitemaps** — the pages competitors "use that do well" are the exact cited URLs already in our
`citations` data (better than their sitemap: the pages that actually win). Only QC's own
sitemap needs fetching.

### The classification
| QC sitemap has a matching page? | Diagnosis | `action_type` | Recommendation shape |
|---|---|---|---|
| **No** | Content gap — page doesn't exist | `content` | Create the page targeting this query |
| **Yes, but not cited** | Structure/authority — page exists, engines skip it | `technical` | Add FAQPage schema + direct-answer H2 to the existing URL, then pursue third-party links (playbook #3, #1) |

### B1. Fetch + cache QC sitemaps — DONE
- [x] Fetch qccareerschool.com + sub-brand domains (qcpetstudies, qceventplanning,
      qcdesignschool, qcmakeupacademy) sitemaps; slugs are matched from URLs (no per-page
      `<title>` fetch needed). Falls back to `sitemap_index.xml` / `wp-sitemap.xml`
      (qcmakeupacademy is Yoast-style), follows one level of index nesting, and filters
      out asset URLs (cdn.*, images/PDFs) so only real pages count as coverage.
- [x] Cached as `api/knowledge/qc_sitemaps.json` (fetched 2026-07-03: 371 page URLs across
      5 domains); refresh ~monthly with `python -m api.queries.sitemap_coverage`.

### B2. `diagnose_coverage(segment)` — DONE
- [x] Fuzzy-match the segment's topic against QC sitemap slugs (`api/queries/
      sitemap_coverage.py`): stopword-stripped token overlap + difflib per-token fuzz;
      slug-precision tie-break so `/dog-grooming` beats `/download-...-course-catalog`.
      Optional `school` arg restricts matching to that sub-brand's domain.
- [x] Emit `have_page` / `missing_page` + the QC URL when found (`unknown` for non-topic
      segments, all-stopword topics like "How to Become", or a missing cache).

### B3. Integrate — DONE
- [x] Coverage verdict added to each CITATION CONTRAST entry in the evidence bundle, with
      prompt guidance ("never recommend creating a page that coverage shows already exists").
- [x] `_apply_coverage_diagnosis()` in `recommendations_synthesis.py` sets `action_type`
      **deterministically** after generation (missing → `content`, have-but-weak →
      `technical`, and fills `target` with the existing QC URL) for topic-scoped
      content/technical recs — the tension resolved in code, not left to the model.

### Deferred / not doing
- **Competitor sitemap crawling** — noisy (huge sitemaps, mostly irrelevant URLs); the cited
  URLs we already store answer "what's working for them" more precisely. Revisit only if we
  want to preempt topics competitors cover broadly but that haven't surfaced in our data yet.

---

## Sequencing
1. **Fix A** — afternoon-sized, no new infra, fixes the vague-evidence complaint immediately.
2. **Fix B** — larger (sitemap fetch/parse/cache + matching heuristic); it's what makes recs
   correctly diagnose *create-a-page* vs *fix-the-page*.
