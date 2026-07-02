from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi import Body

from api.queries import (
    get_mention_rate_by_engine,
    get_mention_rate_by_category,
    get_mention_rate_by_school,
    get_sentiment_distribution,
    get_top_positives,
    get_top_concerns,
    get_top_competitors_by_school,
    get_citations,
    get_summary,
    get_competitor_win_rate,
    get_qc_citations,
    get_citations_by_school,
    get_sentiment_citations,
    get_responses,
    get_citation_rate_by_engine,
    get_citation_rate_by_category,
    get_citation_rate_by_school,
    get_topics,
    get_topics_over_time,
    get_prompt_detail,
)

from api.queries.recommendations_synthesis import (
    generate_recommendations,
    save_recommendations,
    get_saved_recommendations,
    update_recommendation_status,
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

@app.get("/api/citation-rate-by-engine")
def citation_rate_by_engine(days: int = None):
    return get_citation_rate_by_engine(days)

@app.get("/api/citation-rate-by-category")
def citation_rate_by_category(days: int = None):
    return get_citation_rate_by_category(days)

@app.get("/api/citation-rate-by-school")
def citation_rate_by_school(days: int = None):
    return get_citation_rate_by_school(days)

@app.get("/api/sentiment-distribution")
def sentiment_distribution(days: int = None):
    return get_sentiment_distribution(days)

@app.get("/api/top-concerns")
def top_concerns(days: int = None):
    return get_top_concerns(days)

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

@app.get("/api/top-competitors-by-school")
def top_competitors_by_school(days: int = None):
    return get_top_competitors_by_school(days)

@app.get("/api/competitor-win-rate")
def competitor_win_rate(days: int = None):
    return get_competitor_win_rate(days)


@app.get("/api/qc-citations")
def qc_citations(days: int = None):
    return get_qc_citations(days)

@app.get("/api/citations-by-school")
def citations_by_school(days: int = None):
    return get_citations_by_school(days)

@app.get("/api/sentiment-citations")
def sentiment_citations(days: int = None):
    return get_sentiment_citations(days)

@app.get("/api/responses")
def responses(
    days: int = None,
    engine: str = None,
    question_type: str = None,
    school: str = None,
    qc_mentioned: bool = None,
    sentiment: str = None,
    page: int = 1,
    page_size: int = 20
):
    return get_responses(days, engine, question_type, school, qc_mentioned, sentiment, page, page_size)

@app.get("/api/topics")
def topics(days: int = None):
    return get_topics(days)

@app.get("/api/competitor-wins")
def competitor_wins(days: int = None):
    return get_competitor_wins(days)

@app.get("/api/qc-buried-positions")
def qc_buried_positions(days: int = None):
    return get_qc_buried_positions(days)

@app.get("/api/citation-gaps")
def citation_gaps(days: int = None):
    return get_citation_gaps(days)

@app.get("/api/recurring-concerns")
def recurring_concerns(days: int = None):
    return get_recurring_concerns(days)

@app.get("/api/generate-recommendations")
def trigger_recommendations(days: int = None):
    recs = generate_recommendations(days)
    save_recommendations(recs)
    return {"generated": len(recs), "recommendations": recs}

@app.get("/api/recommendations")
def list_recommendations():
    return get_saved_recommendations()

@app.patch("/api/recommendations/{rec_id}")
def patch_recommendation_status(rec_id: str, status: str = Body(..., embed=True)):
    update_recommendation_status(rec_id, status)
    return {"updated": True}


@app.get("/api/topics-over-time")
def topics_over_time(days: int = None):
    return get_topics_over_time(days)

@app.get("/api/topic-prompt/{prompt_id}")
def topic_prompt(prompt_id: str, days: int = None):
    result = get_prompt_detail(prompt_id, days)
    if result is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Prompt not found")
    return result