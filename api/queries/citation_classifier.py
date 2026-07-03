import json
import os

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def classify_citations_for_response(
    competitors: list[str],
    urls: list[str],
    response_text: str,
) -> dict[str, list[str]]:
    """
    For a single AI response that mentions multiple competitors, classify each
    citation URL to the competitor(s) it was cited in support of.

    Uses the full response text (not just domain names) so third-party sites
    are correctly attributed based on context — e.g. a review article cited in
    the Penn Foster paragraph is attributed to Penn Foster even if the domain
    doesn't contain "pennfoster".

    Returns a dict mapping competitor_name → list of URLs.
    A URL may appear under multiple competitors if the response cites it for both.
    """
    if not urls or not competitors:
        return {}

    url_list = "\n".join(f"- {u}" for u in urls)
    competitors_json = json.dumps(competitors)

    prompt = f"""You are analyzing an AI engine response that mentions multiple educational competitors.

Response text:
\"\"\"{response_text}\"\"\"

Competitors mentioned in this response: {competitors_json}
Citation URLs included with this response:
{url_list}

Task: For each competitor, identify which citation URLs were specifically cited in support of content about that competitor.
Rules:
- INCLUDE a URL under a competitor if the response text discusses or recommends that competitor in the same section/context where the URL appears
- INCLUDE third-party review, comparison, or article URLs if the response uses them when talking about a specific competitor
- A URL may appear under multiple competitors if the response cites it for both
- EXCLUDE a URL from a competitor if it clearly belongs to a different competitor's section
- EXCLUDE generic neutral URLs (Wikipedia, job boards, industry directories) unless the response explicitly ties them to a specific competitor

Return JSON only, using the exact competitor names as keys:
{json.dumps({c: ["url1", "url2"] for c in competitors})}

If a competitor has no attributable citations, use an empty list for that key."""

    try:
        response = _client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=800,
            messages=[
                {
                    "role": "system",
                    "content": "You are a data classification assistant. Always respond with valid JSON only. No markdown, no backticks.",
                },
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
        )
        result = json.loads(response.choices[0].message.content)
        # Validate: only keep keys that are actual competitors, values must be lists
        return {
            comp: [u for u in result.get(comp, []) if isinstance(u, str)]
            for comp in competitors
        }
    except Exception:
        return {}
