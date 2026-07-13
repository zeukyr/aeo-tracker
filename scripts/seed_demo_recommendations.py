"""
Seed DEMO recommendations that exercise the redesigned per-type cards
(fix / reach-out / get-listed / build) with the exact content from the design
mockup, so the new UI can be reviewed against realistic payloads.

Non-destructive: rows are inserted directly with a fixed demo batch_id and
status 'proposed' — save_recommendations() is deliberately NOT used, so real
proposed recs are not superseded.

Usage:
    python -m scripts.seed_demo_recommendations           # insert demo cards
    python -m scripts.seed_demo_recommendations --clean   # remove them again
"""

import sys
import uuid

from psycopg2.extras import Json

from api.db import get_connection

DEMO_BATCH_ID = str(uuid.uuid5(uuid.NAMESPACE_DNS, "qc-demo-recommendation-cards"))

# Stable per-rec question ids (uuid5 so re-runs dedupe cleanly by cleanup).
_QID_FIX = str(uuid.uuid5(uuid.NAMESPACE_DNS, "demo-q-event-planner"))
_QID_REACH = str(uuid.uuid5(uuid.NAMESPACE_DNS, "demo-q-grooming-worth-it"))
_QID_BUILD = str(uuid.uuid5(uuid.NAMESPACE_DNS, "demo-q-grooming-schools"))

_FIX_QC_URL = "https://www.qceventplanning.com/become-an-event-planner"

_FIX_FEATURES = [
    {"id": "faq", "label": "FAQ section", "geo_weight": "high",
     "winners_present": 5, "winners_total": 6, "winners_pct": 83,
     "prevalence": "most", "qc_has": False, "recommend": True},
    {"id": "salary_data", "label": "Salary data", "geo_weight": "high",
     "winners_present": 5, "winners_total": 6, "winners_pct": 83,
     "prevalence": "most", "qc_has": False, "recommend": True},
    {"id": "step_by_step", "label": "Step-by-step path", "geo_weight": "high",
     "winners_present": 4, "winners_total": 6, "winners_pct": 67,
     "prevalence": "most", "qc_has": False, "recommend": True},
    {"id": "author_byline", "label": "Author byline", "geo_weight": "medium",
     "winners_present": 3, "winners_total": 6, "winners_pct": 50,
     "prevalence": "some", "qc_has": False, "recommend": False},
    {"id": "comparison_table", "label": "Comparison table", "geo_weight": "medium",
     "winners_present": 2, "winners_total": 6, "winners_pct": 33,
     "prevalence": "some", "qc_has": True, "recommend": False},
    {"id": "schema_markup", "label": "Schema markup", "geo_weight": "high",
     "winners_present": 4, "winners_total": 6, "winners_pct": 67,
     "prevalence": "most", "qc_has": True, "recommend": False},
    {"id": "cited_sources", "label": "Cited external sources", "geo_weight": "medium",
     "winners_present": 4, "winners_total": 6, "winners_pct": 67,
     "prevalence": "most", "qc_has": True, "recommend": False},
    {"id": "cost_breakdown", "label": "Cost breakdown", "geo_weight": "medium",
     "winners_present": 2, "winners_total": 6, "winners_pct": 33,
     "prevalence": "some", "qc_has": False, "recommend": False},
    {"id": "duration_estimate", "label": "Duration estimate", "geo_weight": "low",
     "winners_present": 3, "winners_total": 6, "winners_pct": 50,
     "prevalence": "some", "qc_has": True, "recommend": False},
    {"id": "testimonials", "label": "Student testimonials", "geo_weight": "low",
     "winners_present": 1, "winners_total": 6, "winners_pct": 17,
     "prevalence": "few", "qc_has": True, "recommend": False},
    {"id": "last_updated", "label": "Visible last-updated date", "geo_weight": "medium",
     "winners_present": 3, "winners_total": 6, "winners_pct": 50,
     "prevalence": "some", "qc_has": False, "recommend": False},
    {"id": "toc", "label": "Table of contents", "geo_weight": "low",
     "winners_present": 2, "winners_total": 6, "winners_pct": 33,
     "prevalence": "some", "qc_has": True, "recommend": False},
]

_FIX_GAPS = [
    {k: f[k] for k in ("id", "label", "geo_weight", "winners_present", "winners_total", "winners_pct")}
    for f in _FIX_FEATURES if f["recommend"]
]
_FIX_PARTIAL = [
    {k: f[k] for k in ("id", "label", "geo_weight", "winners_present", "winners_total", "winners_pct")}
    for f in _FIX_FEATURES
    if not f["qc_has"] and not f["recommend"] and f["winners_present"] > 0 and f["geo_weight"] != "low"
]

