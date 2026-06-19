from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.queries import (
    get_mention_rate_by_engine,
    get_mention_rate_by_category,
    get_mention_rate_by_school,
    get_sentiment_distribution,
    get_top_positives,
    get_top_concerns,
    get_top_competitors,
    get_citations,
    get_summary,
    get_competitor_win_rate,
)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

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

@app.get("/api/summary")
def summary(days: int = None):
    return get_summary(days)

@app.get("/api/mention-rate-by-category")
def mention_rate_by_category(days: int = None):
    return get_mention_rate_by_category(days)

@app.get("/api/mention-rate-by-school")
def mention_rate_by_school(days: int = None):
    return get_mention_rate_by_school(days)

@app.get("/api/sentiment-distribution")
def sentiment_distribution(days: int = None):
    return get_sentiment_distribution(days)

@app.get("/api/top-positives")
def top_positives(days: int = None):
    return get_top_positives(days)

@app.get("/api/top-competitors")
def top_competitors(days: int = None):
    return get_top_competitors(days)

@app.get("/api/competitor-win-rate")
def competitor_win_rate(days: int = None):
    return get_competitor_win_rate(days)
