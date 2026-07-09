# Recommendation question-router plan

**Status:** proposed (2026-07-08). Restructures the deterministic rec engine from
two independent, additive builders (Tab 1 build + Tab 2 fix) into a single
**per-question router** that classifies the winning pages first and dispatches to
exactly one of three branches. The feature-diff becomes a leaf of the "fix"
branch instead of the entry point for every losing item.

---

## 1. The bug this fixes

Today [`generate_recommendations`](../../api/queries/recommendations_synthesis.py)
runs:

```python
recommendations = build_tab2_recommendations(days)          # feature-diff, every covered topic
recommendations = recommendations + build_tab1_recommendations(days)   # build/earn, additive
```

The two builders run **independently and additively**, at **topic grain**:

- `build_tab2_recommendations` fires [`build_scorecard`](../../api/queries/tab2_scorecard.py)
  (the feature-diff) on *any* topic where QC has a slug-matched page, with **no
  check that the winners are the same kind of page as QC's**. A course page gets
  compared against informational guides and told to "add question headings / FAQ
  / comparison table."
- `build_tab1_recommendations` *separately* notices the genre mismatch via
  [`genre_gap`](../../api/queries/page_facts.py) and says "build a guide" — so the
  same topic emits **both** a mismatched fix and a build.

The feature-diff is being used as the router. The fix is to **classify winners
first and route on that**; the feature-diff only runs inside the fix branch.

## 2. Target structure (the flow we are implementing)

```
1. SELECT (deterministic)   per question, QC losing (low citation share).
                            ALL topics — buildability gates the BUILD branch,
                            NOT selection (§5.1, critique 1).
2. CLASSIFY WINNERS FIRST   bucket each cited page by source-type; find the
                            dominant winning type. No LLM.
3. ROUTE on winner type:
     no dominant type ............................... TRIAGE (visible list, §5.9)
     non-ownable (ugc / review / reference):
         reachable (open / gated) . REACH OUT -> Tab 3        (stop)
         closed (wikipedia / .gov)  ALIGN/BUILD -> Tab 1      (stop)
         unknown .................. TRIAGE (visible list, §5.9)
     ownable (editorial / competitor) AND QC lacks a same-KIND page:
         buildable topic .......... BUILD -> Tab 1            (stop)
         reputation topic ......... REACH OUT (if channel) / TRIAGE   (stop)
     ownable AND QC already has that KIND of page .. FIX -> Tab 2     (step 4)
4. FEATURE-DIFF   only in the fix branch. Same-kind vs same-kind, so
                  "add FAQ / comparison table" is legitimate.
```

**Governing principle (added after review):** a losing question is *never*
silently dropped. Anything the router cannot action with confidence — no dominant
winner type, unknown outreach feasibility, or a reputation question with no
channel — goes to a visible **TRIAGE** list (§5.9), not to silence and not to a
forced build. Selection is deliberately topic-blind; the gates live in the
branches, where they can be selective without swallowing whole categories.

Three work-streams / tabs, one per terminal branch: **Tab 1 Strategic Growth**
(build), **Tab 2 Improve Existing Pages** (fix), **Tab 3 Outreach & Earn**
(reach out). The reach-out branch is itself feasibility-gated (§5.7): outreach we
can actually perform lands in Tab 3; non-ownable sources with no channel fall back
to Tab 1 as "build/align content to earn the slot indirectly."

## 3. Grain decision: per question (validated against data)

Measured on the live DB (2026-07-08):

- **Volume is a non-issue.** Median question carries **16 distinct cited URLs /
  371 citations** across ~48 engine×snapshot responses — ample to name a dominant
  winner type per question.
- **Topics blend disjoint winners.** Average pairwise overlap of the top-5
  winning *domains* between questions in the same topic (Jaccard): Course
  Discovery **0.05** (20 q), How to Become **0.06** (11 q), Career Exploration
  0.12, Starting a Business 0.19. A topic-level "dominant winner type" averages
  unrelated things — the exact mismatch the router removes, one level up.
- **Cheap.** 47 questions total; routing all of them is trivial. The old
  `max_topics=2` cap existed only because topic-level fetches were the cost worry.