_FIX_EMERGENT = ("Winners quote a named industry certification (CMP, CSEP) in the first "
                 "paragraph; QC's page introduces its own certificate name only.")

FIX_REC = {
    "problem": ("QC's event-planning career page is the same kind of page as the winners "
                "— and still loses on structure."),
    "action": ("Add an FAQ section answering cost, duration, and prerequisites; add salary "
               f"data with a cited source; add a numbered step-by-step certification path to {_FIX_QC_URL}."),
    "priority": "high",
    "school": "Event Planning",
    "evidence": ("Analyzed 6 of 8 cited pages — 2 could not be fetched. FAQ section — 5/6 (83%) "
                 "cited pages have it, QC does not; Salary data — 5/6 (83%) cited pages have it, "
                 "QC does not; Step-by-step path — 4/6 (67%) cited pages have it, QC does not"),
    "action_type": "technical",
    "target": _FIX_QC_URL,
    "segment": {"dimension": "topic", "value": "event planning certification"},
    "metric_impact": "citation_rate",
    "expected_direction": 1,
    "expected_magnitude": None,
    "effort": "M",
    "confidence": 0.7,
    "detail": {
        "evidence_tier": "high",
        "evidence_grade": {
            "tier": "high",
            "winners_readable": 6,
            "winners_cited_total": 8,
            "winners_unreadable": [
                {"url": "https://eventcareers.example.com/guide", "domain": "eventcareers.example.com",
                 "status": "fetch_failed", "citation_count": 2},
                {"url": "https://plannerpath.example.com/certified", "domain": "plannerpath.example.com",
                 "status": "fetch_failed", "citation_count": 1},
            ],
            "checklist_gaps": _FIX_GAPS,
            "partial_gaps": _FIX_PARTIAL,
            "emergent": {"insight": _FIX_EMERGENT, "edit": ""},
        },
        "scorecard": {
            "topic": "event planning certification",
            "question": "How do I become a certified event planner?",
            "qc_url": _FIX_QC_URL,
            "qc_title": "Become an Event Planner | QC Event School",
            "qc_readable": True,
            "winners": [
                {"url": "https://www.indeed.com/career-advice/finding-a-job/how-to-become-event-planner",
                 "domain": "indeed.com", "page_type": "editorial", "citation_count": 5},
                {"url": "https://eventplannerassoc.org/certify",
                 "domain": "eventplannerassoc.org", "page_type": "reference", "citation_count": 3},
                {"url": "https://www.coursera.org/articles/event-planner",
                 "domain": "coursera.org", "page_type": "editorial", "citation_count": 3},
                {"url": "https://www.thebalancecareers.com/event-planner-career",
                 "domain": "thebalancecareers.com", "page_type": "editorial", "citation_count": 2},
                {"url": "https://www.weddingwire.com/education/event-planning",
                 "domain": "weddingwire.com", "page_type": "editorial", "citation_count": 1},
                {"url": "https://www.nyiad.edu/event-planning-course",
                 "domain": "nyiad.edu", "page_type": "commercial", "citation_count": 1},
            ],
            "winners_total": 6,
            "winners_cited_total": 8,
            "winners_unreadable": [
                {"url": "https://eventcareers.example.com/guide", "domain": "eventcareers.example.com",
                 "status": "fetch_failed", "citation_count": 2},
                {"url": "https://plannerpath.example.com/certified", "domain": "plannerpath.example.com",
                 "status": "fetch_failed", "citation_count": 1},
            ],
            "winners_excluded": [],
            "sufficient": True,
            "features": _FIX_FEATURES,
            "emergent_insight": _FIX_EMERGENT,
            "emergent_edit": "",
            "suggested_edits": [
                "Add an FAQ section answering cost, duration, and prerequisites",
                "Add salary data with a cited source",
                "Add a numbered step-by-step certification path",
            ],
        },
        "router": {
            "branch": "fix",
            "reason": "qc_page_same_kind_still_loses",
            "question_id": _QID_FIX,
            "question": "How do I become a certified event planner?",
            "topic": "Event Planning",
            "qc_share": 0.12,
            "n_citations": 20,
            "dominant_source": "editorial",
            "dominant_share": 0.5,
            "vote": {"voters": 10, "ownable_share": 0.4, "non_ownable_share": 0.6,
                     "buckets": {"editorial": 5, "reference": 3, "competitor": 2},
                     "cleared_bar": False},
            "winners": [
                {"url": "https://www.indeed.com/career-advice/finding-a-job/how-to-become-event-planner",
                 "page_type": "editorial", "source_type": "editorial", "citation_count": 5},
                {"url": "https://eventplannerassoc.org/certify",
                 "page_type": "reference", "source_type": "certifying_body", "citation_count": 3},
                {"url": "https://www.coursera.org/articles/event-planner",
                 "page_type": "editorial", "source_type": "competitor", "citation_count": 3},
                {"url": "https://www.thebalancecareers.com/event-planner-career",
                 "page_type": "editorial", "source_type": "editorial", "citation_count": 2},
                {"url": "https://www.weddingwire.com/education/event-planning",
                 "page_type": "editorial", "source_type": "editorial", "citation_count": 1},
            ],
            "abstentions": [],
            "source_questions": [
                {"question_id": _QID_FIX, "question": "How do I become a certified event planner?",
                 "topic": "Event Planning", "school": "Event Planning"},
            ],
        },
        "priority_rank": {"rank": 4, "of": 14,
                          "reason": "Verified 3-gap diff on an existing page with high citation volume."},
        "question_plan": {"question_id": _QID_FIX, "role": "primary", "emitter": "fix"},
    },
}

