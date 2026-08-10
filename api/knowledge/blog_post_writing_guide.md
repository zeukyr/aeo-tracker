LLM‑Optimized Single‑Post Writing Guide
1. Core Principle: Extraction Ease
LLMs cite content that is self-contained, answer-first, and machine-readable.
Every section should be structured so an LLM can lift it cleanly without surrounding context.
Internal editorial standard for content intended to be surfaced, quoted, or cited by AI systems (ChatGPT, Claude, Perplexity, Gemini). This is a house standard, not a citation to external published research — treat specific thresholds (word counts, trim percentages, tier definitions) as working rules to test and adjust, not fixed facts.

2. Structural Elements (Corrected)
A. Answer‑First Writing
Begin each section with a single declarative sentence that directly answers the heading’s question.
This is the strongest predictor of extraction across all engines.

B. Question-Based Headings (H2/H3)
Use headings phrased as real user queries:
What is X?
How does Y work?
Why does Z matter?
This aligns your content with user intent and LLM retrieval patterns.

C. Two Different Block Types (Fixing the Word Count Conflict)
This is the part you flagged — and you were right.
LLM research shows two distinct optimal lengths, each serving a different purpose:
1. Extractable Answer Block (40–60 words)
A short, standalone paragraph immediately under each heading.
Purpose:
Gives LLMs a clean, quotable chunk
Acts as the “answer-first” unit
Mirrors how models chunk text internally
This is NOT the full paragraph.
It is the summary block.
2. Full Paragraph (150–300 words)
Yu et al. found this is the optimal length for LLM citation.
Purpose:
Provides depth
Contains attributable assertions
Offers enough context for models to extract multiple claims
This is the main body paragraph following the extractable block.
So the correct structure is:
Heading (question)
40–60 word extractable answer block
150–300 word full paragraph
Optional comparison table
Optional examples or data
This resolves the inconsistency.

