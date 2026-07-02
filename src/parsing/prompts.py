"""
prompts.py

Prompt templates only. No logic, no API calls — just the text sent to the
LLM. Keeping this separate makes prompt tweaks a one-file diff, and keeps
llm_client.py focused on the actual call/error-handling mechanics.
"""

COMPETITOR_CONTEXT = """
You are analyzing an AI engine response to the question: "{question}"
Response: "{response}"
Citations: {citations}

QC (QC Career School, QC Makeup Academy, QC Design School, QC Event Planning,
QC Pet Studies, QC Wellness Studies) is being tracked separately — do NOT
include QC in your output. Only extract competitor brands.
"""

COMPETITOR_RULES = """
A "brand" is ONLY a named school, training program, academy, institution,
certification body, or educational platform.
DO NOT treat any of the following as brands: job titles, occupations,
generic nouns (vendors, venues, restaurants), platforms (Facebook, Reddit,
YouTube, Yelp, Thumbtack), job boards (Indeed), URLs or domains.

List every competitor brand mentioned, in the order they first appear.
For each, include the exact substring as it appears in the response text
(so it can be located with a string search) as "text_as_written".
"""

PROMPTS = {
    "course": COMPETITOR_CONTEXT + COMPETITOR_RULES + """
Return JSON only, no preamble, no markdown:
{{
    "competitors": [
        {{"name": "Brand Name", "text_as_written": "exact substring from response"}}
    ],
    "links": [
        {{"url": "https://...", "is_inline": true/false}}
    ]
}}
Every URL from Citations must appear exactly once in "links".
is_inline = true if the response text actively names/recommends this source,
false if it's just a background citation.
""",

    "general": COMPETITOR_CONTEXT + COMPETITOR_RULES + """
Return JSON only, no preamble, no markdown:
{{
    "competitors": [
        {{"name": "Brand Name", "text_as_written": "exact substring from response"}}
    ],
    "links": [
        {{"url": "https://...", "is_inline": true/false}}
    ]
}}
Every URL from Citations must appear exactly once in "links".
is_inline = true if the response text actively names/recommends this source,
false if it's just a background citation.
""",

    "competition": COMPETITOR_CONTEXT + """
Return JSON only, no preamble, no markdown:
{{
    "qc_sentiment": "positive" | "negative" | "neutral",
        - "positive": predominantly favorable toward QC, no significant caveats
        - "negative": serious doubts, explicitly discourages QC, or unfavorable conclusion
        - "neutral": purely factual with no lean, OR balanced pros/cons with no overall lean
    "qc_verdict": "one sentence summary of what the AI concluded about QC",
    "competitor_mentioned": "competitor name" or null,
    "competitor_won": "competitor name" | "QC" | "no_clear_winner" | null,
        - competitor/QC name only if the response clearly favors one overall
        - "no_clear_winner" if it presents both as valid depending on needs (most common case)
        - null only if no competitor was mentioned at all
    "win_reasons": [reasons the winning side was favored, or [] if no_clear_winner/null],
    "concerns_raised": [concerns raised about QC, or []],
    "positives_raised": [positives raised about QC, or []]
}}
"""
}