REACH_REC = {
    "problem": ('"Is a dog grooming certification worth it?" is answered from Reddit threads '
                "— QC appears in 4% of 26 responses."),
    "action": ("Participate in r/doggrooming — answer certification-value questions as a named "
               "QC educator; the cited thread is open to new replies."),
    "priority": "medium",
    "school": "Pet Grooming",
    "evidence": ("For 'Is a dog grooming certification worth it?' engines cite "
                 "reddit.com (6x); quora.com (3x); thesprucepets.com (2x) across 26 responses; "
                 "QC is cited in 4% of them. Channel: public subreddit, replies open."),
    "action_type": "community",
    "target": "https://www.reddit.com/r/doggrooming/comments/certification_worth_it",
    "segment": {"dimension": "topic", "value": "dog grooming certification value"},
    "metric_impact": "visibility_score",
    "expected_direction": 1,
    "expected_magnitude": None,
    "effort": "S",
    "confidence": 0.6,
    "detail": {
        "router": {
            "branch": "reach_out",
            "reason": "non_ownable_winners",
            "question_id": _QID_REACH,
            "question": "Is a dog grooming certification worth it?",
            "topic": "Pet Grooming",
            "qc_share": 0.04,
            "n_citations": 26,
            "dominant_source": "ugc",
            "dominant_share": 0.64,
            "vote": {"voters": 14, "ownable_share": 0.29, "non_ownable_share": 0.71,
                     "buckets": {"ugc": 9, "editorial": 3, "competitor": 2},
                     "cleared_bar": True},
            "winners": [
                {"url": "https://www.reddit.com/r/doggrooming/comments/certification_worth_it",
                 "page_type": "forum", "source_type": "ugc", "citation_count": 6},
                {"url": "https://www.quora.com/Is-a-dog-grooming-certification-worth-it",
                 "page_type": "forum", "source_type": "ugc", "citation_count": 3},
                {"url": "https://www.thesprucepets.com/become-a-dog-groomer",
                 "page_type": "editorial", "source_type": "editorial", "citation_count": 2},
                {"url": "https://groomertalk.com/threads/certification-value",
                 "page_type": "forum", "source_type": "ugc", "citation_count": 2},
                {"url": "https://www.udemy.com/course/dog-grooming",
                 "page_type": "commercial", "source_type": "competitor", "citation_count": 1},
            ],
            "abstentions": [],
            "source_questions": [
                {"question_id": _QID_REACH, "question": "Is a dog grooming certification worth it?",
                 "topic": "Pet Grooming", "school": "Pet Grooming"},
            ],
            "outreach_feasibility": {
                "channel": "community",
                "feasibility": "open",
                "mechanism": ("Answer certification-value questions as a named QC educator "
                              "(disclosed affiliation); link the tuition/outcomes page only "
                              "where a thread asks for specifics."),
                "evidence": "Public subreddit, replies open",
            },
        },
        "priority_rank": {"rank": 7, "of": 14,
                          "reason": "UGC-dominated query; open channel makes this a small, fast win."},
        "question_plan": {"question_id": _QID_REACH, "role": "primary", "emitter": "reach_out"},
    },
}

