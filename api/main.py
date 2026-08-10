from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi import Body, File

from api.recommendations.blog_persona_extract import UnsupportedFileType, extract_text

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
    run_site_audit,
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
    generate_blog_ideas,
    generate_blog_ideas_from_persona,
    generate_full_post,
    get_all_personas,
    get_blog_idea,
    get_blog_idea_candidates,
    get_blog_idea_generation_status,
    get_blog_ideas,
    save_persona,
    update_blog_idea_status,
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

@app.get("/api/site-audit")
def site_audit(school: str = None, refresh: bool = False):
    """Site-wide structural/schema audit of QC's own pages - the cheap,
    LLM-free counterpart to the per-question fix-branch scorecard. See
    api/queries/site_audit.py. `refresh=true` bypasses the page_facts cache
    and re-fetches every page's HTML."""
    return run_site_audit(school, force=refresh)


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

@app.get("/api/blog-personas")
def list_blog_personas():
    """Every saved buyer-persona/testimonials/stats blob, one per school -
    powers the editor on the Blog Ideas tab, used before generation rather
    than a hardcoded knowledge file (see migrations/013_blog_personas.sql)."""
    return get_all_personas()

@app.post("/api/blog-personas/extract")
async def extract_blog_persona_file(file: UploadFile = File(...)):
    """Plain-text extraction for the persona editor's file-upload option
    (pages/BlogPersonas.jsx) - lets a person upload their existing .md/.txt
    persona or testimonial doc, or .xlsx survey export, straight into a
    field's box instead of retyping or copy-pasting it."""
    raw = await file.read()
    try:
        text = extract_text(file.filename, raw)
    except UnsupportedFileType as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not text:
        raise HTTPException(status_code=400, detail="No text could be extracted from this file.")
    return {"text": text}

@app.put("/api/blog-personas")
def put_blog_persona(
    school: str = Body(None),
    buyer_persona: str = Body(None),
    stats: str = Body(None),
    testimonials: str = Body(None),
):
    """Upserts the persona for one school, one category at a time or all
    three together. Blank/whitespace in all three clears the row (deletes
    it) - same endpoint handles both save and clear."""
    return save_persona(school, buyer_persona, stats, testimonials)

@app.get("/api/blog-ideas")
def list_blog_ideas():
    return get_blog_ideas()

@app.get("/api/blog-ideas/generation-status")
def blog_ideas_generation_status():
    return get_blog_idea_generation_status()

@app.get("/api/blog-ideas/candidates")
def blog_idea_candidates(days: int = None):
    """Live, largest-first list of uncovered (topic, school) pairs for the picker."""
    return get_blog_idea_candidates(days)

@app.post("/api/blog-ideas/generate")
def post_generate_blog_ideas(
    days: int = None,
    force: bool = False,
    selections: list[dict] = Body(None),
):
    """selections: [{"topic": str, "school": str | None}, ...] - a (topic,
    school) pair isn't representable as repeated query params, so this takes
    a JSON body instead of the query-param list other picker endpoints use."""
    status = get_blog_idea_generation_status()
    if not status["can_generate"] and not force:
        raise HTTPException(status_code=429, detail={
            "message": "Blog ideas were generated recently; cooldown still active.",
            **status,
        })
    return generate_blog_ideas(days, selections)

@app.post("/api/blog-ideas/generate-from-persona")
def post_generate_blog_ideas_from_persona(school: str = Body(None, embed=True), force: bool = False):
    """Second ideation path: topics mined from one school's saved persona
    data alone, not the tracked-query bank (see
    generate_blog_ideas_from_persona's docstring). Shares the same
    table-wide cooldown gate as /generate above."""
    status = get_blog_idea_generation_status()
    if not status["can_generate"] and not force:
        raise HTTPException(status_code=429, detail={
            "message": "Blog ideas were generated recently; cooldown still active.",
            **status,
        })
    result = generate_blog_ideas_from_persona(school)
    if not result["generated"]:
        raise HTTPException(status_code=422, detail={
            "message": "Couldn't generate topics from this school's persona data.",
            **result,
        })
    return result

@app.get("/api/blog-ideas/{idea_id}")
def single_blog_idea(idea_id: str):
    idea = get_blog_idea(idea_id)
    if idea is None:
        raise HTTPException(status_code=404, detail="Blog idea not found")
    return idea

@app.patch("/api/blog-ideas/{idea_id}")
def patch_blog_idea_status(idea_id: str, status: str = Body(...)):
    try:
        update_blog_idea_status(idea_id, status)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"updated": True}

@app.post("/api/blog-ideas/{idea_id}/draft")
def post_generate_full_post(idea_id: str):
    """On-demand full-post draft for one cluster idea - not cooldown-gated
    like the batch idea generation, since it's already a deliberate
    per-idea human action, not a sweep."""
    result = generate_full_post(idea_id)
    if not result["generated"]:
        raise HTTPException(status_code=422, detail={
            "message": "Couldn't generate a full post for this idea.",
            "reason": result.get("reason"),
        })
    return result

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
