import { METRIC_INFO } from "../lib/metricInfo";

// Small ⓘ affordance that explains a metric on hover/focus in 1-2 sentences.
// Copy lives in lib/metricInfo.js so every surface showing the same metric
// shares one explanation.
//
// Placement props (rec cards have overflow:hidden, so the pop must open
// toward the card's interior):
//   dir="down" (default) — pop below the icon; use anywhere near a card top.
//   dir="up"             — pop above; for bottom-of-card rows (track bar).
//   align="left" (default) | "center" | "right" — which edge hugs the icon.
export default function InfoTip({ id, dir = "down", align = "left" }) {
  const info = METRIC_INFO[id];
  if (!info) return null;
  return (
    <span className={`infotip infotip--${dir} infotip--${align}`}>
      <button type="button" className="infotip__btn" aria-label={`About: ${info.label}`}>
        i
      </button>
      <span className="infotip__pop" role="tooltip">
        <b className="infotip__title">{info.label}</b>
        <span className="infotip__text">{info.text}</span>
      </span>
    </span>
  );
}
