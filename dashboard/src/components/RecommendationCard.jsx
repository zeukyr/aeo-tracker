import { useState } from "react";
import { formatDate } from "../lib/format";
import { cardVariant, channelLabel, urlLabel, feasibilityOf } from "../lib/recview";
import InfoTip from "./InfoTip";
import RecTrail from "./rec/RecTrail";
import RecCitations from "./rec/RecCitations";
import FixDiffModule from "./rec/FixDiffModule";
import TargetDossier from "./rec/TargetDossier";
import ContentBrief from "./rec/ContentBrief";
import PagePlan from "./rec/PagePlan";
import { VARIANTS, BADGE_ICONS } from "./rec/variantMeta";

const EFFORT_DOTS = { S: 1, M: 2, L: 3 };
const EFFORT_LABELS = { S: "Small effort", M: "Medium effort", L: "Large effort" };

function addDays(iso, days) {
  const d = new Date(iso);
  d.setDate(d.getDate() + days);
  return d.toISOString();
}

function todayISODate() {
  return new Date().toISOString().slice(0, 10);
}

function formatMetric(rec) {
  if (!rec.metric_impact) return null;
  const arrow = rec.expected_direction === 1 ? "↑" : rec.expected_direction === -1 ? "↓" : "";
  const magnitude = rec.expected_magnitude != null ? ` ${rec.expected_magnitude}` : "";
  return `targets ${rec.metric_impact} ${arrow}${magnitude}`.trim();
}

function formatOutcome(rec) {
  const o = rec.outcome;
  if (!o || o.diff_in_diff_lift == null) return "";
  const sign = o.diff_in_diff_lift > 0 ? "+" : "";
  return ` · ${rec.metric_impact} ${sign}${o.diff_in_diff_lift}pts vs baseline`;
}

// Fix cards already restate every gap in the checklist below (ActionLine) -
// the intro paragraph only needs to set the scene, not re-list the specifics.
// Other variants' rec.problem isn't duplicated by a checklist, so it's left as-is.
function problemLine(rec, variant) {
  if (variant !== "fix") return rec.problem;
  const sc = rec.detail?.scorecard;
  const gaps =
    rec.detail?.evidence_grade?.checklist_gaps?.length ??
    (sc?.features || []).filter((f) => f.recommend).length;
  const metricGaps =
    rec.detail?.evidence_grade?.metric_gaps?.length ??
    (sc?.metric_rows || []).filter((r) => r.recommend).length;
  const total = gaps + metricGaps;
  if (!total) return rec.problem;
  return (
    <>
      Engines cite competitors instead of QC{sc?.question ? <> for &lsquo;{sc.question}&rsquo;</> : ""}.{" "}
      {total} structural issue{total === 1 ? "" : "s"} out of range — fixes below.
    </>
  );
}

// The verdict band's one-line "why this card exists", per variant.
function verdictLine(rec, variant) {
  const router = rec.detail?.router;
  if (variant === "fix") {
    const gaps =
      rec.detail?.evidence_grade?.checklist_gaps?.length ??
      (rec.detail?.scorecard?.features || []).filter((f) => f.recommend).length;
    return (
      <>
        <b>The page exists but engines skip it</b>
        {gaps > 0
          ? <> — {gaps} verified structural gap{gaps === 1 ? "" : "s"} vs the cited field.</>
          : <> — weaker signals only, below the evidence bar.</>}
      </>
    );
  }
  if (variant === "reach") {
    // Fan-out companions supplement an ownable-field primary (fix/build) —
    // "QC can't own" belongs only to the true reach_out branch.
    if (router?.branch === "reach_out_fanout") {
      const source = channelLabel(rec.target) || "a source";
      return (
        <>
          <b>Engines also draw on {source} for this query</b> — earn presence there alongside the
          primary play.
        </>
      );
    }
    return (
      <>
        <b>Engines answer from {router?.dominant_source ?? "third-party"} sources QC can't own</b> —
        earn presence instead.
      </>
    );
  }
  if (variant === "inclusion") {
    const opp = rec.detail?.opportunity;
    return (
      <>
        <b>{urlLabel(opp?.url ?? rec.target)}</b> is cited {opp?.citation_count ?? "?"}× and lists{" "}
        {opp?.lists_competitors?.length ?? "several"} rivals — never QC.
        <InfoTip id="inclusion_gate" />
      </>
    );
  }
  if (variant === "build") {
    if (router?.genre_mismatch)
      return <><b>QC's page is the wrong kind for this query</b> — engines reward a different genre here.</>;
    const grouped = router?.grouped_questions?.length ?? 0;
    if (router?.branch === "competitive_pattern") {
      return (
        <>
          <b>QC has no page covering this</b> — competitors keep winning on{" "}
          {router.reason_label?.toLowerCase()} across {grouped} question{grouped === 1 ? "" : "s"}.
        </>
      );
    }
    return (
      <>
        <b>QC has no page {grouped > 1 ? "on this topic" : "for this query"}</b> —{" "}
        {router?.dominant_source === "competitor" ? "rival providers won it with theirs." : `${router?.dominant_source ?? "other"} pages won it.`}
      </>
    );
  }
  return null;
}

