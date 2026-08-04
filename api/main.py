from fastapi import FastAPI, HTTPException
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
    get_citation_rate_by_engine,
    get_citation_rate_by_category,
    get_citation_rate_by_school,
    get_topics,
    get_topics_over_time,
    get_prompt_detail,
    get_prompt_responses,
    get_health_summary,
    get_reddit_targets,
    set_reddit_thread_status,
    get_losing_questions,
    set_qc_url_override,
)

from api.recommendations import (
    generate_recommendations,
    save_recommendations,
    generate_reach_out_sweep,
    save_reach_out_recommendations,
    get_saved_recommendations,
    get_recommendation,
    update_recommendation_status,
    set_recommendation_pinned,
    get_generation_status,
    get_question_recommendation_status,
    generate_question_recommendation,
    get_question_recommendations,
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
def mention_rate_by_engine(days: int = None, school: str = None):
    return get_mention_rate_by_engine(days, school)

@app.get("/api/citation-rate-by-engine")
def citation_rate_by_engine(days: int = None, school: str = None):
    return get_citation_rate_by_engine(days, school)

@app.get("/api/citation-rate-by-category")
def citation_rate_by_category(days: int = None, school: str = None):
    return get_citation_rate_by_category(days, school)

@app.get("/api/citation-rate-by-school")
def citation_rate_by_school(days: int = None, school: str = None):
    return get_citation_rate_by_school(days, school)

@app.get("/api/sentiment-distribution")
def sentiment_distribution(days: int = None, school: str = None):
    return get_sentiment_distribution(days, school)

@app.get("/api/top-concerns")
def top_concerns(days: int = None, school: str = None):
    return get_top_concerns(days, school)

@app.get("/api/citations")
def citations(days: int = None, school: str = None):
    return get_citations(days, school)

@app.get("/api/summary")
def summary(days: int = None, school: str = None):
    return get_summary(days, school)

@app.get("/api/mention-rate-by-category")
def mention_rate_by_category(days: int = None, school: str = None):
    return get_mention_rate_by_category(days, school)

@app.get("/api/mention-rate-by-school")
def mention_rate_by_school(days: int = None, school: str = None):
    return get_mention_rate_by_school(days, school)

@app.get("/api/top-positives")
def top_positives(days: int = None, school: str = None):
    return get_top_positives(days, school)

@app.get("/api/top-competitors-by-school")
def top_competitors_by_school(days: int = None, school: str = None):
    return get_top_competitors_by_school(days, school)

@app.get("/api/competitor-win-rate")
def competitor_win_rate(days: int = None, school: str = None):
    return get_competitor_win_rate(days, school)


@app.get("/api/qc-citations")
def qc_citations(days: int = None, school: str = None):
    return get_qc_citations(days, school)

@app.get("/api/citations-by-school")
def citations_by_school(days: int = None, school: str = None):
    return get_citations_by_school(days, school)

@app.get("/api/sentiment-citations")
def sentiment_citations(days: int = None, school: str = None):
    return get_sentiment_citations(days, school)

@app.get("/api/topics")
def topics(
    days: int = None,
    engine: str = None,
    question_type: str = None,
    school: str = None,
    qc_mentioned: bool = None,
    sentiment: str = None,
):
    return get_topics(days, engine, question_type, school, qc_mentioned, sentiment)

@app.get("/api/recommendations/refresh-signals")
def refresh_signal_recommendations(days: int = None, force: bool = False):
    """
    Refresh the concern + credibility recs (no per-question selection), plus
    the reach-out sweep (reach-out primary + inclusion opportunities +
    community fan-out for every current losing question) - both share this
    one cooldown-gated action; the reach-out sweep is cheap (no LLM call)
    but still tied to the same cadence as a deliberate, simple choice rather
    than its own button/schedule.
    """
    status = get_generation_status()
    if not status["can_generate"] and not force:
        raise HTTPException(status_code=429, detail={
            "message": "Recommendations were generated recently; cooldown still active.",
            **status,
        })
    recs = generate_recommendations(days)
    result = save_recommendations(recs)
    reach_out_recs = generate_reach_out_sweep(days)
    result["reach_out"] = save_reach_out_recommendations(reach_out_recs)
    return result

@app.get("/api/recommendations/candidates")
def recommendation_candidates(days: int = None):
    """Live, weakest-first list of losing questions for the question picker."""
    return get_losing_questions(days)

@app.get("/api/recommendations/generation-status")
def recommendations_generation_status():
    return get_generation_status()

@app.get("/api/recommendations/health-summary")
def recommendations_health_summary(days: int = None, school: str = None):
    return get_health_summary(days, school)

@app.get("/api/recommendations/reddit-targets")
def recommendations_reddit_targets(days: int = None, school: str = None):
    return get_reddit_targets(days, school)

@app.put("/api/recommendations/reddit-targets/{post_id}/status")
def put_reddit_thread_status(
    post_id: str,
    url: str = Body(...),
    subreddit: str = Body(None),
    status: str = Body(...),
    reason: str = Body(None),
):
    if status not in ("dead", "open"):
        raise HTTPException(status_code=400, detail="status must be 'dead' or 'open'")
    set_reddit_thread_status(post_id, url, subreddit, status, reason)
    return {"updated": True}

@app.get("/api/recommendations")
def list_recommendations(include_superseded: bool = False):
    return get_saved_recommendations(include_superseded)

@app.get("/api/recommendations/{rec_id}")
def single_recommendation(rec_id: str):
    rec = get_recommendation(rec_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="Recommendation not found")
    return rec

@app.patch("/api/recommendations/{rec_id}")
def patch_recommendation_status(
    rec_id: str,
    status: str = Body(None),
    implemented_at: str = Body(None),
    is_pinned: bool = Body(None),
):
    if status is None and is_pinned is None:
        raise HTTPException(status_code=400, detail="No update provided")
    if status is not None:
        update_recommendation_status(rec_id, status, implemented_at)
    if is_pinned is not None:
        set_recommendation_pinned(rec_id, is_pinned)
    return {"updated": True}

@app.get("/api/questions/{question_id}/recommendation-status")
def question_recommendation_status(question_id: str):
    return get_question_recommendation_status(question_id)

@app.get("/api/questions/{question_id}/recommendations")
def question_recommendations(question_id: str):
    """The question's live action plan: every non-superseded rec covering it."""
    return get_question_recommendations(question_id)

@app.post("/api/questions/{question_id}/recommendation")
def question_recommendation(question_id: str, days: int = None):
    return generate_question_recommendation(question_id, days)

@app.put("/api/questions/{question_id}/qc-url-override")
def set_question_qc_url_override(question_id: str, qc_url: str = Body(...), note: str = Body(None)):
    """A human correction of the matched QC page for this question - takes
    priority over the sitemap matcher from now on. Immediately regenerates
    the question's plan (bypassing the cooldown, not an active/committed rec)
    so the correction is reflected right away instead of on the next
    30-day cycle."""
    set_qc_url_override(question_id, qc_url, note)
    return generate_question_recommendation(question_id, force=True)

@app.delete("/api/questions/{question_id}/qc-url-override")
def clear_question_qc_url_override(question_id: str):
    """Revert to the sitemap matcher's own verdict for this question."""
    set_qc_url_override(question_id, None)
    return generate_question_recommendation(question_id, force=True)


@app.get("/api/topics-over-time")
def topics_over_time(
    days: int = None,
    engine: str = None,
    question_type: str = None,
    school: str = None,
    qc_mentioned: bool = None,
    sentiment: str = None,
):
    return get_topics_over_time(days, engine, question_type, school, qc_mentioned, sentiment)

@app.get("/api/topic-prompt/{prompt_id}")
def topic_prompt(prompt_id: str, days: int = None):
    result = get_prompt_detail(prompt_id, days)
    if result is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Prompt not found")
    return result

@app.get("/api/topic-prompt/{prompt_id}/responses")
def topic_prompt_responses(prompt_id: str, engine: str, days: int = None):
    result = get_prompt_responses(prompt_id, engine, days)
    if result is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Prompt not found")
    return result
