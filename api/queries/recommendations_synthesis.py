import os
import json
from openai import OpenAI
from dotenv import load_dotenv
from api.queries.recommendations import (
    get_competitor_wins,
    get_qc_buried_positions,
    get_citation_gaps,
    get_recurring_concerns,
)

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

from api.db import get_connection

def save_recommendations(recommendations):
    with get_connection() as conn:
        with conn.cursor() as cur:
            for rec in recommendations:
                cur.execute("""
                    INSERT INTO recommendations (problem, action, priority, school, evidence)
                    VALUES (%s, %s, %s, %s, %s)
                """, (
                    rec["problem"],
                    rec["action"],
                    rec["priority"],
                    rec.get("school"),
                    rec.get("evidence")
                ))
        conn.commit()

def update_recommendation_status(rec_id, status):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE recommendations SET status = %s WHERE id = %s",
                (status, rec_id)
            )
        conn.commit()

def get_saved_recommendations():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, generated_at, problem, action, priority, school, evidence, status
                FROM recommendations
                ORDER BY generated_at DESC, priority ASC;
            """)
            rows = cur.fetchall()
    return [
        {
            "id": str(r[0]),
            "generated_at": str(r[1]),
            "problem": r[2],
            "action": r[3],
            "priority": r[4],
            "school": r[5],
            "evidence": r[6],
            "status": r[7]
        }
        for r in rows
    ]
def generate_recommendations(days=None):
    competitor_wins = get_competitor_wins(days)
    buried_positions = get_qc_buried_positions(days)
    citation_gaps = get_citation_gaps(days)
    concerns = get_recurring_concerns(days)

    summary = f"""
QUESTIONS WHERE COMPETITORS WIN AND QC IS INVISIBLE (top patterns):
{json.dumps(competitor_wins[:20], indent=2)}

QUESTIONS WHERE QC APPEARS BUT IS BURIED BEHIND COMPETITORS:
{json.dumps(buried_positions[:15], indent=2)}

TOPICS WHERE EXTERNAL SITES ARE CITED INSTEAD OF QC (3+ times):
{json.dumps(citation_gaps[:20], indent=2)}

RECURRING CONCERNS RAISED ABOUT QC IN SENTIMENT-FOCUSED RESPONSES:
{json.dumps(concerns[:15], indent=2)}
"""

    prompt = f"""You are an AI visibility strategist analyzing data for QC Career School, 
an online school with faculties in pet care (QC Pet Studies), event planning (QC Event Planning), 
design, makeup, and wellness.

Based on this data:

{summary}

Generate 5-8 specific, actionable recommendations. For each one:
- State the specific problem, citing the exact question, competitor, or concern from the data above
- Recommend a specific, concrete content or website action QC could take
- Estimate priority (high/medium/low) based on how often this pattern repeats in the data
- Specify which school it applies to (QC Pet Studies, QC Event Planning, or both)

Only make claims that are directly supported by the data provided. Do not invent patterns that aren't there.

Return as JSON: {{
    "recommendations": [
        {{
            "problem": "...",
            "action": "...",
            "priority": "high|medium|low",
            "school": "...",
            "evidence": "..."
        }}
    ]
}}"""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        max_tokens=2000,
        messages=[
            {
                "role": "system",
                "content": "You are a data-driven strategy consultant. Always respond with valid JSON only. No markdown, no preamble. Never fabricate data not present in the input."
            },
            {"role": "user", "content": prompt}
        ],
        response_format={"type": "json_object"}
    )

    result = json.loads(response.choices[0].message.content)
    return result["recommendations"]