from fastapi import FastAPI
from api.queries import (
    get_mention_rate_by_engine,
    get_sentiment_distribution,
    get_top_concerns,
    get_top_competitors,
    get_citations
)

app = FastAPI()

@app.get("/")
def root():
    return {"status": "running"}

@app.get("/api/mention-rate-by-engine")
def mention_rate_by_engine(days: int = None):
    return get_mention_rate_by_engine(days)

@app.get("/api/sentiment-distribution")
def sentiment_distribution(days: int = None):
    return get_sentiment_distribution(days)

@app.get("/api/top-concerns")
def top_concerns(days: int = None):
    return get_top_concerns(days)

@app.get("/api/top-competitors")
def top_competitors(days: int = None):
    return get_top_competitors(days)

@app.get("/api/citations")
def citations(days: int = None):
    return get_citations(days)