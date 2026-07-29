import { cardVariant, channelLabel, bucketLabel } from "../../lib/recview";
import { VARIANTS, BADGE_ICONS } from "./variantMeta";

const STATUS_LABELS = {
  accepted: "Accepted",
  in_progress: "In progress",
  implemented: "Implemented",
  measuring: "Measuring",
  validated: "Worked",
  failed: "No lift",
  inconclusive: "Inconclusive",
};

// One channel option inside a QuestionGroup - a single-line summary of what a
// full RecommendationCard would show. Clicking it expands that full card in
// place (see QuestionGroup), so this only needs to convey enough to decide
// whether it's worth opening: which channel, how confident, whether it's gated.
export default function RecRow({ rec, onToggleExpand }) {
  const variant = cardVariant(rec);
  const label = channelLabel(rec.target);
  const isReddit = label.startsWith("r/");
  const winner = (rec.detail?.router?.winners || []).find((w) => w.url === rec.target);
  const bucket = !isReddit && winner?.source_type ? bucketLabel(winner.source_type) : null;
  const feas = rec.detail?.outreach_feasibility ?? rec.detail?.router?.outreach_feasibility;
  const statusLabel = STATUS_LABELS[rec.status];

  return (
    <button type="button" className="rec-row" onClick={() => onToggleExpand(rec.id)}>
      <span className="rec-row__badge">{BADGE_ICONS[variant] ?? BADGE_ICONS.build}{VARIANTS[variant]?.badge}</span>
      <span className="rec-row__target">
        {label}
        {bucket && <span className="rec-row__bucket"> ({bucket})</span>}
      </span>
      <span className="rec-row__meta">
        {statusLabel && <span className="rec-row__status">{statusLabel}</span>}
        <span className={`priority-pill priority-pill--${rec.priority}`}>{rec.priority}</span>
        {rec.confidence != null && <span>{Math.round(rec.confidence * 100)}% conf</span>}
        {feas?.feasibility === "gated" && <span className="chip chip--gated">gated</span>}
      </span>
      <span className="rec-row__chevron">▾</span>
    </button>
  );
}
