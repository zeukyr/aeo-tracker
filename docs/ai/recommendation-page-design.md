# Recommendations Page — UI + Generation Lifecycle

Design spec for the rebuilt Recommendations tab. Covers the page layout/mockup and the
generation lifecycle (how batches are created, saved, and superseded without losing work).

Companion to `docs/ai/recommendation-system-phases-bc.md` (the phase checklist). This doc is
the **UI + lifecycle decision record**; it is frontend-focused and largely independent of Phase C's
measurement engine.

## Decisions locked in
- **No metric-card grid.** KPI numbers live inline in the summary bullets, not a reused `.metric-grid`.
- **Open with a plain-language summary** — two columns: *What's going well* / *What needs work* —
  derived **deterministically** in code from `get_momentum()` + `get_weakest_*` (no LLM call, updates
  instantly with the period/school filter).
- **Funnel into recommendations ordered by priority**, grouped into High / Medium / Low sections with counts.
- **Each recommendation is trackable**: a per-card tracking bar with a "Mark implemented" action that
  captures the implementation date, then shows a measuring → outcome state.
- **Generation is manual + gated** with a **monthly cooldown**; batches are **non-destructive** —
  committed work is never wiped by a new run.

---

## Page mockup

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  Recommendations                                                                │
│  AI-visibility strategy generated from your tracked data                        │
│  Last updated Jun 28 · next refresh available Jul 28        [ ↻ Refresh (locked)]│
└──────────────────────────────────────────────────────────────────────────────┘

  ┌─ What's going well ────────────────────┐ ┌─ What needs work ─────────────────────┐
  │  ● Positive sentiment 33.3% ↑5.0pts —  │ │  ▲ Gemini: 0% citation rate across 13 │
  │    your biggest gain this period       │ │    responses — effectively invisible  │
  │  ● Perplexity strongest engine —       │ │  ▲ "How to Become" weakest topic:     │
  │    19.4% mention / 34.9% citation      │ │    5.8 visibility over 95 responses   │
  │  ● QC cited on qcpetstudies.com for    │ │  ▲ Penn Foster leads SOV at 13.6%,    │
  │    4 credibility prompts               │ │    backed by Reddit + Facebook        │
  └────────────────────────────────────────┘ └────────────────────────────────────────┘
   green-tinted .card, numbers inline           amber-tinted .card
   (deterministic from momentum + weakest_*)

  ── Active · 1 ────────────────────────────────────────────────────────────────
     (anything past `proposed` — pinned, survives every regeneration)

  ┌────────────────────────────────────────────────────────────────────────────┐
  │  HIGH   citation   QC Pet Studies   effort: M                                │
  │  Pursue inclusion in the 3 grooming-school listicles Gemini cites…           │
  │  ┌ engine: gemini ┐  ┌ targets citation_rate ↑8pts ┐  ┌ confidence 72% ┐     │
  │ ┌──────────────────────────────────────────────────────────────────────────┐│
  │ │  ● Implemented Jun 12 · measuring citation_rate · result ~Jun 26           ││
  │ └──────────────────────────────────────────────────────────────────────────┘│
  └────────────────────────────────────────────────────────────────────────────┘

  PRIORITIZED RECOMMENDATIONS              [ status: All ▾ ]  [ type: All ▾ ]

  ── High priority · 2 ─────────────────────────────────────────────────────────
  ┌────────────────────────────────────────────────────────────────────────────┐
  │  HIGH   content   Both   effort: L                                           │
  │  QC is absent from "best online pet-care courses" comparison pages…          │
  │  → Publish a QC vs Penn Foster comparison page (playbook tactic #6).          │
  │  ┌ topic: How to Become ┐  ┌ targets mention_rate ↑ ┐  ┌ confidence 65% ┐     │
  │  ▸ Show evidence                                                             │
  │ ┌──────────────────────────────────────────────────────────────────────────┐│
  │ │  Not started            [ Accept ]        [ ✓ Mark implemented ]           ││
  │ └──────────────────────────────────────────────────────────────────────────┘│
  └────────────────────────────────────────────────────────────────────────────┘
  ┌────────────────────────────────────────────────────────────────────────────┐
  │  HIGH   outreach   QC Event Planning   effort: S    …                        │
  └────────────────────────────────────────────────────────────────────────────┘

  ── Medium priority · 3 ───────────────────────────────────────────────────────
  ┌── … ──┐  ┌── … ──┐  ┌── … ──┐

  ── Low priority · 1 ──────────────────────────────────────────────────────────
  ┌── … ──┐
```

### "Mark implemented" interaction

```
  click [ ✓ Mark implemented ]
        │
        ▼
  ┌──────────────────────────────────────────────────────────────────────────┐
  │  When did you implement this?   [ 📅 Jun 12, 2026 ]   [ Confirm ]  [ ✕ ]   │
  └──────────────────────────────────────────────────────────────────────────┘
        │ confirm  → PATCH status=implemented, implemented_at=Jun 12
        ▼
  ● Implemented Jun 12 · measuring citation_rate · result ~Jun 26      (measuring)
        │ Phase C measurement runs later
        ▼
  ✓ Worked · citation_rate +6.2pts vs baseline (14 → 20.2%) · validated  (outcome)
```

### Card tracking-bar states

| Status | Tracking bar |
|---|---|
| `proposed` | **[ Accept ]  [ ✓ Mark implemented ]** |
| `accepted` / `in_progress` | "Accepted — not yet implemented" + **[ ✓ Mark implemented ]** |
| `implemented` / `measuring` | `● Implemented {date} · measuring {metric} · result ~{date+window−lag}` |
| `validated` | `✓ Worked · {metric} {±delta} vs baseline · validated` (green) |
| `failed` | `✗ No lift · {metric} flat/down vs baseline` (red) |
| `inconclusive` | `— Inconclusive · not enough data yet` (neutral) |

`result ~{date}` = `implemented_at + measurement_window_days − ~2wk recrawl lag`. The verdict
(worked/failed) is filled in by Phase C; everything up to `measuring` works without it.

---

## Health summary logic (deterministic, no LLM)

`buildHealthSummary(momentum, weakest, positives, qcCitations)` runs client-side from data already fetched.

**Going well** — pick, ranked by magnitude, from: KPIs with a positive diff (for `avg_rank`, a
*negative* diff is good); `momentum.best_engine`; non-empty `qc_citations`.

**Needs work** — from: KPIs with a negative diff; the worst row of
`get_weakest_engines/topics/schools`; `momentum.top_competitors[0]`.

Cap each column at ~3–4 bullets. Fully reactive to the period/school filter.

---

## Generation lifecycle (non-destructive)

Nothing is ever deleted. `save_recommendations()` is already INSERT-only; every run appends a batch
stamped with `generated_at`. The risk to design against is **display churn** — an in-flight rec
visually disappearing under a newer batch. Solved by making **status**, not batch age, decide what's protected.

### Trigger & cooldown
- **Manual, gated.** Server refuses a new batch within **~30 days** of the latest `generated_at`.
- UI header shows `Last updated {date} · next refresh available {date+30d}` with a disabled Refresh
  button until the cooldown clears (and, optionally, until there's genuinely new tracker data).
- Rationale: a monthly rhythm lets the user finish acting on the current batch before the next one
  appears, and matches GEO's slow recrawl timeline.

### What a new batch does to the previous one
```
new batch generates
      │
      ├─ in-flight recs (accepted / in_progress / implemented / measuring / validated / failed)
      │     → PINNED, carried forward untouched, shown in the "Active" section
      │
      └─ old `proposed` recs (nobody acted on them)
            → marked `superseded` (archive, NOT delete) — hidden from the main list, kept for history
```
A rec you "wanted to implement" is by definition no longer `proposed` (you clicked Accept or Mark
implemented), so a regeneration can never wipe it.

### Dedup on regenerate
Before inserting a new `proposed` rec, skip it if an **active** rec already covers the same
`problem` / `segment`, so in-progress work doesn't reappear as a duplicate suggestion.

### Page layout reflects it
- **Active** section (top) = all pinned in-flight recs, across every batch.
- **Prioritized recommendations** (below) = `proposed` recs from the newest batch only, grouped by priority.

---

## New CSS / components (compose from existing `:root` tokens)

| Class | Purpose |
|---|---|
| `.health-grid`, `.health-col--good` / `--warn` | 2-col summary; `.card` tinted `--color-up-bg` / `--color-down-bg` |
| `.section-header` | "High priority · N" / "Active · N" divider rows |
| `.priority-pill--high/med/low` | reuse `--color-down` / `--color-amber` / `--color-neutral` |
| `.chip` | `.badge` base — action_type / segment / metric_impact+direction / confidence |
| `.rec-card`, `.rec-track-bar` | recommendation card + its tracking strip |
| `.rec-track-bar--measuring/--good/--warn/--neutral` | outcome states |

Note: current `Recommendations.jsx` uses raw Tailwind — migrate it onto these semantic classes so it
matches the rest of the dashboard.

---

## Backend changes this UI needs

Small; the measurement engine stays in Phase C.
- Extend `PATCH /api/recommendations/{id}` to accept optional `implemented_at`; persist it in
  `update_recommendation_status()`. (Columns already exist from the migration.)
- Add a `superseded` status value (or `archived` bool) + supersede/dedup logic in the generation path.
- Gate `POST /generate-recommendations` behind the 30-day cooldown (check `MAX(generated_at)`).
- `GET /api/recommendations` returns batch grouping + excludes `superseded` from the default view.

## Deferred to Phase C
Baseline snapshot at implement-time, the diff-in-diff measurement, and the final worked/failed
verdicts in the tracking bar. The card fully supports `proposed → implemented(date) → measuring`
without any of it.