function ImplementPopover({ onConfirm, onCancel }) {
  const [date, setDate] = useState(todayISODate());
  return (
    <>
      <span>When did you implement this?</span>
      <div className="rc-track__actions">
        <input
          type="date"
          className="date-input"
          value={date}
          max={todayISODate()}
          onChange={(e) => setDate(e.target.value)}
        />
        <button className="btn btn--primary" onClick={() => onConfirm(date)}>Confirm</button>
        <button className="btn btn--ghost" onClick={onCancel}>✕</button>
      </div>
    </>
  );
}

function TrackBar({ rec, isPopoverOpen, onAccept, onOpenPopover, onCancelPopover, onConfirmImplemented }) {
  if (isPopoverOpen) {
    return (
      <div className="rc-track">
        <ImplementPopover
          onConfirm={(date) => onConfirmImplemented(rec.id, date)}
          onCancel={onCancelPopover}
        />
      </div>
    );
  }

  if (rec.status === "proposed") {
    return (
      <div className="rc-track">
        <span>Not started</span>
        <div className="rc-track__actions">
          <button className="btn btn--ghost" onClick={() => onAccept(rec.id)}>Accept</button>
          <button className="btn btn--primary" onClick={() => onOpenPopover(rec.id)}>✓ Mark implemented</button>
        </div>
      </div>
    );
  }

  if (rec.status === "accepted" || rec.status === "in_progress") {
    return (
      <div className="rc-track">
        <span>{rec.status === "accepted" ? "Accepted — not yet implemented" : "In progress"}</span>
        <div className="rc-track__actions">
          <button className="btn btn--primary" onClick={() => onOpenPopover(rec.id)}>✓ Mark implemented</button>
        </div>
      </div>
    );
  }

  if (rec.status === "implemented" || rec.status === "measuring") {
    const implementedDate = rec.implemented_at ? formatDate(rec.implemented_at) : null;
    const windowDays = rec.measurement_window_days ?? 30;
    const resultDate = rec.implemented_at
      ? formatDate(addDays(rec.implemented_at, Math.max(windowDays - 14, 7)))
      : null;
    return (
      <div className="rc-track">
        <span>
          ● Implemented {implementedDate}
          {rec.metric_impact && ` · measuring ${rec.metric_impact}`}
          {resultDate && ` · result ~${resultDate}`}
          <InfoTip id="measurement" dir="up" />
        </span>
      </div>
    );
  }

  if (rec.status === "validated") {
    return <div className="rc-track rc-track--good">✓ Worked{formatOutcome(rec)}<InfoTip id="measurement" dir="up" /></div>;
  }

  if (rec.status === "failed") {
    return <div className="rc-track rc-track--warn">✗ No lift{formatOutcome(rec)}<InfoTip id="measurement" dir="up" /></div>;
  }

  if (rec.status === "inconclusive") {
    return <div className="rc-track">— Inconclusive · not enough data yet<InfoTip id="measurement" dir="up" /></div>;
  }

  return null;
}

// Tab-1 strategic evidence bars (kept from the previous card).
function StrategicEvidence({ ev }) {
  const max = Math.max(ev.max_count || 0, 1);
  return (
    <div className="tab1ev">
      <span className="tab1ev__eyebrow">
        What AI cites{ev.scope_label ? ` for “${ev.scope_label}”` : " for this topic"}
        <InfoTip id="citations_panel" />
      </span>
      <div className="tab1ev__rows">
        {ev.cited.map((c, i) => (
          <div className="tab1ev__row" key={i}>
            <span className="tab1ev__domain">{c.domain}</span>
            <span className="tab1ev__bar"><i style={{ width: `${(c.count / max) * 100}%` }} /></span>
            <span className="tab1ev__n">{c.count}×</span>
          </div>
        ))}
        <div className="tab1ev__row tab1ev__row--qc">
          <span className="tab1ev__domain">QC (third-party citations)</span>
          <span className="tab1ev__bar"><i style={{ width: `${(ev.qc_citations / max) * 100}%` }} /></span>
          <span className="tab1ev__n">{ev.qc_citations}×</span>
        </div>
      </div>
    </div>
  );
}