Topic keeps a smaller job: it gates the **BUILD branch only** (a reputation
question like "is QC accredited in Canada" can't build its way to credibility),
never selection and never the reach-out or fix branches — §5.1. It is not the
routing unit.

## 4. Architecture: what we reuse vs. build

Most machinery already exists; the change is ordering + one suppression gate.

| Flow step | Reuse | New / changed |
|---|---|---|
| Select losing questions (all topics) | `mention_responses.qc_cited` boolean | `get_losing_questions()` selection query — topic-blind |
| Buildability gate (BUILD branch only) | `questions.topic` | `BUILDABLE_TOPICS` / `REPUTATION_TOPICS` — gate the build branch, not selection |
| Winner source-type buckets | `page_facts.page_type` | `source_type()` + `dominant_source_type()` rollup; review/reference domain sets |
| Reach-out branch | `strategy_to_recommendations` community/earn recs, `inclusion_opportunity` | packaged as a terminal branch |
| Build branch | Tab 1 uncovered / `genre_gap` build recs | packaged as a terminal branch |
| Fix branch (feature-diff) | `build_scorecard`, `scorecard_to_recommendation` | gated behind winner-type match; per-question winners |
| Match gate (has page, wrong kind) | `genre_gap(qc_facts, winner_facts)` | **used to SUPPRESS the scorecard** (today only Tab 1 reads it) |
| Coverage (does QC have a page for this intent) | `diagnose_coverage` (already per-question) | — |
| Outreach feasibility | `inclusion_opportunity`, fetched `page_facts` content | `outreach_channels.json` registry + `outreach_feasibility()` + affordance regex |
| Tab 3 "Outreach & Earn" | `_work_stream`, `WORK_STREAMS` (frontend) | third work-stream (migration-free — derived from `action_type`) |
| Triage: unrouted losing questions | — | `triage` output stream + dashboard "Needs triage" list (§5.9) |

## 5. Components

### 5.1 New module: `api/queries/question_router.py`

The orchestrator. Owns selection, routing, and dedup; delegates rec authoring to
the existing leaf builders.

```python
BUILDABLE_TOPICS  = {"Course Discovery", "How to Become",
                     "Starting a Business", "Career Exploration"}
REPUTATION_TOPICS = {"Brand Credibility", "Competitor Comparison"}

def get_losing_questions(days=None, max_qc_share=0.15):
    """
    Per-question QC citation share across ALL topics (buildability is a BUILD-
    branch gate, not a selection filter — critique 1), share <= threshold.
    Returns [{question_id, question, topic, school, qc_share, n_citations}],
    weakest first. qc_share from qc_cited / total responses (bool column),
    or QC-owned-URL count / total citations for a finer share.
    """

def route_question(q, days=None):
    """
    The router. Returns {"branch": "reach_out"|"build"|"fix"|"triage",
    "question": q, "winners": [...facts], "dominant": (bucket, share),
    "qc_url": url|None, "genre_mismatch": {...}|None,
    "feasibility": {...}|None, "reason": str, "build_candidate": bool}.
    Every losing question yields one of these — "triage" is a first-class
    outcome, never a silent None.
    """

def build_router_recommendations(days=None):
    """Route every losing question; returns (recommendations, triage) — the
    triage list is surfaced, not discarded (§5.9). Dedup per 5.6."""
```

**`route_question` logic (the heart):**

```python
winners = get_question_cited_urls(q["question_id"], days)     # 5.3
facts   = get_pages_facts([w["url"] for w in winners])        # cached per-URL
bucket, share = dominant_source_type(facts)                   # 5.2
buildable = q["topic"] in BUILDABLE_TOPICS

# ── no dominant winner type: a finding, not a silent drop (critique 2) ──
if bucket is None:                        # fragmented field — no format wins
    return triage(q, reason="fragmented_field",
                  build_candidate=buildable)   # QC could plausibly OWN it;
                                               # labelled, not auto-built (§5.9)

# ── non-ownable winners ──
if bucket in ("ugc", "review", "reference"):
    feas = outreach_feasibility(dominant_winner_facts)        # §5.7
    if feas["feasibility"] in ("open", "gated"):
        return {"branch": "reach_out", "feasibility": feas, ...}  # Tab 3
    if feas["feasibility"] == "closed":       # wikipedia / .gov — known unownable
        return {"branch": "build", "reason": "earn_indirect", ...}  # Tab 1 align
    return triage(q, reason="feasibility_unknown")   # NOT auto-build (critique 4)

# ── ownable winners (editorial / competitor) ──
cov    = diagnose_coverage({"dimension": "topic", "value": q["topic"]})
qc_url = _covered_url_for_question(cov, q["question"])    # this question's page
if qc_url:
    gm = genre_gap(get_page_facts(qc_url), facts)         # same-kind check
    if not gm:
        return {"branch": "fix", "qc_url": qc_url, ...}   # -> step 4
    # else: has a page, wrong kind -> falls through to BUILD (buildability-gated)
else:
    gm = None                                             # no QC page at all

# BUILD only fires on buildable topics (critique 1); reputation earns or triages
if buildable:
    return {"branch": "build", "genre_mismatch": gm, ...}          # Tab 1
feas = outreach_feasibility(facts)          # reputation topic — can't build cred
if feas["feasibility"] in ("open", "gated"):
    return {"branch": "reach_out", "feasibility": feas, ...}       # Tab 3
return triage(q, reason="reputation_no_channel")                   # §5.9
```

Two load-bearing lines: `genre_gap` returning non-None is exactly "QC has a page
but it's the wrong kind" — today only `build_tab1` reads it to *add* a build rec;
here it *suppresses* the feature-diff (the core bug fix). And every non-return
path ends in `triage(...)`, never a silent `None`.

### 5.2 Source-type rollup (extend `api/queries/page_facts.py`)

`source_type` is a **router-level layer over `page_type`** — we do **not** add new
`page_type` values (avoids rippling `_COMPARABLE_TYPES`, `PAGE_TYPE_ACTIONS`, the
genre maps). Domain rules run first, then map the existing `page_type`:

```python
_REVIEW_DOMAINS    = {"g2.com", "capterra.com", "trustpilot.com", "coursera.org",
                      "udemy.com", "classcentral.com", "coursereport.com",
                      "switchup.org", "careerkarma.com"}
_REFERENCE_DOMAINS = {"wikipedia.org", "wikidata.org", "britannica.com"}

_PAGE_TYPE_TO_SOURCE = {
    "community": "ugc",
    "competitor": "competitor",
    "guide": "editorial", "editorial": "editorial", "association": "editorial",
    "roundup": "editorial", "directory": "editorial",
    "government": "reference",
    "video": "other", "qc_owned": "other",
}

def source_type(facts):
    root = _root_domain(facts.get("domain", ""))
    if root in _REVIEW_DOMAINS:    return "review"
    if root in _REFERENCE_DOMAINS: return "reference"
    return _PAGE_TYPE_TO_SOURCE.get(facts.get("page_type"), "other")

def dominant_source_type(winner_facts, threshold=0.6):
    """
    Citation-weighted dominant bucket, or (None, share) when nothing clears
    `threshold`. "other" votes are excluded from the denominator (they don't
    vote — a URL cited 40x weighs more than one cited once). threshold reuses
    the 0.6 dominance bar already used by genre_gap.
    """
```

Weight by `citation_count` (attached per winner), not raw page count.

### 5.3 Per-question winners (extend `api/queries/tab1_strategy.py`)

Mirror [`get_topic_cited_urls`](../../api/queries/tab1_strategy.py) with a
`question_id` filter:

```python
def get_question_cited_urls(question_id, days=None, limit=_TOP_N_URLS):
    """Top external (non-QC) URLs cited for ONE question, ranked by count."""
    # WHERE m.question_id = %s  (instead of the segment clause)
```

### 5.4 Fix branch — per-question feature-diff (extend `api/queries/tab2_scorecard.py`)

`build_scorecard` currently re-fetches winners by topic. Add an optional
`winner_facts` / `question_id` param so the router passes **this question's**
winners straight in (already fetched in `route_question` — no refetch):

```python
def build_scorecard(topic, qc_url, question=None, days=None, winner_facts=None):
    # if winner_facts is None: fall back to today's get_topic_cited_urls path
```

`scorecard_to_recommendation(sc)` is unchanged — still emits the technical rec.

### 5.5 Reach-out and build leaf builders

Reuse the existing rec-dict shapes so `_normalize_recommendation` /
`critique_recommendations` / the DB schema are untouched.

- **reach_out** (emits `action_type` in `{"outreach","citation","community"}` →
  Tab 3; every card carries `outreach_feasibility` in `detail` for the badge):
  - `ugc` → authentic community-presence rec (reuse the ecosystem rec in
    [`strategy_to_recommendations`](../../api/queries/tab1_strategy.py)).
  - `review` → "claim/create a profile on {domain}; solicit reviews."
  - `reference` → usually `closed` → re-routes to a Tab 1 build/align rec.
  - In all cases, also surface any per-winner `inclusion_opportunity` (roundups/
    directories that provably list rivals but not QC) as a concrete Tab 3 target,
    each feasibility-gated. `closed`/`unknown` targets fall back to Tab 1 (§5.7).
- **build**: reuse the genre-mismatch build rec and the gap-build rec from
  `strategy_to_recommendations` (informational-guide vs course-page wording is
  already written there).

### 5.6 Dedup (per-question grain's one cost)

Near-duplicate questions route to the same target. After routing all 47:

- **fix** → group by `qc_url`. Run the scorecard **once per unique QC page**
  (representative = highest-volume / lowest-share question), not once per
  question — bounds the semantic-LLM passes to #pages, not #questions.
- **build** → group by (intent / page-kind, school). Group size is a **priority
  booster**, not a firing gate — singletons still build (§7, critique 3).
- **reach_out** → group by target platform/domain + bucket.

### 5.7 Outreach feasibility (the reach-out branch's second router)

The reach-out branch must not emit "pitch this site" without a channel to pitch
*through*. Reddit and Coursera are reachable; a `.gov` page or Wikipedia is not.
Feasibility is determined **deterministically** from three layers, in order:

1. **Curated domain registry** — `api/knowledge/outreach_channels.json` (a static
   knowledge artifact, refreshed ~monthly like `geo_playbook.md` / `qc_sitemaps.json`).
   High-value domains with their exact channel + mechanism:

   ```json
   {
     "domains": {
       "reddit.com":       {"channel":"participate","feasibility":"open",
                            "mechanism":"Post authentic expert answers / host an AMA as a named QC account."},
       "quora.com":        {"channel":"participate","feasibility":"open",
                            "mechanism":"Answer relevant questions from a verified QC expert profile."},
       "coursera.org":     {"channel":"partner","feasibility":"gated",
                            "mechanism":"Apply to Coursera's partner/content program (approval required)."},
       "classcentral.com": {"channel":"submit","feasibility":"open",
                            "mechanism":"Submit QC courses to the Class Central catalog."},
       "g2.com":           {"channel":"claim","feasibility":"open",
                            "mechanism":"Claim/create the QC vendor profile; solicit reviews."},
       "trustpilot.com":   {"channel":"claim","feasibility":"open",
                            "mechanism":"Claim the QC business profile; invite reviews."},
       "wikipedia.org":    {"channel":"align","feasibility":"closed",
                            "mechanism":"No direct edits (COI). Earn a citation by publishing a source editors can reference."}
     },
     "gov_tld":            {"channel":"none","feasibility":"closed",
                            "mechanism":"Not reachable. Benchmark the authority; align QC content."}
   }
   ```

2. **Page-content affordance scan** — for editorial / unknown domains not in the
   registry, look at the already-fetched `page_facts` content for a submission or
   claim affordance (deterministic regex, no LLM):

   ```python
   _OUTREACH_AFFORDANCE = re.compile(
       r"\b(write for us|submit (a )?(listing|guest|your)|contribute|"
       r"add your (business|school|listing)|claim (this|your) (listing|profile|business)|"
       r"get listed|nominate|advertise with us)\b", re.I)
   ```

   A match → `open` (the matched phrase is the evidence). A contact page / email
   but no self-serve affordance → `gated`. Nothing → `unknown`.

3. **Source-type default** — when the domain is unknown and the page couldn't be
   read: `ugc → participate/open`, `review → claim/gated`, `reference → align/closed`,
   `editorial → pitch/unknown`.

```python
def outreach_feasibility(facts):
    """{channel, feasibility: open|gated|closed|unknown, mechanism, evidence}.
    Registry override -> page affordance -> source-type default."""
```

**How feasibility routes the card:**

| feasibility | destination | framing |
|---|---|---|
| `open` | Tab 3 card | concrete outreach action; confidence 0.6, effort S |
| `gated` | Tab 3 card, badged "requires application/partnership" | confidence 0.5, effort M |
| `closed` (**known** non-ownable: wikipedia, `.gov`) | **Tab 1 build/align** | "publish authoritative content to earn the slot — no direct channel to {domain}" |
| `unknown` (unclassified domain / unreadable page) | **TRIAGE (§5.9)** | do NOT build off a source we couldn't classify — surface for a human decision (critique 4) |

The `closed` vs `unknown` split is deliberate. A Wikipedia- or `.gov`-dominant
question is *known* to be unownable, so "build the authoritative source they'd
cite" is a justified content action. But `unknown` means we failed to even
classify the source — routing that to a build is the same forced-answer pattern
the router exists to kill, so it goes to triage instead.

`outreach_feasibility` also runs on **per-winner inclusion opportunities**
(roundups/directories that provably list rivals but not QC — from
`inclusion_opportunity`), so those become Tab 3 cards gated the same way, instead
of sitting in Tab 1 as they do today.

### 5.8 Tab 3 wiring (backend + frontend)

Migration-free — tabs are derived from `action_type`, not stored.

- **Backend** — the reach-out branch emits `action_type` in
  `{"outreach","citation","community"}`; extend
  [`_work_stream`](../../api/queries/recommendations_synthesis.py):

  ```python
  if action_type == "technical":                         return "on_page"
  if action_type in ("outreach","citation","community"): return "outreach"
  return "strategic"
  ```

  Carry `feasibility` in the rec's `detail` for the badge.

- **Frontend** — add a third entry to `WORK_STREAMS` in
  [`Recommendations.jsx`](../../dashboard/src/tabs/Recommendations.jsx) and update
  the `streamOf` fallback:

  ```js
  { key: "outreach", label: "Outreach & Earn",
    question: "Where does AI look that we can't own?",
    note: "For PR / partnerships / community — earn presence on the third-party sources engines cite. Each card shows whether a channel exists (open / requires application / no direct channel)." }
  ```

  Note: this **moves** today's inclusion/earn recs out of Strategic Growth into
  Outreach & Earn — intended; Tab 1 becomes build-only.

### 5.9 Triage: unrouted losing questions (never silently dropped)

The three action branches only fire when the router is confident. Everything else
a losing question can be — and given the fragmented winners (Jaccard 0.05–0.19),
"no dominant type" is expected to be one of the **largest** buckets — lands here,
visibly, instead of vanishing.

```python
def triage(q, reason, build_candidate=False):
    return {"branch": "triage", "question": q, "reason": reason,
            "build_candidate": build_candidate}
```

`reason` ∈ `{fragmented_field, feasibility_unknown, reputation_no_channel}`.

- **`fragmented_field`** (no dominant winner type) is itself a finding: no single
  format wins the query, so QC could plausibly *own* it with one strong page.
  When the topic is buildable it's flagged `build_candidate=True` — but it stays
  in triage as a labelled candidate for a human to green-light; it does **not**
  auto-fire a build rec (same discipline as `unknown` feasibility).
- **`feasibility_unknown`** — non-ownable winners we couldn't find a channel for.
- **`reputation_no_channel`** — a Brand Credibility / Competitor Comparison
  question with ownable-but-unbuildable winners and no outreach channel. (These
  are *also* still handled by the existing `build_concern_recommendations` /
  `build_credibility_recommendation` engines — triage just makes sure the router
  itself doesn't lose them.)

**Surfacing:** `build_router_recommendations` returns `(recommendations, triage)`.
The triage list renders as a distinct, collapsed **"Needs triage — losing
questions the router couldn't auto-action"** panel on the Recommendations page
(not inside the three action tabs), each row showing the question, its reason, and
the `build_candidate` flag. This keeps the count visible (the metric §10 asks us
to track) and turns "silently produces nothing" into "here are the N questions a
human should look at."

## 6. Orchestration rewrite (`recommendations_synthesis.py`)

```python
def generate_recommendations(days=None):
    recommendations, triage = build_router_recommendations(days)  # replaces tab2 + tab1
    recommendations += build_concern_recommendations(days)  # unchanged
    cred = build_credibility_recommendation(days)           # unchanged
    if cred: recommendations.append(cred)
    recommendations = _apply_competitive_boost(recommendations, days)
    # strategic_evidence attach loop stays as-is
    return recommendations, triage    # triage surfaced to the API/dashboard (§5.9)
```

`build_tab1_recommendations` / `build_tab2_recommendations` retire as top-level
entry points; their internals (`analyze_strategic_topic`, `strategy_to_recommendations`,
`build_scorecard`, `scorecard_to_recommendation`) live on as the branch leaves.

## 7. Confidence / gating (per the target structure)

- **Fix** — safest, fires on weaker evidence. `confidence 0.7` (unchanged).
- **Build** — highest effort + uncertainty, but per-question grain + low topic
  overlap means valid builds are frequently **singletons** (one question hits one
  guide gap — e.g. "how to start an event planning business"), and singletons can
  carry independent Search Console demand. So a **single question is enough to
  fire** (critique 3). `confidence 0.55`. Convergence and demand are **priority
  boosters, not firing gates**: ≥N questions routing BUILD to the same target
  (from 5.6 dedup) or a Search Console volume signal raise priority/confidence;
  their absence never suppresses a build. (`fragmented_field` build *candidates*
  from §5.9 are the separate, weaker case — those stay in triage.)
- **Reach out** — fires when winners are non-ownable **and a channel exists**
  (§5.7). Framed as PR / community / review-profile action. `confidence` 0.6
  (`open`) / 0.5 (`gated`). `closed`/`unknown` never fires as outreach — it
  re-routes to a Tab 1 build/align rec so no card asks for an impossible action.

## 8. Segment / measurement

Set `segment = {"dimension": "question", "value": question, "question_id": id}`
for precision, and add a one-line `question` case to
[`_segment_clause_params`](../../api/queries/recommendation_signals.py)
(`AND m.question_id = %s`). This makes the future Phase C diff-in-diff
question-grained (more precise than topic). Back-compat: keep `topic` available in
`detail` for topic-level rollups on the dashboard.

## 9. Phased checklist

- [ ] R1 `source_type` + `dominant_source_type` + review/reference domain sets (`page_facts.py`)
- [ ] R2 `get_question_cited_urls` (`tab1_strategy.py`)
- [ ] R3 `build_scorecard(..., winner_facts=)` param (`tab2_scorecard.py`)
- [ ] R4 `question_router.py`: `get_losing_questions`, `route_question`, leaf dispatch, dedup
- [ ] R5 rewire `generate_recommendations`; retire tab1/tab2 top-level builders
- [ ] R6 `question` case in `_segment_clause_params`
- [ ] R7 per-branch confidences; build fires on singletons (convergence/SC boost priority, not gate — critique 3)
- [ ] R8 `outreach_channels.json` registry + `outreach_feasibility()` + affordance regex (§5.7)
- [ ] R9 Tab 3: `_work_stream` outreach mapping + `WORK_STREAMS`/`streamOf` in `Recommendations.jsx` (§5.8)
- [ ] R10 `triage()` + `(recommendations, triage)` return threaded through API; "Needs triage" panel in `Recommendations.jsx` (§5.9)
- [ ] R11 verify: dry-run router over all 47 questions — assert (a) the motivating
      case ("how to start a business" → editorial winners + QC course page → BUILD,
      scorecard NOT run), (b) no question emits both a fix and a build, (c) a
      reddit/coursera-dominant question → Tab 3 `open`/`gated`, wikipedia/.gov →
      Tab 1 build, (d) a Brand Credibility question is *selected* (not dropped) and
      routes to reach-out or triage, (e) unclassifiable/fragmented questions land
      in triage, not in a build — and log the triage count/reasons

**Immediate bleed-stopper (ship first, independently):** in
`build_tab2_recommendations`, call `genre_check` and `continue` on a mismatch.
One commit, stops the bad recs today; the full router (R1–R8) then supersedes it.

## 10. Risks / caveats

- Review/reference domain sets are allowlists — will miss long-tail platforms;
  start small, extend as `page_type=editorial` winners get spot-checked.
- `coursera.org` etc. could also read as competitor via brand-token match — the
  domain check runs first in `source_type`, so review wins; confirm on real data.
- "No dominant type" is expected to be one of the LARGEST buckets given the low
  topic overlap (fragmented winners rarely clear 0.6). These are NOT dropped —
  they go to the triage list as `fragmented_field` findings (§5.9). Still track
  the count and reasons: a very high rate may mean the 0.6 bar is too strict, or
  that the triage list needs its own build-candidate ranking to be useful.
- Triage is only valuable if someone reads it. If the "Needs triage" panel grows
  unbounded and is ignored, fragmented findings are lost in practice even though
  they aren't dropped in code — worth a lightweight ranking (by citation volume /
  qc_share) so the strongest own-the-field candidates surface first.
- 47 questions is the current tracked set; the router scales with it, but a
  materially larger set may re-raise the scorecard LLM cost — 5.6 dedup is what
  keeps it bounded.
