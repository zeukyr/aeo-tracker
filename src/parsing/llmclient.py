"""
llm_client.py

The actual OpenAI call, plus error handling. This is the only file that
should import `openai` or touch API credentials — isolating it here means
swapping models/providers later only touches one file, and unit tests for
prompts.py / merge.py / deterministic.py don't need network mocking.
"""

import json
import os

from dotenv import load_dotenv
from openai import OpenAI, RateLimitError

from src.logger import logger
from .prompts import PROMPTS

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def call_llm(question, question_type, raw_response, citations):
    prompt = PROMPTS[question_type].format(
        question=question,
        response=raw_response,
        citations=citations or []
    )
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=1000,
            messages=[
                {"role": "system", "content": "You are a data extraction assistant. Always respond with valid JSON only. No markdown, no backticks, no preamble."},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
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