function VerdictBand({ rec, variant, onOpenDetail, onTogglePin }) {
  const v = VARIANTS[variant];
  const rank = rec.detail?.priority_rank;
  const tier = rec.detail?.evidence_tier;
  const feas = feasibilityOf(rec);
  return (
    <div className="rc-verdict">
      <span className="rc-verdict__badge">{BADGE_ICONS[variant] ?? BADGE_ICONS.build}{v.badge}</span>
      <p className="rc-verdict__line">{verdictLine(rec, variant)}</p>
      <div className="rc-meta">
        <div className="rc-meta__item">
          <span className="rc-meta__label">Priority<InfoTip id="priority" /></span>
          <span className={`priority-pill priority-pill--${rec.priority}`} title={rank?.reason}>
            {rec.priority}{rank ? ` · #${rank.rank}/${rank.of}` : ""}
          </span>
        </div>
        {rec.effort && (
          <div className="rc-meta__item">
            <span className="rc-meta__label">Effort<InfoTip id="effort" /></span>
            <span className="rc-effort" title={EFFORT_LABELS[rec.effort]}>
              {[1, 2, 3].map((i) => (
                <i key={i} className={i <= (EFFORT_DOTS[rec.effort] ?? 0) ? "on" : ""} />
              ))}
            </span>
          </div>
        )}
        {variant === "fix" && tier && (
          <div className="rc-meta__item">
            <span className="rc-meta__label">Evidence<InfoTip id="evidence_tier" /></span>
            <span
              className={`chip ${tier === "high" ? "chip--open" : "chip--gated"}`}
              title={tier === "high"
                ? "Verified structural gap: most analyzed cited pages share a feature QC's page lacks."
                : "Weaker signal: thin winner sample, sub-threshold gaps, or an LLM-observed pattern — a lead, not a verified gap."}
            >
              {tier === "high" ? "verified gap" : "weak signal"}
            </span>
          </div>
        )}
        {(variant === "reach" || variant === "inclusion") && feas?.feasibility && (
          <div className="rc-meta__item">
            <span className="rc-meta__label">Channel<InfoTip id="channel" /></span>
            <span
              className={`chip ${feas.feasibility === "gated" ? "chip--gated" : "chip--open"}`}
              title={feas.mechanism || feas.evidence}
            >
              {feas.feasibility === "gated" ? "gated — approval" : "open — self-serve"}
            </span>
          </div>
        )}
        {rec.confidence != null && (
          <div className="rc-meta__item">
            <span className="rc-meta__label">Confidence<InfoTip id="confidence" align="right" /></span>
            <span className="rc-conf">
              <i style={{ "--w": `${Math.round(rec.confidence * 100)}%` }} />
              {Math.round(rec.confidence * 100)}%
            </span>
          </div>
        )}
        {onTogglePin && (
          <button
            type="button"
            className={`btn btn--ghost rc-pin ${rec.is_pinned ? "rc-pin--active" : ""}`}
            onClick={() => onTogglePin(rec.id, !rec.is_pinned)}
          >
            {rec.is_pinned ? "★ Pinned" : "☆ Pin"}
          </button>
        )}
        {onOpenDetail && (
          <button className="btn btn--ghost" onClick={() => onOpenDetail(rec.id)}>Open →</button>
        )}
      </div>
    </div>
  );
}

function BodyChips({ rec, variant }) {
  const metricLabel = formatMetric(rec);
  const grouped = rec.detail?.router?.grouped_questions?.length;
  return (
    <div className="rec-card__chips">
      {rec.school && <span className="chip">{rec.school}</span>}
      {rec.segment?.value && (
        <span className="chip chip--segment">{rec.segment.dimension}: {rec.segment.value}</span>
      )}
      {metricLabel && (
        <span className="chip chip--metric">{metricLabel}<InfoTip id="metric_target" /></span>
      )}
      {variant === "build" && grouped > 1 && (
        <span className="chip">{grouped} questions converge here<InfoTip id="grouped_questions" /></span>
      )}
      {rec.outcome?.lift != null && (
        <span
          className={`chip ${rec.outcome.lift >= 0 ? "chip--open" : "chip--gated"}`}
          title={`${rec.metric_impact}: ${Math.round((rec.outcome.baseline_value ?? 0) * 100)}% before → ${Math.round((rec.outcome.post_value ?? 0) * 100)}% after (${rec.outcome.verdict})`}
        >
          lift {rec.outcome.lift >= 0 ? "+" : ""}{Math.round(rec.outcome.lift * 100)}pts · {rec.outcome.verdict}
          <InfoTip id="measurement" />
        </span>
      )}
    </div>
  );
}
function TargetBox({ url }) {
  if (!url) return null;
  return (
    <a className="rc-target-box" href={url} target="_blank" rel="noreferrer">
      <span className="rc-target-box__eyebrow">QC's page</span>
      <span className="rc-target-box__url">{urlLabel(url)}</span>
    </a>
  );
}

