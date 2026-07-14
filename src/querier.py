import os
from dotenv import load_dotenv
from openai import OpenAI, RateLimitError
from perplexity import Perplexity
from google import genai
from src.logger import logger

load_dotenv()

# ---- ChatGPT ----
def query_chatgpt(question):
    try:
        client = OpenAI(
            api_key=os.getenv("OPENAI_API_KEY"),
            max_retries=1)
        response = client.responses.create(
            model="gpt-4o-mini",
            tools=[{"type": "web_search"}],
            tool_choice={"type": "web_search"},
            input=question
        )

        text = response.output_text
        citations = []
        fanout_queries = []
        for item in response.output:
            if hasattr(item, "type") and item.type == "web_search_call":
                action = getattr(item, "action", None)
                if action and hasattr(action, "queries") and action.queries:
                    fanout_queries.extend(q for q in action.queries if q)
            if hasattr(item, "content"):
                for block in item.content:
                    if hasattr(block, "annotations"):
                        for annotation in block.annotations:
                            if annotation.type == "url_citation":
                                citations.append(annotation.url)
    except RateLimitError as e:
        logger.error(f"RateLimitError: {e}")
        raise SystemExit("Rate limited")

    return {
        "text": text,
        "citations": citations,
        "fanout_queries": fanout_queries,
    }
    

def query_gemini_fanout(question):
    try:
        client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=question,
            config=genai.types.GenerateContentConfig(
                tools=[genai.types.Tool(google_search=genai.types.GoogleSearch())]
            )
        )
        queries = []
        if response.candidates:
            meta = response.candidates[0].grounding_metadata
            if meta and meta.web_search_queries:
                queries = list(meta.web_search_queries)
        return {"fanout_queries": queries}
    except Exception as e:
        logger.error(f"Gemini fanout failed: {e}")
        return {"fanout_queries": []}


def query_perplexity(question):
    client = Perplexity()
    completion = client.chat.completions.create(
        model="sonar",
        messages=[{"role": "user", "content": question}]
    )

    text = completion.choices[0].message.content
    citations = completion.citations or []

    return {
        "text": text,
        "citations": citations
    }
    
# ---- Gemini ----
# def query_gemini(question):
#     client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
#     response = client.models.generate_content(
#         model="gemini-2.5-flash",
#         contents=question
#     )
#     return response.text

def query_all_engines(question):
    results = {}

    try:
        chatgpt = query_chatgpt(question)
        results["chatgpt"] = {
            "text": chatgpt["text"],
            "citations": chatgpt["citations"],
            "fanout_queries": chatgpt.get("fanout_queries", []),
        }
    except Exception as e:
        results["chatgpt"] = {"error": str(e)}

    try:
        gemini = query_gemini_fanout(question)
        results["gemini"] = {
            "fanout_queries": gemini.get("fanout_queries", []),
        }
    except Exception as e:
        results["gemini"] = {"error": str(e)}

    # try:
    #     perplexity = query_perplexity(question)
    #     results["perplexity"] = {
    #         "text": perplexity["text"],
    #         "citations": perplexity["citations"],
    #     }
    # except Exception as e:
    #     results["perplexity"] = {"error": str(e)}

    return results