D. Comparison Structure (Elevated to Primary Format)
Comparison framing is treated as the strongest structural predictor of citation in this standard. Use even when the query isn't explicitly comparative:
Include:
“X vs Y” sections
Side-by-side tables
Explicit contrasts
Lists of differences
LLMs prefer discrete, attributable assertions.
E. TL;DR / Key Takeaways
Every post opens (after the title, before the first H2) with a 3-bullet-maximum summary of the piece's core claims. This is a distinct, shorter unit than the extractable answer block — it summarizes the whole post, not one section. Keep each bullet to a single sentence.
F. Bold Takeaway Sentence
End every major section (each H2) with one bolded sentence that restates the section's core claim in a standalone, quotable form. This gives models a second, differently-worded extraction point per section beyond the opening answer block.
G. The "Who, How, Why" Framework
Every post documents, either in a dedicated block or woven into the intro:
Who created this content (author, named contributors)
How it was produced (primary sources consulted, expert input, original research conducted)
Why it exists (what gap or question it addresses that existing content doesn't) This is distinct from the author bio (EEAT, section 4B) — it's about provenance of the content itself, not just the author's credentials.
H. Case Vignettes
Where the topic supports it, include at least one short case example in Challenge → Intervention → Result format. Keep each vignette self-contained (a model should be able to extract it as a unit without needing the rest of the post). Name the entity involved wherever possible (see Section 3A).
I. Rhythm / Cadence Check
Before publishing, scan for repetitive sentence length or structure (e.g., five consecutive sentences all starting with the subject, or all ~12 words long). Vary sentence length deliberately — this is a human-readability and voice-distinctiveness check, not an extractability rule.


3. Technical Elements (Single‑Post Only)
A. Named Entity Requirement
Query-term coverage alone (matching the exact words users search) is necessary but not sufficient. Content must name specific entities, not generic categories:
Geographic locations ("Austin, TX" not "a major city")
Organizations (actual company/institution names)
People (named individuals, not "an expert")
Standards or certifications (e.g., "ISO 27001," "SOC 2 Type II" — not "industry-standard security")
Named entities give LLMs concrete, verifiable nodes to anchor extraction and attribution to; generic phrasing gives them nothing to hold onto.
B. Inline Citation Format Rules
When citing external sources:
Sources must be live hyperlinks, not plain-text references ("according to a 2024 study" with no link is not a citation).
No verbatim quotes longer than 14 words — paraphrase and cite instead.
No single source quoted or cited more than once per post (cite different supporting passages if you need the source twice — don't repeat the same quote).

C. Structured Data
Include: Article schema, FAQPage schema, Person schema (author), Organization schema, sameAs links, accurate dateModified.

4. Content Quality Requirements
A. Originality Levels (Tiered System)
Aim for at least one Tier 1 or 2 element per post; Tier 3–4 elements support but don't replace it.

Tier
Description
Example
1 — Primary original data
Data your organization generated directly
Your own survey, your own product usage data, a benchmark you ran
2 — Original synthesis
Not new data, but a new analysis or framework built from existing public data
A comparison table built from public pricing pages; a framework that combines two known concepts
3 — Aggregated/cited data
Existing third-party stats, properly cited
Citing a published industry report with a live link
4 — Restated common knowledge
Widely known information restated in your own words
Definitions, background context, standard explanations



B. EEAT Compliance
Include:
Author bio
Credentials
Named sources
Transparent methodology
LLMs inherit EEAT preferences from training data.

5. Testing & Validation Criteria
Run every draft through these three checks before publishing:
A. AI Self-Citation Test
Ask: could an AI system already generate this content from its existing training knowledge, without needing to fetch this page? If yes, the piece likely lacks the named entities, Tier 1–2 originality, or specificity needed to be worth citing over the model's own generation. Revise toward more original/specific content.
B. Citation Worthiness Test
Identify the single most citable sentence or data point in the piece — the one thing a model would most plausibly quote or attribute. If you can't identify one, or the best candidate is generic, the post needs a stronger anchor claim (usually a Tier 1–2 data point or a sharply worded comparison).
C. Brand Recall Test
Remove the author name, byline, and any brand mentions from the piece. Is it still identifiable as your organization's voice from tone and framing alone? If not, the piece is undifferentiated — it may perform functionally but won't build brand-specific recall in the way repeated citation is meant to.

6. What to Avoid (New Section)
First-person pronouns ("I think," "in my experience," "we believe")
Promotional or sales language (brand hype, CTAs, "best in class," "industry-leading")
Opinion without evidence
Verbose filler (long intros, storytelling, conversational padding)
Banned phrases / AI filler check — maintain and check against a running list of generic AI-tell phrasing (e.g., "in today's fast-paced world," "it's important to note that," "unlock the power of"). These read as filler to both human readers and, per this standard, to model-side quality heuristics.
The 30% Trim
Before finalizing, cut the draft by roughly 30% by removing: qualifiers ("very," "really," "quite"), passive voice constructions, and redundant paragraphs that restate an already-made point. This is a deliberate compression pass, not a suggestion — run it as a discrete editorial step after the first full draft.
Tone throughout: neutral, objective, informational, evidence-based.

7. Content Mode Assignment
Before drafting, assign each post one mode. Structure and tone rules shift by mode:
Mode
Purpose
Structural emphasis
Informational
Answer a query directly
Heaviest use of Section 2 structure (answer-first, comparison tables); minimal persuasive framing
Editorial
Offer analysis or a point of view on a topic
More room for synthesis (Tier 2 originality) and named case vignettes; still no first-person or unsupported opinion
Commercial
Support a buying decision
Comparison structure is central; must stay evidence-based per Section 6 — commercial intent does not license promotional language

Persona / Audience Targeting
Every post is written to a specific, named persona and a specific buyer-journey stage (e.g., "engineering manager evaluating vendors, early research stage" vs. "developer already shortlisting, technical evaluation stage") — not a generic reader. The persona and journey stage should shape word choice, depth of technical detail, and which comparisons are included.
8. Platform-Specific Optimization
ChatGPT & Claude
Use clean HTML structure
Ensure extractable blocks are clearly separated
FAQPage schema is highly effective
Comparison tables perform exceptionally well
Gemini
Over-indexes on brand-owned properties
Prefers structured data and schema-rich pages
Strong preference for authoritative domains
Perplexity
Uses pre-built indices
Pulls from YouTube, Reddit, retail sites
Video content and community presence matter
Live HTML changes matter less than indexed content
ChatGPT (Discovery Queries)
Injects brand names from training data
Earned media and high-authority mentions matter
Optimize primarily for: ChatGPT
Optimize secondarily for: Perplexity
Optimize passively for: Claude
Do not prioritize: Gemini
Off-Page / Multi-Platform Signals (New)
Data aggregator presence — Wikipedia, Wikidata, and Crunchbase presence materially affects citation eligibility, especially on Perplexity. Treat these as a content-adjacent workstream, not something a single post can fix on its own.
Backlink quality over volume — a small number of mentions in trade press or authoritative outlets outweighs a large number of low-quality links.
Audio/video presence — a YouTube explainer or walkthrough of the same topic is itself a citation-eligible format on Perplexity and should be considered a companion asset, not a nice-to-have.

9. UX Considerations 
The 40–60 word extractable block satisfies LLMs and skimmers.
The 150–300 word full paragraph satisfies depth, nuance, and LLM citation patterns.
This gives you:
human readability
LLM extractability
research-backed citation likelihood


9. Site-Level Factors
These extend beyond any single article but govern whether it can perform:
Topical authority / cluster planning — this post should be planned as part of an interlinked cluster, not published as a standalone piece (see multi-blog strategy doc).
Internal linking rules — every post needs a minimum outbound link count (to related cluster pages) and inbound link count (from the pillar or sibling pages). No orphan pages — a published post with zero internal links pointing to it should be flagged.
Source authority hierarchy — when external sources conflict, resolve using a defined precedence (e.g., primary/regulatory sources > peer-reviewed or trade research > reputable press > aggregator sites). Document which tier a cited source falls into so conflicts are resolved consistently across the team, not ad hoc per writer.
10. Final Single‑Post Checklist
Structure
TL;DR (3 bullets max) at top
Question-based H2/H3
40–60 word extractable answer block per section
150–300 word full paragraph per section
Bold takeaway sentence at end of each major section
Comparison structure included
Who/How/Why documented
Case vignette(s) in Challenge → Intervention → Result format, where applicable
Rhythm/cadence check passed
Sourcing & entities
Named entities used (locations, orgs, people, standards) — not generic references
Query-term coverage confirmed
Inline citations are live hyperlinks
No verbatim quote over 14 words
No source cited twice
At least one Tier 1 or 2 originality element
Source authority hierarchy applied where sources conflict
Validation
AI Self-Citation Test passed
Citation Worthiness Test — most citable sentence identified
Brand Recall Test passed
Editorial
30% trim pass completed
Banned-phrase check passed
No first-person pronouns
No promotional language
Content mode assigned (Informational / Editorial / Commercial)
Persona and buyer-journey stage identified
Structured data & metadata
Article + FAQPage + Person + Organization schema
sameAs links
Accurate dateModified
EEAT elements present (author bio, credentials, methodology)
Site-level
Assigned to a pillar/cluster
Minimum internal link counts met (inbound + outbound)
Not an orphan page