# A second cited community for the same question - demonstrates the reach-out
# fan-out: one rec per distinct pitchable community (r/<subreddit> keyed).
REACH_FANOUT_REC = {
    "problem": ("AI engines cite r/petgrooming when answering 'Is a dog grooming "
                "certification worth it?' - QC has no presence in that community."),
    "action": ("Participate in r/petgrooming - answer 'Is a dog grooming certification "
               "worth it?' as a named QC educator (disclosed affiliation); the cited "
               "thread (2x) is the entry point."),
    "priority": "low",
    "school": "Pet Grooming",
    "evidence": ("https://www.reddit.com/r/petgrooming/comments/is_certification_needed "
                 "cited 2x for 'Is a dog grooming certification worth it?' "
                 "(r/petgrooming: 2 citations total). Channel: source-type default: ugc."),
    "action_type": "community",
    "target": "https://www.reddit.com/r/petgrooming/comments/is_certification_needed",
    "segment": {"dimension": "question", "value": "Is a dog grooming certification worth it?",
                "question_id": _QID_REACH},
    "metric_impact": "visibility_score",
    "expected_direction": 1,
    "expected_magnitude": None,
    "effort": "S",
    "confidence": 0.6,
    "detail": {
        "router": {
            **{k: v for k, v in REACH_REC["detail"]["router"].items()
               if k != "outreach_feasibility"},
            "branch": "reach_out_fanout",
        },
        "outreach_feasibility": {
            "channel": "participate",
            "feasibility": "open",
            "mechanism": ("Participate authentically as a named QC presence "
                          "(expert answers, AMAs)."),
            "evidence": "source-type default: ugc",
        },
        "question_plan": {"question_id": _QID_REACH, "role": "companion",
                          "emitter": "reach_out_fanout"},
    },
}

INCLUSION_REC = {
    "problem": ("https://alison.com/tag/event-planning is cited 4x for 'How do I become a "
                "certified event planner?' and lists Udemy, Skillshare, Coursera - but never mentions QC."),
    "action": ("Submit a QC listing to this directory (https://alison.com/tag/event-planning). "
               "(Requires approval.)"),
    "priority": "high",
    "school": "Event Planning",
    "evidence": ("https://alison.com/tag/event-planning cited 4x; page content verified to list "
                 "Udemy, Skillshare, Coursera and never mention QC. Channel: page verified to "
                 "list competitors and not QC."),
    "action_type": "citation",
    "target": "https://alison.com/tag/event-planning",
    "segment": {"dimension": "topic", "value": "event planning directories"},
    "metric_impact": "citation_rate",
    "expected_direction": 1,
    "expected_magnitude": None,
    "effort": "S",
    "confidence": 0.8,
    "detail": {
        "router": {
            "branch": "inclusion_opportunity",
            "reason": "lists_rivals_never_qc",
            "question_id": _QID_FIX,
            "question": "How do I become a certified event planner?",
            "topic": "Event Planning",
            "qc_share": 0.12,
            "n_citations": 20,
            "dominant_source": "editorial",
            "dominant_share": 0.5,
            "vote": {"voters": 10, "ownable_share": 0.4, "non_ownable_share": 0.6,
                     "buckets": {"editorial": 5, "reference": 3, "competitor": 2},
                     "cleared_bar": False},
            "winners": [],
            "abstentions": [],
            "source_questions": [
                {"question_id": _QID_FIX, "question": "How do I become a certified event planner?",
                 "topic": "Event Planning", "school": "Event Planning"},
            ],
        },
        "outreach_feasibility": {
            "channel": "pitch",
            "feasibility": "gated",
            "mechanism": "Pitch QC for inclusion - the page provably lists rival providers.",
            "evidence": "page verified to list competitors and not QC",
        },
        "opportunity": {
            "url": "https://alison.com/tag/event-planning",
            "lists_competitors": ["Udemy", "Skillshare", "Coursera"],
            "citation_count": 4,
        },
        "priority_rank": {"rank": 3, "of": 14,
                          "reason": "Verified inclusion gap on a page engines already cite 4x."},
        "question_plan": {"question_id": _QID_FIX, "role": "companion",
                          "emitter": "inclusion_opportunity"},
    },
}