function ActionLine({ text }) {
  const parts = text.split("; ").filter(Boolean);
  if (parts.length <= 1) {
    return (
      <p className="rc-body__action">
        <span className="rc-body__arrow">→</span>
        <span>{text}</span>
      </p>
    );
  }
  return (
    <ul className="rc-body__action rc-body__action--list">
      {parts.map((part, i) => (
        <li key={i}>
          <span className="rc-body__arrow">→</span>
          <span>{part}</span>
        </li>
      ))}
    </ul>
  );
}

// Source-question links back to the Prompts tab, shared by every card shape:
// router-provided when routed, else the rec's question segment (R6) so even
// compact and fallback cards can jump to their prompt page.
function SourceQuestions({ rec, onOpenPrompt }) {
  const routed = rec.detail?.router?.source_questions || [];
  const seg = rec.segment;
  const questions = routed.length
    ? routed
    : seg?.dimension === "question" && seg.question_id
      ? [{ question_id: seg.question_id, question: seg.value }]
      : [];
  if (!questions.length || !onOpenPrompt) return null;
  return (
    <div className="rc-module">
      <p className="rc-pane__title">Source questions</p>
      <div className="rc-demand">
        {questions.map((q) => (
          <button
            type="button"
            key={q.question_id}
            className="rc-demand__q"
            onClick={() => onOpenPrompt(q.question_id)}
          >
            <span className="rc-demand__text">{q.question}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

// Build cards justify a content investment: the exact pages to beat.
function BenchmarkModule({ router }) {
  const bench = (router?.winners || []).filter((w) => w.source_type !== "other").slice(0, 2);
  if (!bench.length) return null;
  return (
    <div className="rc-module">
      <p className="rc-pane__title">Benchmark — the pages to beat</p>
      <div className="rc-demand">
        {bench.map((w) => (
          <a className="rc-cite__domain" href={w.url} target="_blank" rel="noreferrer" key={w.url}>
            {urlLabel(w.url)}
          </a>
        ))}
      </div>
    </div>
  );
}

// The router's decision trail is trust/debugging material, not something a
// person fixing the page needs to read every time the checklist above already
// tells them what to do - collapsed by default. The emergent-insight callout
// is explicitly lower-confidence than the verified gaps above it, so it rides
// along in the same collapsed section rather than sitting next to them as if
// it were equally actionable.
function RouterReasoning({ rec, variant, router, sc, expanded, onToggle }) {
  return (
    <div className="rc-pane">
      <button className="rc-more" type="button" onClick={onToggle}>
        {expanded ? "Hide reasoning ▴" : "Show reasoning ▾"}
      </button>
      {expanded && (
        <>
          <p className="rc-pane__title">How the router decided</p>
          <RecTrail rec={rec} variant={variant} />
          {variant === "fix" && (
            <div className="rc-module">
              <RecCitations
                router={router}
                sc={sc}
                title={sc ? `Compared against · ${sc.winners_total} of ${sc.winners_cited_total} cited pages` : undefined}
              />
              {sc && sc.winners_cited_total > sc.winners_total && (
                <p className="rc-cites__note">
                  Coverage: analyzed {sc.winners_total} of {sc.winners_cited_total} cited pages
                  {sc.winners_unreadable?.length ? ` — ${sc.winners_unreadable.length} could not be fetched` : ""}
                  , so "most winners" means most of the analyzed ones.
                </p>
              )}
            </div>
          )}
          {variant === "fix" && sc?.emergent_insight && (
            <div className="rc-insight">
              <span className="rc-insight__tag">◆ LLM-observed pattern · lower confidence</span>
              {sc.emergent_insight}
            </div>
          )}
        </>
      )}
    </div>
  );
}

// onOpenDetail (optional): shows a permalink button that opens this rec's own
// detail page (/recommendations/:id). Omit it on the detail page itself.
export default function RecommendationCard({ rec, isPopoverOpen, onAccept, onOpenPopover, onCancelPopover, onConfirmImplemented, onOpenPrompt, onOpenDetail, onTogglePin }) {
  const [showRaw, setShowRaw] = useState(false);
  const [showReasoning, setShowReasoning] = useState(false);
  const variant = cardVariant(rec);
  const router = rec.detail?.router;
  const sc = rec.detail?.scorecard;
  // When a Content Brief module renders below, it already carries the
  // outline + format spec structured out of `rec.action` - showing the full
  // concatenated string here too would just reproduce the wall of text the
  // brief exists to replace, so lead with its short core action instead.
  const contentBrief = router?.content_brief ?? rec.detail?.concern?.content_brief;
  const actionLine = contentBrief?.action ?? rec.action;

  const trackBar = (
    <TrackBar
      rec={rec}
      isPopoverOpen={isPopoverOpen}
      onAccept={onAccept}
      onOpenPopover={onOpenPopover}
      onCancelPopover={onCancelPopover}
      onConfirmImplemented={onConfirmImplemented}
    />
  );

  // Inclusion opportunities get a compact card: the verified facts are few
  // and strong, and a queue of them shouldn't cost a full card each.
  if (variant === "inclusion") {
    return (
      <div className={`rc ${VARIANTS[variant].cls}`}>
        <VerdictBand rec={rec} variant={variant} onOpenDetail={onOpenDetail} onTogglePin={onTogglePin} />
        <div className="rc-body">
          <ActionLine text={rec.action} />
          {rec.detail?.opportunity?.lists_competitors?.length > 0 && (
            <span className="rc-rivals">
              {rec.detail.opportunity.lists_competitors.map((r) => (
                <span className="rc-rival" key={r}>{r}</span>
              ))}
            </span>
          )}
          <p className="rc-body__note">
            Why we're sure: the inclusion gate reads the fetched page — rivals verifiably listed,
            QC verifiably absent. That's why this card carries high confidence.
          </p>
          <BodyChips rec={rec} variant={variant} />
          <SourceQuestions rec={rec} onOpenPrompt={onOpenPrompt} />
        </div>
        {trackBar}
      </div>
    );
  }

  return (
    <div className={`rc ${VARIANTS[variant].cls}`}>
      <VerdictBand rec={rec} variant={variant} onOpenDetail={onOpenDetail} onTogglePin={onTogglePin} />

      <div className="rc-body">
        {variant === "fix" && <TargetBox url={rec.target} />}
        <p className="rc-body__problem">{problemLine(rec, variant)}</p>
        <ActionLine text={actionLine} />
        {rec.detail?.priority_rank?.reason && (
          <p className="rc-body__note">{rec.detail.priority_rank.reason}</p>
        )}
        <BodyChips rec={rec} variant={variant} />
      </div>

      {router ? (
        <div className={`rc-panes${showReasoning ? "" : " rc-panes--collapsed"}`}>
          <RouterReasoning
            rec={rec}
            variant={variant}
            router={router}
            sc={sc}
            expanded={showReasoning}
            onToggle={() => setShowReasoning(!showReasoning)}
          />
          <div className="rc-pane">
            {variant === "fix" && sc && <FixDiffModule sc={sc} />}
            {variant === "reach" && (
              <>
                <TargetDossier rec={rec} />
                <div className="rc-module">
                  <RecCitations router={router} />
                </div>
              </>
            )}
            {variant === "build" && (
              <>
                {router.content_brief ? (
                  <>
                    <ContentBrief brief={router.content_brief} hideStructure={!!router.page_plan} />
                    {router.page_plan && (
                      <div className="rc-module">
                        <PagePlan plan={router.page_plan} />
                      </div>
                    )}
                    <div className="rc-module">
                      <RecCitations router={router} />
                    </div>
                  </>
                ) : (
                  <RecCitations router={router} />
                )}
                <BenchmarkModule router={router} />
              </>
            )}
            <SourceQuestions rec={rec} onOpenPrompt={onOpenPrompt} />
          </div>
        </div>
      ) : (
        <div className="rc-body">
          {rec.target && <p className="rec-card__target">Target: {rec.target}</p>}
          {rec.detail?.concern?.content_brief && (
            <ContentBrief brief={rec.detail.concern.content_brief} />
          )}
          {rec.detail?.evidence && <StrategicEvidence ev={rec.detail.evidence} />}
          <SourceQuestions rec={rec} onOpenPrompt={onOpenPrompt} />
        </div>
      )}

      {rec.evidence && (
        <div className="rc-body">
          <button className="rc-more" type="button" onClick={() => setShowRaw(!showRaw)}>
            {showRaw ? "Hide raw evidence ▴" : "Show raw evidence ▾"}
          </button>
          {showRaw && <p className="rec-card__evidence">{rec.evidence}</p>}
        </div>
      )}

      {trackBar}
    </div>
  );
}
