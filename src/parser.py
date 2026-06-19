import os
import json
from openai import OpenAI
from src.logger import logger
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

PROMPTS = {
"course": """
You are analyzing an AI engine response to the question: "{question}"

The response was:
"{response}"

The following URLs were cited alongside this response:
{citations}

You are checking whether "QC Career School" (also known as QC Makeup Academy, QC Design School, QC Event Planning, QC Pet Studies, or QC Wellness Studies) is mentioned in the response above.

Extract the following and return as JSON only, no preamble, no markdown:
{{
    "qc_mentioned": true if any QC brand is mentioned in the response, false otherwise,
    "qc_mention_order": integer or null.
        - Use 1 for the first school/platform mentioned in the response, 2 for the second, and so on. Never use 0.
        - Use null only if qc_mentioned is false (QC does not appear at all).
        - If QC is mentioned, this must be a positive integer, never 0 or negative.
    "competitors": [list of other COURSES, SCHOOLS, or EDUCATION PLATFORMS mentioned by name that someone could enroll in. Do NOT include QC Career School, QC Makeup Academy, QC Design School, QC Event Planning, QC Pet Studies, or QC Wellness Studies — these are all the same company and should never be listed as competitors.]
    "competitor_count": number of competitors mentioned,
    "competitor_won": name of school most prominently recommended, or null if QC won,
    "win_reasons": [reasons the competitor was preferred over QC, or empty list]
    "qc_cited": true if any URL in the citations list belongs to QC Career School, QC Pet Studies, QC Event Planning, QC Design School, QC Makeup Academy, or QC Wellness Studies — even if QC is not mentioned in the response text itself. false otherwise.
}}
""",

"general": """
You are analyzing an AI engine response to the question: "{question}"

The response was:
"{response}"

You are checking whether "QC Career School" (also known as QC Makeup Academy, QC Design School, QC Event Planning, QC Pet Studies, or QC Wellness Studies) is mentioned in the response above.

Extract the following and return as JSON only, no preamble, no markdown:
{{
    "qc_mentioned": true/false,
    "qc_mention_order": integer or null.
        - Use 1 for the first school/platform mentioned in the response, 2 for the second, and so on. Never use 0.
        - Use null only if qc_mentioned is false (QC does not appear at all).
  - If QC is mentioned, this must be a positive integer, never 0 or negative.
    "competitors": [list of other COURSES, SCHOOLS, or EDUCATION PLATFORMS mentioned by name that someone could enroll in. Do NOT include QC Career School, QC Makeup Academy, QC Design School, QC Event Planning, QC Pet Studies, or QC Wellness Studies — these are all the same company and should never be listed as competitors.],
    "competitor_count": integer,
    "competitor_won": "name of platform recommended most prominently, or null if QC won",
    "win_reasons": ["reasons competitor was preferred, or empty list"]
    "qc_cited": true if any URL in the citations list belongs to QC Career School, QC Pet Studies, QC Event Planning, QC Design School, QC Makeup Academy, or QC Wellness Studies — even if QC is not mentioned in the response text itself. false otherwise.
}}
The following URLs were cited alongside this response:
{citations}
""",

"credibility": """
You are analyzing an AI engine response to the question: "{question}"

The response was:
"{response}"

You are checking whether "QC Career School" (also known as QC Makeup Academy, QC Design School, QC Event Planning, QC Pet Studies, or QC Wellness Studies) is mentioned in the response above.

Extract the following and return as JSON only, no preamble, no markdown:
{{
    "qc_sentiment": classify as one of:
        - "positive" if the response is predominantly favorable toward QC with no significant caveats
        - "negative" if the response raises serious doubts, explicitly discourages QC, or concludes unfavorably
        - "neutral" if the response is purely factual with no clear lean, OR if it's mixed — presenting both positive and cautionary information without a clear overall lean
    "qc_verdict": "one sentence summary of what the AI concluded about QC",
    "concerns_raised": ["list", "of", "concerns", "mentioned"],
    "positives_raised": ["list", "of", "positives", "mentioned"]
    "qc_cited": true if any URL in the citations list belongs to QC Career School, QC Pet Studies, QC Event Planning, QC Design School, QC Makeup Academy, or QC Wellness Studies — even if QC is not mentioned in the response text itself. false otherwise.
}}
The following URLs were cited alongside this response:
{citations}
""",

"competition": """
You are analyzing an AI engine response to the question: "{question}"

The response was:
"{response}"

The following URLs were cited alongside this response:
{citations}

You are checking how "QC Career School" (also known as QC Makeup Academy, QC Design School, QC Event Planning, QC Pet Studies, or QC Wellness Studies) is portrayed in the response above relative to any competitor mentioned.

Read the full response carefully before deciding. Pay attention to which option is actually favored in the text, not just which one is mentioned first or more often.

Extract the following and return as JSON only, no preamble, no markdown:
{{
    "qc_sentiment": classify as one of:
        - "positive" if the response is predominantly favorable toward QC with no significant caveats
        - "negative" if the response raises serious doubts, explicitly discourages QC, or concludes unfavorably
        - "neutral" if the response is purely factual with no clear lean, OR if it's mixed — presenting both positive and cautionary information without a clear overall lean
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

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON from OpenAI: {e}")
        return {}
    except Exception as e:
        logger.error(f"OpenAI parsing error: {e}")
        return {}