BUILD_REC = {
    "problem": ('Engines answer "best online dog grooming schools" from competitor pages '
                "— QC is cited in 8% of 24 responses."),
    "action": ("Create a QC page answering 'What are the best online dog grooming schools?' - "
               "rival providers (udemy.com, skillshare.com) won this query with their own pages. "
               "Benchmark depth and coverage against: https://www.udemy.com/topic/dog-grooming, "
               "https://www.skillshare.com/browse/grooming."),
    "priority": "high",
    "school": "Pet Grooming",
    "evidence": ("For 'What are the best online dog grooming schools?' engines cite udemy.com (6x); "
                 "skillshare.com (5x); thesprucepets.com (3x); alison.com (2x) across 24 responses; "
                 "QC is cited in 8% of them."),
    "action_type": "content",
    "target": "What are the best online dog grooming schools?",
    "segment": {"dimension": "topic", "value": "online dog grooming schools"},
    "metric_impact": "citation_rate",
    "expected_direction": 1,
    "expected_magnitude": None,
    "effort": "L",
    "confidence": 0.55,
    "detail": {
        "router": {
            "branch": "build",
            "reason": "no_qc_page",
            "question_id": _QID_BUILD,
            "question": "What are the best online dog grooming schools?",
            "topic": "Pet Grooming",
            "qc_share": 0.08,
            "n_citations": 24,
            "dominant_source": "competitor",
            "dominant_share": 0.61,
            "vote": {"voters": 18, "ownable_share": 0.78, "non_ownable_share": 0.22,
                     "buckets": {"competitor": 11, "editorial": 4, "reference": 2, "ugc": 1},
                     "cleared_bar": True},
            "winners": [
                {"url": "https://www.udemy.com/topic/dog-grooming",
                 "page_type": "directory", "source_type": "competitor", "citation_count": 6},
                {"url": "https://www.skillshare.com/browse/grooming",
                 "page_type": "directory", "source_type": "competitor", "citation_count": 5},
                {"url": "https://www.thesprucepets.com/dog-grooming-schools",
                 "page_type": "editorial", "source_type": "editorial", "citation_count": 3},
                {"url": "https://alison.com/tag/dog-grooming",
                 "page_type": "directory", "source_type": "competitor", "citation_count": 2},
                {"url": "https://petcareacademy.example.net/rankings",
                 "page_type": "editorial", "source_type": "other", "citation_count": 1},
            ],
            "abstentions": [
                {"url": "https://petcareacademy.example.net/rankings",
                 "domain": "petcareacademy.example.net", "page_type": "editorial",
                 "source_type": "other", "fetch_status": "fetch_failed",
                 "reason": "unfetched-unknown-domain"},
            ],
            "source_questions": [
                {"question_id": _QID_BUILD, "question": "What are the best online dog grooming schools?",
                 "topic": "Pet Grooming", "school": "Pet Grooming"},
                {"question_id": str(uuid.uuid5(uuid.NAMESPACE_DNS, "demo-q-grooming-legit")),
                 "question": "Which dog grooming certification programs are legit?",
                 "topic": "Pet Grooming", "school": "Pet Grooming"},
            ],
            "grouped_questions": [
                "What are the best online dog grooming schools?",
                "Which dog grooming certification programs are legit?",
            ],
        },
        "priority_rank": {"rank": 2, "of": 14,
                          "reason": "Two questions converge on the same gap; rivals own the field."},
        "question_plan": {"question_id": _QID_BUILD, "role": "primary", "emitter": "build"},
    },
}

DEMO_RECS = [FIX_REC, REACH_REC, REACH_FANOUT_REC, INCLUSION_REC, BUILD_REC]

_INSERT_SQL = """
    INSERT INTO recommendations (
        problem, action, priority, school, evidence,
        action_type, target, segment, metric_impact,
        expected_direction, expected_magnitude, effort, confidence,
        batch_id, detail, status
    )
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'proposed')
    RETURNING id
"""


def clean(cur):
    cur.execute("DELETE FROM recommendations WHERE batch_id = %s", (DEMO_BATCH_ID,))
    return cur.rowcount


def main():
    with get_connection() as conn:
        with conn.cursor() as cur:
            removed = clean(cur)
            if "--clean" in sys.argv:
                print(f"removed {removed} demo recommendation(s) (batch {DEMO_BATCH_ID})")
                conn.commit()
                return
            ids = []
            for rec in DEMO_RECS:
                cur.execute(_INSERT_SQL, (
                    rec["problem"], rec["action"], rec["priority"], rec.get("school"),
                    rec.get("evidence"), rec.get("action_type"), rec.get("target"),
                    Json(rec["segment"]), rec.get("metric_impact"),
                    rec.get("expected_direction"), rec.get("expected_magnitude"),
                    rec.get("effort"), rec.get("confidence"),
                    DEMO_BATCH_ID, Json(rec["detail"]),
                ))
                ids.append(cur.fetchone()[0])
        conn.commit()
    print(f"replaced {removed} and inserted {len(ids)} demo recommendation(s), batch {DEMO_BATCH_ID}:")
    for rec, rid in zip(DEMO_RECS, ids):
        print(f"  {rid}  [{rec['detail'].get('router', {}).get('branch', '?'):>21}]  {rec['problem'][:70]}")
    print("clean up with: python -m scripts.seed_demo_recommendations --clean")


if __name__ == "__main__":
    main()
