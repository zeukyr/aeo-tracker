import { useState } from "react";
import InfoTip from "../InfoTip";

// Feature-diff matrix for fix cards: rows from detail.scorecard.features,
// gap rows (recommend=true) first and flagged. Prevalence renders as a dot
// strip — n of N analyzed winners — so "most" is countable at a glance.
// Collapsing must never hide a gap: every row where QC lacks a feature some
// winner has stays visible; only parity rows sit behind the toggle.

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

export default function FixDiffModule({ sc }) {
  const [expanded, setExpanded] = useState(false);
  const features = sc.features || [];
  // verified gaps first, then below-bar gaps, then parity rows
  const rank = (f) => (f.recommend ? 0 : !f.qc_has && f.winners_present > 0 ? 1 : 2);
  const ordered = [...features].sort((a, b) => rank(a) - rank(b));
  const gapRows = ordered.filter((f) => rank(f) < 2).length;
  const visibleRows = Math.max(gapRows, COLLAPSED_ROWS);
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
            ? "Hide parity features ▴"
            : `Show ${hidden} more feature${hidden === 1 ? "" : "s"} where QC is at parity ▾`}
        </button>
      )}

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
