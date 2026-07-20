import { useState } from "react";
import InfoTip from "../InfoTip";

// Feature-diff matrix for fix cards: rows from detail.scorecard.features,
// gap rows (recommend=true) first and flagged. Prevalence renders as a dot
// strip — n of N analyzed winners — so "most" is countable at a glance.
// Default view shows ONLY verified gaps (recommend=true) - "below bar" and
// parity rows are noise once there's a real gap to act on, so both sit behind
// one toggle. Nothing is discarded: the full row set (and the full metric_rows
// set below) is always in `sc`, just collapsed by default.

const MAX_DOTS = 10;
const COLLAPSED_ROWS = 6;

function PrevDots({ present, total }) {
  const shown = Math.min(total, MAX_DOTS) || 0;
  const on = total > 0 ? Math.round((present / total) * shown) : 0;
  return (
    <span className="rc-prevdots" aria-hidden="true">
      {Array.from({ length: shown }, (_, i) => (
        <i key={i} className={i < on ? "on" : ""} />
      ))}
    </span>
  );
}

// Formats a ratio feature's value/target for display ("17%" / "3 levels").
function fmtMetric(value, unit) {
  return unit === "pct" ? `${value}%` : `${value} level${value === 1 ? "" : "s"}`;
}

function MetricRows({ metricRows }) {
  const [expanded, setExpanded] = useState(false);
  if (!metricRows?.length) return null;

  const ordered = [...metricRows].sort((a, b) => (a.recommend ? 0 : 1) - (b.recommend ? 0 : 1));
  const gapRows = ordered.filter((r) => r.recommend).length;
  // Same default-hide rule as the feature-diff table above: only measured-out-
  // of-range metrics show by default; in-range ones are stored data, not noise
  // the reader needs by default, so they sit behind the same kind of toggle.
  const rows = expanded ? ordered : ordered.slice(0, gapRows);
  const hidden = ordered.length - gapRows;

  return (
    <div style={{ marginTop: 14 }}>
      <p className="rc-pane__title">
        Structural metrics vs. GEO citation-research targets
        <InfoTip id="metric_rows_table" />
      </p>
      {rows.length > 0 && (
        <div className="rc-diff-scroll">
          <table className="rc-diff">
            <thead>
              <tr><th>Metric</th><th>GEO</th><th>Target</th><th>QC</th><th></th></tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id} className={r.recommend ? "rc-gap" : ""}>
                  <td>{r.label}</td>
                  <td><span className={`rc-geo rc-geo--${r.geo_weight}`}>{r.geo_weight}</span></td>
                  <td className="rc-frac">
                    {r.target_min}-{r.target_max}{r.unit === "pct" ? "%" : " levels"}
                  </td>
                  <td>
                    <span className={r.in_range ? "rc-mark rc-mark--yes" : "rc-mark rc-mark--no"}>
                      {r.qc_value === null ? "—" : fmtMetric(r.qc_value, r.unit)}
                    </span>
                  </td>
                  <td>
                    {r.recommend ? (
                      <span className="rc-gapflag">out of range</span>
                    ) : (
                      <span className="rc-belowbar">{r.qc_value === null ? "—" : "in range"}</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {hidden > 0 && (
        <button className="rc-more" type="button" onClick={() => setExpanded(!expanded)}>
          {expanded
            ? "Hide in-range metrics ▴"
            : `Show ${hidden} more measured metric${hidden === 1 ? "" : "s"} (in range) ▾`}
        </button>
      )}
    </div>
  );
}

export default function FixDiffModule({ sc }) {
  const [expanded, setExpanded] = useState(false);
  const features = sc.features || [];
  // verified gaps first, then below-bar gaps, then parity rows
  const rank = (f) => (f.recommend ? 0 : !f.qc_has && f.winners_present > 0 ? 1 : 2);
  const ordered = [...features].sort((a, b) => rank(a) - rank(b));
  // Default view: only verified gaps (rank 0). Below-bar and parity rows both
  // collapse behind the toggle - once there's a real gap, "below bar" isn't
  // actionable enough to earn default screen space. Falls back to a small
  // context window when there's no verified gap at all (a low-tier/parity
  // card), so the table isn't empty.
  const gapRows = ordered.filter((f) => f.recommend).length;
  const visibleRows = gapRows > 0 ? gapRows : COLLAPSED_ROWS;
  const rows = expanded ? ordered : ordered.slice(0, visibleRows);
  const hidden = ordered.length - visibleRows;

  return (
    <div>
      <p className="rc-pane__title">
        Feature diff — QC page vs cited field
        <InfoTip id="feature_diff_table" />
      </p>
      <div className="rc-diff-scroll">
        <table className="rc-diff">
          <thead>
            <tr><th>Feature</th><th>GEO</th><th>Cited pages</th><th>QC</th><th></th></tr>
          </thead>
          <tbody>
            {rows.map((f) => (
              <tr key={f.id ?? f.label} className={f.recommend ? "rc-gap" : ""}>
                <td>{f.label}</td>
                <td><span className={`rc-geo rc-geo--${f.geo_weight}`}>{f.geo_weight}</span></td>
                <td>
                  <PrevDots present={f.winners_present} total={f.winners_total} />
                  <span className="rc-frac">{f.winners_present}/{f.winners_total}</span>
                </td>
                <td>
                  <span className={f.qc_has ? "rc-mark rc-mark--yes" : "rc-mark rc-mark--no"}>
                    {f.qc_has ? "✓" : "✗"}
                  </span>
                </td>
                <td>
                  {f.recommend ? (
                    <span className="rc-gapflag">+ Add</span>
                  ) : !f.qc_has && f.winners_present > 0 ? (
                    <span className="rc-belowbar">below bar</span>
                  ) : (
                    <span className="rc-belowbar">—</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {hidden > 0 && (
        <button className="rc-more" type="button" onClick={() => setExpanded(!expanded)}>
          {expanded
            ? "Hide below-bar & parity features ▴"
            : `Show ${hidden} more feature${hidden === 1 ? "" : "s"} (below bar / at parity) ▾`}
        </button>
      )}

      <MetricRows metricRows={sc.metric_rows} />

      {sc.suggested_edits?.length > 0 && (
        <div className="rc-edits">
          <p className="rc-pane__title" style={{ margin: "0 0 2px" }}>Suggested edits</p>
          {sc.suggested_edits.map((e, i) => (
            <div className="rc-edit" key={i}><b>+</b><span>{e}</span></div>
          ))}
        </div>
      )}

      {sc.emergent_insight && (
        <div className="rc-insight">
          <span className="rc-insight__tag">◆ LLM-observed pattern · lower confidence</span>
          {sc.emergent_insight}
        </div>
      )}
    </div>
  );
}
