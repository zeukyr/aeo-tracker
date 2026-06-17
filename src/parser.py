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
    "qc_recommendation": classify as one of:
        - "recommended" if QC is presented as a good option with positive framing, whether as the sole pick, a co-equal pick, or a favorable alternative
        - "not_recommended" if QC is mentioned but described negatively, discouraged, or positioned as inferior to other options
        - "not_mentioned" if QC does not appear anywhere in the response
    "competitors": [list of other schools or platforms mentioned by name],
    "competitor_count": number of competitors mentioned,
    "competitor_won": name of school most prominently recommended, or null if QC won,
    "win_reasons": [reasons the competitor was preferred over QC, or empty list]
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
    "qc_recommendation": classify as one of:
        - "recommended" if QC is presented as a good option with positive framing, whether as the sole pick, a co-equal pick, or a favorable alternative
        - "not_recommended" if QC is mentioned but described negatively, discouraged, or positioned as inferior to other options
        - "not_mentioned" if QC does not appear anywhere in the response
    "competitors": ["list", "of", "other", "schools", "or", "platforms", "mentioned"],
    "competitor_count": integer,
    "competitor_won": "name of platform recommended most prominently, or null if QC won",
    "win_reasons": ["reasons competitor was preferred, or empty list"]
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
    "qc_sentiment": "positive" | "neutral" | "negative",
    "qc_verdict": "one sentence summary of what the AI concluded about QC",
    "concerns_raised": ["list", "of", "concerns", "mentioned"],
    "positives_raised": ["list", "of", "positives", "mentioned"]
}}
The following URLs were cited alongside this response:
{citations}
""",

"competition": """
You are analyzing an AI engine response to the question: "{question}"

The response was:
"{response}"

You are checking whether "QC Career School" (also known as QC Makeup Academy, QC Design School, QC Event Planning, QC Pet Studies, or QC Wellness Studies) is mentioned in the response above.

Extract the following and return as JSON only, no preamble, no markdown:
{{
    "qc_sentiment": "positive" | "neutral" | "negative",
    "qc_verdict": "one sentence summary of what the AI concluded about QC",
    "competitors": ["list", "of", "competitors", "mentioned"],
    "competitor_count": integer,
    "competitor_won": "name of school the AI recommended over QC, or null if QC won",
    "win_reasons": ["reasons competitor was preferred, or empty list"],
    "concerns_raised": ["concerns raised about QC, or empty list"],
    "positives_raised": ["positives raised about QC, or empty list"]
}}
The following URLs were cited alongside this response:
{citations}
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