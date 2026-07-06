# Recommendation System — Phase B & Phase C To-Do

Roadmap for the two remaining phases of the closed-loop GEO recommendation system.
Phase A (richer evidence signals) is **done**: `api/queries/recommendation_signals.py`
+ `build_evidence()` in `recommendations_synthesis.py`.

- **Phase B = Quality layer** — make the LLM's recommendations concrete, GEO-sound, and reviewable.
- **Phase C = Closed loop** — track whether implementing a recommendation actually moved the metric.

The DB migration for both phases already exists at
`migrations/001_recommendation_closed_loop.sql` and **has been applied** to the live
Supabase DB (columns confirmed present; `recommendations_status_chk` constraint active).

---

## Phase B — Quality layer — **DONE**

Goal: every recommendation is a **falsifiable hypothesis** (names a metric, a segment,
an expected direction) and is grounded in known-effective GEO tactics + competitor evidence.

### B1. GEO knowledge base
- [x] Create `api/knowledge/geo_playbook.md` — curated Generative-Engine-Optimization tactics
      (third-party citations, "best-of" listicles, Reddit/Quora presence, Wikipedia/Wikidata,
      FAQ/schema markup, comparison-table content, primary-source authority, freshness/recrawl).
- [x] Load it in `recommendations_synthesis.py` (`_load_geo_playbook()`) and inject into the
      prompt so each problem maps onto a proven tactic rather than generic advice.
- [ ] (Optional, deferred) periodic refresh via WebSearch — left static for now.

### B2. Competitor benchmarking
- [x] Added `get_competitor_profile(competitor, days, limit)` to `recommendation_signals.py`:
      surfaces domains cited in responses where the competitor appears + any recorded
      `win_reasons` attributed to them. (Simpler signature than originally sketched — no
      `segment` param needed since brand name alone scopes the query.)
- [x] Wired into `build_evidence()`: profiles the top 2 competitors from `momentum.top_competitors`.
- Verified live: Penn Foster's profile shows `pennfoster.edu`, `facebook.com`, `reddit.com` as
  backing domains — confirms playbook tactic #5 (community presence) is real, observed behavior.

### B3. Falsifiable action schema
- [x] Extended the rec object with: `action_type` (content|technical|citation|outreach),
      `target`, `segment` (jsonb: `{dimension, value}`), `metric_impact`, `expected_direction`
      (1/-1), `expected_magnitude`, `effort` (S/M/L), `confidence` (0-1).
- [x] Updated the generation prompt to require these fields with explicit vocab.
- [x] Added `_normalize_recommendation()` — defense-in-depth validation that coerces any
      out-of-vocabulary field to `None` rather than trusting the model followed the enum,
      independent of the judge pass.
- [x] Updated `save_recommendations()` INSERT (uses `psycopg2.extras.Json` for the `segment`
      jsonb column) and `get_saved_recommendations()` SELECT for the new columns.
- [x] Updated `dashboard/src/tabs/Recommendations.jsx`: new badges for action_type/effort/
      segment/metric+direction/confidence, target line, and **fixed a live bug** — the
      component's `STATUS_OPTIONS` still had the old `pending/in_progress/done` vocabulary,
      which no longer matches the `recommendations_status_chk` constraint applied by the
      migration (would have 500'd on any status change). Now uses the 8-state lifecycle vocab.

### B4. LLM-as-judge critique pass
- [x] Added `critique_recommendations(recommendations, evidence)` — second `gpt-4o-mini` call
      scoring each candidate on specificity / evidence_grounding / geo_soundness / measurability;
      drops only on evidence_grounding ≤ 2 or specificity ≤ 2 (fabricated or too vague), not for style.
- [x] Fails open: if the judge call errors or a rec is missing from its response, that rec is
      kept rather than silently dropped.
- [x] Drops are logged via `src.logger` with the judge's stated reason.
- [x] Wired into `generate_recommendations()`: generate → normalize → critique → return.

### B5. Verify
- [x] Syntax-checked all touched files; confirmed no circular imports (`api.main` imports cleanly).
- [x] Ran all new signal functions + `build_evidence()` live against Supabase — evidence bundle
      is ~19.8k chars (~5k tokens); + playbook (~5.75k chars) well within gpt-4o-mini context.
- [x] DB round-trip test: inserted a dummy rec with all new fields, fetched it back, verified
      `segment` jsonb round-trips correctly and `status` defaults to `'proposed'`, cleaned up.
- [x] Dashboard: `eslint` clean, `vite build` succeeds.
- [ ] **Not yet run**: a real end-to-end `generate_recommendations()` call (actual OpenAI spend +
      writes real rows). User deferred this — trigger via the dashboard's "Generate new
      recommendations" button whenever ready.

---

## Phase C — Closed loop (does implementing it work?)

Goal: measure each recommendation's real effect using difference-in-differences,
and feed outcomes back into future generation.

### C1. Apply the migration
- [ ] Run `migrations/001_recommendation_closed_loop.sql` against Supabase
      (verify `recommendations.id` type matches the FK first).
- [ ] Confirm lifecycle columns + `recommendation_outcomes` table exist.

### C2. Lifecycle state machine
- [ ] Implement status flow: proposed → accepted → in_progress → implemented →
      measuring → {validated | failed | inconclusive}.
- [ ] Extend `update_recommendation_status()` to enforce valid transitions.
- [ ] When a rec is marked `implemented`, capture `implemented_at`.

### C3. Baseline snapshot
- [ ] Add `snapshot_baseline(rec_id)` in new `api/queries/recommendation_evaluation.py`:
      compute the target `metric_impact` within `segment` over the window BEFORE `implemented_at`.
- [ ] Store `baseline_value` + `baseline_sample_n`.

### C4. Difference-in-differences measurement
- [ ] Add `measure_outcome(rec_id)`:
  - [ ] post-window starts ~2–4 weeks after `implemented_at` (GEO recrawl lag).
  - [ ] `lift = (post_target − base_target) − (post_control − base_control)` using untargeted control segments.
  - [ ] gate on minimum sample size; run a two-proportion test for `p_value`.
  - [ ] write verdict (validated | failed | inconclusive) to `recommendations.outcome`
        and append a row to `recommendation_outcomes`.
- [ ] (Optional) designate holdout segments deliberately not acted on, as controls.

### C5. Scheduled sweep
- [ ] Add a job (reuse runs/cron infra) that advances `measuring` rows past their
      window and calls `measure_outcome()`.

### C6. Learning feedback loop
- [ ] Fold validated/failed outcomes into `build_evidence()` so generation favors
      tactic classes with a track record.

### C7. Dashboard impact scorecard
- [ ] Add lifecycle board + implemented-rec win rate + cumulative visibility lift
      to `Recommendations.jsx`.

---

## Known caveats (carry forward)
- Causal attribution in GEO is hard — frame outcomes as **directional evidence**, not proof;
  diff-in-diff + holdout segments are what make it credible.
- Low-volume segments will legitimately stay `inconclusive` (min-sample gate).
- The loop only works if someone actually sets `implemented_at` and does the action.
- `win_reasons` is structurally sparse (few `competition` questions, engines rarely pick a
  winner) — grow the head-to-head question set rather than backfilling.
- Project uses OpenAI (gpt-4o-mini), not Anthropic.
