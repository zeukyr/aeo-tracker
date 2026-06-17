import os
from dotenv import load_dotenv
# import google.generativeai as genai
from openai import OpenAI
from perplexity import Perplexity
from google import genai

load_dotenv()

# ---- ChatGPT ----
def query_chatgpt(question):
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    response = client.responses.create(
        model="gpt-4o-mini",
        tools=[{"type": "web_search_preview"}],
        input=question
    )

    text = response.output_text
    citations = []
    for item in response.output:
        if hasattr(item, "content"):
            for block in item.content:
                if hasattr(block, "annotations"):
                    for annotation in block.annotations:
                        if annotation.type == "url_citation":
                            citations.append(annotation.url)

    return {
        "text": text,
        "citations": citations
    }

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
def query_gemini(question):
    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=question
    )
    return response.text

def query_all_engines(question):
    results = {}

    # try:
    #     chatgpt = query_chatgpt(question)
    #     results["chatgpt"] = {
    #         "text": chatgpt["text"],
    #         "citations": chatgpt["citations"],
    #     }
    # except Exception as e:
    #     results["chatgpt"] = {"error": str(e)}

    # try:
    #     perplexity = query_perplexity(question)
    #     results["perplexity"] = {
    #         "text": perplexity["text"],
    #         "citations": perplexity["citations"],
    #     }
    # except Exception as e:
    #     results["perplexity"] = {"error": str(e)}

    try:
        results["gemini"] = {
            "text": query_gemini(question),
            "citations": [],
        }
    except Exception as e:
        results["gemini"] = {"error": str(e)}

    return results