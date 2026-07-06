# GEO Playbook (Generative Engine Optimization)

Reference tactics for improving visibility in AI-generated answers (ChatGPT, Perplexity,
Gemini, etc.), as distinct from classic search-engine SEO. Generative engines answer by
synthesizing across sources they've crawled and trust - they don't rank a list of links,
they pick *facts and names to mention*. Optimizing for that means optimizing for citation,
not for click-through.

Each tactic below is tagged with the metric(s) it primarily moves, using the same names as
the dashboard: `mention_rate`, `citation_rate`, `sov` (share of voice), `avg_rank` (mention
order), `positive_sentiment_rate`, `visibility_score`. Use these tags when filling a
recommendation's `metric_impact` field - don't invent a mechanism that isn't below without
strong evidence for it.

---

## 1. Third-party citation density
**Moves:** `mention_rate`, `sov`
Generative engines mention brands that appear across many independent sources, not just
the brand's own site. A page on qccareerschool.com saying "we're accredited" carries far
less weight than five unrelated sites (review aggregators, industry blogs, forums) saying
the same thing. **Action shape:** pursue placement on third-party sites that already rank
for the target question, rather than only publishing more owned content.

## 2. "Best of" / comparison listicles
**Moves:** `mention_rate`, `sov`, `avg_rank`
Listicle and comparison pages ("Best online pet grooming schools 2026", "X vs Y") are
disproportionately cited by generative engines because they already contain the
compare/contrast structure the engine is trying to reproduce. Getting included in an
existing listicle (or getting a new one created/updated) directly seeds future answers.
**Action shape:** outreach to sites already ranking for "best [category] schools" /
"[competitor] vs [competitor]" to request inclusion or updated comparison.

## 3. Structured Q&A / FAQ content with schema markup
**Moves:** `citation_rate`, `mention_rate`
Content that mirrors the question-answer shape (explicit question as a heading, direct
answer in the first sentence, FAQPage schema markup) is easier for engines to lift
verbatim as a citable fact. Vague marketing copy without a clear claim-to-cite is passed
over. **Action shape:** publish/rewrite a page that directly answers the exact prompt
wording seen in the tracker's weak questions (e.g. "Is a QC Pet Studies certificate
respected by employers?" as an literal H2 with a direct-answer paragraph beneath it).

## 4. Wikipedia / Wikidata presence
**Moves:** `mention_rate`, `citation_rate`
Wikipedia and Wikidata are among the most heavily weighted sources for most generative
engines' training and retrieval. A well-sourced Wikipedia entry (or corrected/expanded
existing entry) for the school or its accreditation status has outsized effect relative to
its cost. **Action shape:** only pursue if verifiable, independent secondary sources exist
to cite - Wikipedia will reject unsourced promotional edits, and a rejected edit wastes
effort here.

## 5. Community / forum presence (Reddit, Quora)
**Moves:** `mention_rate`, `positive_sentiment_rate`
Engines increasingly cite Reddit/Quora threads directly, especially for "is X worth it" /
"is X legit" style questions - exactly the shape of this tracker's `credibility` and
`competition` categories. Genuine, disclosed participation (alumni answering honestly, not
astroturfing) in existing threads about QC schools shifts what the engine finds when it
looks for real-world opinion. **Action shape:** identify existing Reddit/Quora threads
already surfaced in `citation_gaps`/`citation_domains` evidence and contribute genuine,
disclosed responses; do not fabricate reviews.

## 6. Primary-source authority for a specific claim
**Moves:** `citation_rate`, `avg_rank`
When a page is the *original* source of a specific, checkable fact (an accreditation
status, a graduate outcome statistic, a tuition figure), engines prefer citing it directly
over a secondary summary. Vague claims get paraphrased without attribution; specific,
checkable claims get cited. **Action shape:** publish granular, specific facts (exact
accreditation body names, specific outcome numbers) rather than general "quality
education" language.

## 7. Freshness and recrawl signals
**Moves:** all metrics (baseline lift takes longer to materialize)
Generative engines' knowledge lags their training/retrieval cutoff; a page that hasn't
changed in years is less likely to be freshly indexed. Updating dates, adding current-year
references, and republishing with a changed timestamp increases the odds of a page being
recrawled and considered current. **Action shape:** treat this as a supporting tactic, not
a standalone recommendation - pair it with a substantive content change (tactics 1-6), not
just a date bump.

## 8. Consistent NAP/brand facts across sources
**Moves:** `positive_sentiment_rate`, `citation_rate`
Contradictory facts about the same brand across sources (different accreditation claims,
different names for the same program) create uncertainty that shows up as hedging in
generated answers ("it's not entirely clear whether..."). Resolving contradictions across
owned and third-party pages reduces hedged/neutral answers. **Action shape:** use when
`qc_verdict` text or `concerns_raised` shows confusion/contradiction, not just criticism.

---

## Timing note for recommendations
GEO tactics above are content/outreach actions on external and semi-external surfaces;
they depend on the target site being crawled/re-indexed by the AI engine's retrieval
pipeline, which lags real-world publication by roughly 2-4 weeks in practice. Recommend
measuring impact no sooner than that lag after `implemented_at`.
