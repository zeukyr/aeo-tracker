Master Writing Instructions: AEO-Optimized, Human-Sounding Blog Posts
This document merges two previously separate guides into one instruction set for a single generation pass:
The LLM-Optimized Single-Post Writing Guide (structure, extractability, citation mechanics)
The Natural, Human-Sounding Prose guide (tone, word choice, avoiding AI-writing tells)
They are not run as two sequential rewrites. They are applied together, in one draft, under one governing rule.
0. The Governing Rule
Structure is load-bearing. Voice is a finish.
Every numeric requirement, structural element, and sourcing rule in Section 1 below is non-negotiable and must be satisfied in the draft as written — not approximated, not satisfied "in spirit." Every rule in Section 2 governs how those required elements are worded — sentence rhythm, word choice, avoiding AI-tell patterns — but never whether they exist or how long they run.
Concretely:
If a section's full paragraph needs to land at 150–300 words to satisfy Section 1, and the "30% trim" or "vary sentence rhythm" instructions in Section 2 would pull it under 150, the word count wins. Trim by tightening word choice and cutting redundancy, not by deleting content the structure requires.
If a bolded takeaway sentence at the end of a section reads like "excessive bolding" in isolation, it stays. That bolding is a required, deliberate, single-instance-per-section pattern, not the random mid-paragraph bolding the human-voice guide is warning against.
If a bulleted checklist is structurally useful (a comparison, a list of things to check before enrolling), it stays as bullets even though the human-voice guide generally prefers prose. Bullets are for genuinely parallel, scannable items either way — the two guides agree here.
A named statistic, named entity, or named source from Section 1 is never softened, rounded, or genericized during a voice pass. Rephrase the sentence around the number for tone. Never touch the number itself.
When in doubt: draft to satisfy Section 1 first, then read it back and adjust only wording, rhythm, and word choice per Section 2. Do not delete or shorten a required element to make it "sound more natural" — if a required element genuinely can't be made to sound natural, that's a structure-vs-voice conflict to flag explicitly, not something to resolve by quietly dropping the structure.
1. Structural and Sourcing Requirements (Non-Negotiable)
1.1 Before Drafting
Assign one content mode: Informational (answer a query directly, heaviest structural emphasis, minimal persuasive framing), Editorial (analysis/point of view, room for synthesis and named vignettes, still no first-person or unsupported opinion), or Commercial (support a buying decision, comparison-central, evidence-based — commercial intent does not license promotional language).
Identify a specific, named persona and buyer-journey stage (e.g., "career-changer evaluating training options, early research stage"), not a generic reader. This shapes word choice, technical depth, and which comparisons to include — it should shape the draft, not appear as a label inside the draft.
Confirm pillar/cluster placement: this post should be part of an interlinked cluster with internal links in and out where the site structure supports it, and should not be an orphan page.
1.2 Required Structure, Per Section
Each major section (H2) needs, in order:
A question-based heading ("What is X?", "How does Y work?", "Why does Z matter?").
A 40–60 word extractable answer block: a short, standalone paragraph immediately under the heading that directly answers the heading's question in one declarative unit — a clean, quotable chunk, not the full explanation.
A 150–300 word full paragraph: the depth paragraph following the answer block, containing attributable assertions and enough context to support multiple extractable claims.
Optional: a comparison table, example, or supporting data.
A bolded takeaway sentence at the end of the section, restating its core claim in a standalone, quotable form, worded differently from the opening answer block.
At the post level, also include:
A TL;DR (3 bullets maximum, single sentence each) after the title, before the first H2.
A Who/How/Why block, either dedicated or woven into the intro: who created the content, how it was produced (named sources, original data, methodology), and why it exists (what gap it fills that generic advice doesn't).
At least one comparison structure (X vs. Y section, side-by-side table, or explicit contrast list) — use even if the topic isn't explicitly comparative, since comparison framing is the strongest predictor of citation.
At least one case vignette in Challenge → Intervention → Result format where the topic supports it, self-contained enough to be extracted as a standalone unit, with a named entity wherever possible. If the vignette is a composite or hypothetical rather than one verified case, label it as such plainly and keep any illustrative details generic enough that nothing could be mistaken for a verified fact.
An FAQ section near the end (supports FAQPage schema).
1.3 Named Entities and Sourcing
Name specific entities, not generic categories: real geographic locations, actual organization names, named individuals (not "an expert"), named standards or certifications. Generic phrasing gives a model nothing to anchor extraction to.
Do not invent a specific-sounding entity or detail to fill this requirement. If a location, name, or number isn't real or isn't confirmed, either use a genuinely generic placeholder and label it as illustrative, or omit it.
External citations must be live hyperlinks, not plain-text references. No verbatim quote over 14 words — paraphrase and cite instead. No single source cited more than once with the same quote.
Include at least one Tier 1 (primary original data your organization generated) or Tier 2 (original synthesis of existing public data) element per post. Tier 3 (cited third-party stats) and Tier 4 (restated common knowledge) can support but not replace this.
Where sources conflict, resolve by a defined precedence (primary/regulatory > peer-reviewed/trade research > reputable press > aggregator sites), and note which tier a source falls into.
1.4 Using Provided Input Data (Personas, Surveys, Testimonials)
When persona documents, demographic surveys, transcripts, or testimonials are supplied as input for a piece:
Personas shape the draft; they don't appear in it. Use persona and demographic detail to decide word choice, technical depth, which fears or objections to address, and which comparisons to include. Never surface a persona's internal label (e.g., "The Aspiring Entrepreneur," "Career-Changing Professional") in the visible text — write to that reader without naming the segment.
Survey and demographic stats are Tier 1 originality material by default. Cite the organization's own numbers as first-party data: use the specific figure exactly as given, attribute it by name to the source (e.g., "QC Event School's enrollment data shows..."), and weave it into a sentence rather than dropping it as an isolated statistic. Do not round, generalize, or soften a specific figure into a vague claim ("most people," "the majority") during any later editing pass — this is the same rule as Section 2.3's ban on vague attribution, applied specifically to first-party data.
Never invent a statistic to fill a gap. If a point would benefit from a number but no supplied data covers it, either state the point without a number or note that the data isn't available. Do not extrapolate, estimate, or fabricate a precise-sounding figure that isn't in the source material.
Paraphrase testimonials and quotes with attribution rather than block-quoting them, unless they're short enough to use verbatim. Check any supplied quote against the 14-word limit (Section 1.3) before using it directly; if it runs longer, paraphrase it in indirect speech and attribute it to the person's real name.
Distribute supplied data points across the sections where they're most relevant (e.g., learning-style data in a section about curriculum design, timeline data in a section about pacing) rather than stacking all of them into the intro or TL;DR.
If supplied first-party data conflicts with a general industry claim, prefer the named first-party data, and mention the general claim only if it adds real context, following the source authority hierarchy in Section 1.3.
1.5 Validation, Run Against the Finished Draft
AI Self-Citation Test: could an AI system already generate this content from training knowledge alone, without this page? If yes, the piece needs more named entities, Tier 1–2 originality, or specificity.
Citation Worthiness Test: identify the single most citable sentence or data point. If nothing stands out, or the best candidate is generic, add a stronger anchor claim.
Brand Recall Test: with the author name, byline, and brand mentions removed, is the piece still identifiable as this organization's voice from tone and framing alone?
Structured data present where applicable: Article, FAQPage, Person, Organization schema; sameAs links; accurate dateModified; author bio, credentials, and methodology visible (EEAT).
2. Voice and Tone Layer (Applied Inside the Structure Above)
Everything below governs wording, not whether a required element exists.
2.1 Word and Phrase Choices
Cut or replace unless it's the only accurate term for the context: delve, boast/boasts, showcase, underscore, testament (to), tapestry, vibrant, bustling, robust, seamless, leverage, foster, navigate (metaphorically), realm, landscape (metaphorically), journey (metaphorically), unlock, elevate, game-changer, cutting-edge, in today's world/fast-paced world, holistic, plethora, myriad, key/crucial/vital (as filler intensifiers), notable/notably, comprehensive, multifaceted, intricate, meticulous, poignant, profound, rich cultural heritage, stunning natural beauty, breathtaking.
Cut filler transitions that aren't doing real logical work: moreover, furthermore, additionally, in conclusion, overall, in summary, it's important to note that, in order to (→ "to"), at this point in time (→ "now"), due to the fact that (→ "because"). Also maintain and check against a running list of generic AI-tell filler phrases (e.g., "unlock the power of").
Prefer plain, specific verbs and nouns over abstract ones.
2.2 Sentence and Paragraph Craft
Avoid the "rule of three" list habit (reflexively grouping descriptors or examples in sets of three). Vary the count.
Avoid false ranges ("ranging from X to Y") unless the endpoints are genuinely representative.
Avoid "not just X, it's Y" / "not only X but also Y" as a rhetorical crutch, and avoid disguised variants that swap the grammar but keep the same mirror-sentence shape (e.g., "It closes X. It doesn't close Y."). If two consecutive sentences are mirror images of each other, rewrite one into a plain statement.
Drop superficial -ing clauses tacked on for unearned significance ("...cementing its place in history").
Avoid editorializing through unsupported adjectives ("iconic," "renowned," "historic") — state the fact that would justify the label instead of the label.
Avoid a predictable bookend structure where the intro restates the question and a closing paragraph just repeats the intro. (Note: the required TL;DR and section takeaways are not this — they're structural extraction units, not restatement padding.)
Avoid a formulaic "Challenges and Future Outlook" or "In conclusion" section with no real, specific content in it.
Vary sentence rhythm deliberately — this is the same check as the AEO guide's Rhythm/Cadence Check in Section 1.2; it is one check, not two.
2.3 Sourcing and Attribution (Voice Layer)
No vague, unnamed attributions ("experts say," "studies show"). This reinforces, and does not relax, the named-entity requirement in Section 1.3.
No fabricated precision: no fake statistics, invented quotes, or unverifiable citations. If uncertain, say so plainly.
No fabricated specificity in illustrative examples either — an invented but plausible-sounding city, venue, or case name is the same problem as a fake statistic, just smaller. Keep hypothetical or composite examples generic enough that nothing could be mistaken for a verified fact, and label them as illustrative (see Section 1.2's vignette rule).
Don't hedge everything equally — reserve hedges for genuine uncertainty; state known facts plainly.
No first-person plural as a stand-in for a named source ("patterns we see a lot," "we believe"). This also serves the "no first-person pronouns" rule below.
No first-person pronouns anywhere in the piece ("I think," "in my experience," "we believe"), regardless of content mode.
No promotional or sales language (brand hype, CTAs, "best-in-class," "industry-leading"). A Commercial-mode post stays evidence-based; naming a company's own program, curriculum, or data as a Tier 1 source is not promotional language, but describing it with unsupported superlatives is.
No opinion presented without evidence.
2.4 Formatting Tells
Avoid excessive bolding of random key nouns. The one required bolded takeaway per section (Section 1.2) is the exception, not a violation.
No emoji as section headers or bullet markers.
No Title Case applied to ordinary common nouns or phrases that aren't proper nouns or actual titles.
Treat one or two em dashes per piece as a hard ceiling, not a target. Default to a comma, colon, period, or parentheses first. Sweep the finished draft specifically for em dashes before calling it done — they tend to creep in silently across edits.
Avoid excessive bullet-pointing of things that would read more naturally as prose. Reserve bullets for genuinely parallel, scannable items (a checklist, a comparison), which is also where the AEO guide wants them (Section 1.2).
2.5 Assistant Artifacts to Strip Out
No sign-offs, disclaimers, "I hope this helps," references to being an AI or having limitations (unless the content specifically requires a citation caveat), meta-commentary about the writing process ("In this section, we will explore..."), or knowledge-cutoff caveats bolted onto unrelated content.
2.6 House Voice Calibration
When a house style sample is available (existing brand blog posts), calibrate tone to match it: direct second-person address, conversational hooks, contractions, scannable checklists where the sample uses them. This is a tone-and-word-choice adjustment made inside the structure in Section 1 — it does not change which structural elements are required or how long they run.
3. Verification Order (Do Not Skip or Reorder)
Run these checks against the finished single draft, in this order:
Pass 1 — Structure (Section 1), objective and countable:
[ ] TL;DR present, 3 bullets max, single sentence each
[ ] Every H2 is question-phrased
[ ] Every section's extractable answer block is 40–60 words
[ ] Every section's full paragraph is 150–300 words
[ ] Every section ends with a bolded takeaway sentence
[ ] At least one comparison structure present
[ ] Who/How/Why present (dedicated or woven into intro)
[ ] At least one case vignette in Challenge → Intervention → Result format, labeled as illustrative if composite
[ ] Named entities used throughout, not generic references
[ ] At least one Tier 1 or 2 originality element present, and its factual content (numbers, names) unaltered
[ ] Inline citations, if any, are live hyperlinks; no quote over 14 words; no source double-cited
[ ] FAQ section present
[ ] Content mode and persona were used to shape the draft (check word choice/depth match, not a visible label)
[ ] No persona segment name or internal label appears anywhere in the visible text
[ ] Every stat pulled from supplied survey/demographic data appears with its exact original value and named source, not paraphrased into a rounder or vaguer number
[ ] Any supplied testimonial or quote is either verbatim and under 14 words, or paraphrased with the person's real name attached
Pass 2 — Voice (Section 2), applied without breaking Pass 1:
[ ] No word from the cut/replace list without specific reason
[ ] No rule-of-three, false range, "not just X it's Y," or disguised mirror-sentence construction
[ ] No vague unnamed attribution or unattributed "we"
[ ] No first-person pronouns anywhere
[ ] No fabricated specificity in any example
[ ] Sentence rhythm varied, not uniform
[ ] No bookend restatement paragraph
[ ] Em dash count at or under two for the whole piece
[ ] No emoji headers, no excessive random bolding, no title-cased common nouns
[ ] No assistant sign-offs or meta-commentary
[ ] No promotional language
Pass 3 — Reconciliation check (the step most likely to be skipped):
[ ] Re-run the word counts from Pass 1 after any Pass 2 edits. If a voice edit pulled a paragraph under 150 words or an answer block outside 40–60, restore length by adding substantive detail (a specific mechanism, a comparison point, a consequence) — not filler.
[ ] Confirm every named statistic and named entity from Pass 1 still appears with its original specific value, not softened into a general claim.
[ ] Confirm no persona label from the supplied input document was reintroduced or left in during editing.
[ ] Confirm the bolded takeaway sentences are still present — a voice pass focused on "reduce bolding" is the most common way these get accidentally deleted.
If Pass 3 finds a conflict that can't be resolved by wording alone (for example, a required element that genuinely cannot be phrased naturally), flag it explicitly rather than silently resolving it in either direction.


