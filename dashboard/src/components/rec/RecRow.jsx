import { cardVariant, channelLabel, bucketLabel, STATUS_LABELS } from "../../lib/recview";
import { VARIANTS, BADGE_ICONS } from "./variantMeta";

// A single-line summary of what the full RecommendationCard would show.
// Clicking it navigates to the rec's own /recommendations/:id detail page
// (rather than expanding a full card in place) - so the list itself never
// grows taller the more of them you look at, and this only needs to convey
// enough to decide whether it's worth opening: which channel, how confident,
// whether it's gated.
export default function RecRow({ rec, onOpenDetail, onTogglePin }) {
  const variant = cardVariant(rec);
  const label = channelLabel(rec.target);
  const isReddit = label.startsWith("r/");
  const winner = (rec.detail?.router?.winners || []).find((w) => w.url === rec.target);
  const bucket = !isReddit && winner?.source_type ? bucketLabel(winner.source_type) : null;
  const feas = rec.detail?.outreach_feasibility ?? rec.detail?.router?.outreach_feasibility;
  const statusLabel = STATUS_LABELS[rec.status];

  return (
    <div
      className="rec-row"
      role="button"
      tabIndex={0}
      onClick={() => onOpenDetail(rec.id)}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onOpenDetail(rec.id);
        }
      }}
    >
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
      {onTogglePin && (
        <button
          type="button"
          className={`rec-row__pin ${rec.is_pinned ? "rec-row__pin--active" : ""}`}
          aria-label={rec.is_pinned ? "Unpin" : "Pin"}
          title={rec.is_pinned ? "Remove from Pinned" : "Add to Pinned"}
          onClick={(e) => {
            e.stopPropagation();
            onTogglePin(rec.id, !rec.is_pinned);
          }}
        >
          {rec.is_pinned ? "★" : "☆"}
        </button>
      )}
      <span className="rec-row__chevron">→</span>
    </div>
  );
}
