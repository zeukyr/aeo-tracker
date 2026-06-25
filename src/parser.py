import os
import json
from openai import OpenAI
from src.logger import logger
from dotenv import load_dotenv
from openai import RateLimitError
load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
QC_BRANDS = "QC Career School, QC Makeup Academy, QC Design School, QC Event Planning, QC Pet Studies, QC Wellness Studies"

BRAND_EXTRACTION_RULES = """
1. A "brand" is ONLY a named school, training program, academy, institution, certification body, or educatoinal platform 
2. DO NOT treat any of the following as brands:
   - job titles (e.g., dog groomer, veterinarian, HVAC technician)
   - occupations (e.g., photographer, florist, plumber)
   - generic nouns (e.g., vendors, venues, restaurants)
   - platforms (e.g., Facebook, Reddit, YouTube, Yelp, Thumbtack)
   - job boards (e.g., Indeed)
   - URLs or domains

3. Output a list of ALL brands mentioned in the order they appear.
   For each brand, include:
     - "name": the brand name (not the URL)
     - "brand_type": "qc" OR "competitor"
     - "rank_position": 1 for the first brand mentioned, 2 for the second, etc.

4. QC brands (QC Career School, QC Makeup Academy, QC Design School,
   QC Event Planning, QC Pet Studies, QC Wellness Studies) must ALWAYS be:
     - brand_type = "qc"
     - NEVER included as competitors.
"""

LINK_EXTRACTION_RULES = """
5. For EVERY url in the Citations list above, output a link object with:
     - "url": the citation url, copied exactly as given.
     - "is_qc": true if the url is QC's own site, OR a third-party page that
       specifically discusses, reviews, or recommends one of the QC brands.
       false if it's about a competitor, or unrelated/generic content.
     - "is_inline": true if the response text actively names or recommends
       this source as part of its answer, false if it only appears as a
       background citation with no specific emphasis in the text.
   If the Citations list is empty, "links" must be an empty list.
   Every url from the Citations list must appear exactly once in "links".
"""

QC_CONTEXT = """
You are analyzing an AI engine response to the question: "{question}"
Response: "{response}"
Citations: {citations}
QC Career School (also known as """ + QC_BRANDS + """) is the brand being tracked.
"""

PROMPTS = {
"course": QC_CONTEXT + BRAND_EXTRACTION_RULES + LINK_EXTRACTION_RULES + """
Extract the following and return as JSON only, no preamble, no markdown:
{{
    "qc_mentioned": true/false,
    "qc_mention_order": integer or null,
        - Use 1 if a QC brand is the first mentioned in the response, 2 for the second, and so on. Never use 0.
        - Use null only if qc_mentioned is false (QC does not appear at all).
    "qc_cited": true/false,
    "brands": [
        {{
            "name": "Brand Name",
            "brand_type": "qc" | "competitor",
            "rank_position": integer
        }}
    ],
    "links": [
        {{
            "url": "https://...",
            "is_qc": true/false,
            "is_inline": true/false
        }}
    ]
}}
""",

"general": QC_CONTEXT + BRAND_EXTRACTION_RULES + LINK_EXTRACTION_RULES + """
Extract the following and return as JSON only, no preamble, no markdown:
{{
    "qc_mentioned": true/false,
    "qc_mention_order": integer or null,
        - Use 1 if a QC brand is the first mentioned in the response, 2 for the second, and so on. Never use 0.
        - Use null only if qc_mentioned is false (QC does not appear at all).
    "qc_cited": true/false,
    "brands": [
        {{
            "name": "Brand Name",
            "brand_type": "qc" | "competitor",
            "rank_position": integer
        }}
    ],
    "links": [
        {{
            "url": "https://...",
            "is_qc": true/false,
            "is_inline": true/false
        }}
    ]
}}
""",

"competition": QC_CONTEXT + """
Extract the following and return as JSON only, no preamble, no markdown:
{{
    "qc_sentiment": classify as one of:
        - "positive" if the response is predominantly favorable toward QC with no significant caveats
        - "negative" if the response raises serious doubts, explicitly discourages QC, or concludes unfavorably
        - "neutral" if the response is purely factual with no clear lean, OR if it presents both positive and cautionary information without a clear overall lean
    ONLY use these 3 sentiment labels. Do not invent your own labels or use any other words to describe the sentiment.
    "qc_verdict": "one sentence summary of what the AI concluded about QC",
    "competitor_won": classify as exactly one of:
        - the competitor's name, ONLY if the response clearly states or strongly implies the competitor is the better choice overall
        - "QC", ONLY if the response clearly states or strongly implies QC is the better choice overall
        - "no_clear_winner", if the response presents both as valid depending on the person's goals, budget, or needs (this is common — most comparison answers do this, do not force a winner if the text doesn't pick one)
        - null, only if no competitor was mentioned at all,
    "win_reasons": [reasons the winning side was favored, or empty list if competitor_won is "no_clear_winner" or null],
    "concerns_raised": [concerns raised about QC, or empty list],
    "positives_raised": [positives raised about QC, or empty list]
    "qc_cited": true if any URL in the citations list belongs to QC Career School, QC Pet Studies, QC Event Planning, QC Design School, QC Makeup Academy, or QC Wellness Studies — even if QC is not mentioned in the response text itself. false otherwise.
}}
"""
}

def parse_response(question, question_type, raw_response, citations=None):
    try:
        prompt = PROMPTS[question_type].format(
            question=question,
            response=raw_response,
            citations=citations or []
        )

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=1000,
            messages=[
                {
                    "role": "system",
                    "content": "You are a data extraction assistant. Always respond with valid JSON only. No markdown, no backticks, no preamble."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            response_format={"type": "json_object"}
        )

        raw = response.choices[0].message.content.strip()
        logger.info(f"RAW OPENAI OUTPUT: {raw}")
        return json.loads(raw)

    except RateLimitError as e:
        if "insufficient_quota" in str(e):
            raise SystemExit("OpenAI quota exhausted")
        logger.error(f"OpenAI rate limit: {e}")
        return {}
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON: {e}")
        return {}
    except Exception as e:
        logger.error(f"OpenAI parsing error: {e}")
        return {}
