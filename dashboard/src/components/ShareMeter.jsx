import { bucketColor, bucketLabel, formatColor, formatLabel } from "../lib/recview";

// 100%-stacked share meter, optionally with a dominance-threshold bar drawn
// on it (VoteMeter's 60% bar; FormatMeter has no such threshold - format_gap
// is a plurality+margin rule, not a fixed share). Shared by RecTrail's "how
// the router decided" panel and QuestionDetail's Cited URLs panel, so both
// surfaces read the same source_type/format breakdown the same way.
export function ShareMeter({ entries, colorFn, labelFn, thresholdPct, ariaPrefix }) {
  const total = entries.reduce((s, [, n]) => s + n, 0);
  if (!total || entries.length === 0) return null;
  return (
    <div>
      <div className="rc-anchor">
        {thresholdPct != null && (
          <span className="rc-anchor__label" style={{ left: `${thresholdPct}%` }}>{thresholdPct}% bar</span>
        )}
        <div
          className="rc-meter"
          role="img"
          aria-label={`${ariaPrefix}: ${entries.map(([k, n]) => `${labelFn(k)} ${n}`).join(", ")}`}
        >
          {entries.map(([k, n]) => (
            <i key={k} style={{ width: `${(n / total) * 100}%`, background: colorFn(k) }} />
          ))}
        </div>
        {thresholdPct != null && <span className="rc-anchor__tick" style={{ left: `${thresholdPct}%` }} />}
      </div>
      <div className="rc-meter-legend">
        {entries.map(([k, n]) => (
          <span key={k}>
            <i className="rc-dot" style={{ background: colorFn(k) }} />
            {labelFn(k)} {n}
          </span>
        ))}
      </div>
    </div>
  );
}

// source_type vote, citation-weighted, sorted by share - mirrors
// source_votes()'s own citation-weighting on the backend.
export function VoteMeter({ vote }) {
  const buckets = Object.entries(vote?.buckets || {}).sort((a, b) => b[1] - a[1]);
  return (
    <ShareMeter
      entries={buckets} colorFn={bucketColor} labelFn={bucketLabel}
      thresholdPct={60} ariaPrefix="Vote"
    />
  );
}

// Format mix of a set of cited pages, counted BY PAGE (not citation-weighted)
// - deliberately unlike VoteMeter. This has to match the "N/M pages are
// format X" figures the router's own prose quotes (format_gap,
// _secondary_ownable_signal), and both of those tally plain per-page
// Counters, not citation counts - a citation-weighted chart here would show
// different proportions (even a different leader) than the number printed
// next to it. Unclassified pages (format null) abstain from the tally the
// same way they abstain from the source-type vote, rather than showing as a
// slice. `pages` just needs {format} per entry - both router winners and
// QuestionDetail's citation rows already have that shape.
export function FormatMeter({ pages }) {
  const tally = {};
  for (const p of pages || []) {
    if (!p.format) continue;
    tally[p.format] = (tally[p.format] || 0) + 1;
  }
  const entries = Object.entries(tally).sort((a, b) => b[1] - a[1]);
  return <ShareMeter entries={entries} colorFn={formatColor} labelFn={formatLabel} ariaPrefix="Format mix" />;
}
