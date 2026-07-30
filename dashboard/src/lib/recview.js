// Shared helpers for the per-type recommendation card (rc-*).

export const OUTREACH_ACTION_TYPES = ["outreach", "citation", "community"];

// Which card anatomy a rec gets: fix | reach | inclusion | build | generic.
// "generic" = no router detail (concern-engine / credibility recs) — those
// fall back to the flat evidence layout.
export function cardVariant(rec) {
  const stream =
    rec.work_stream ??
    (rec.action_type === "technical"
      ? "on_page"
      : OUTREACH_ACTION_TYPES.includes(rec.action_type)
        ? "outreach"
        : "strategic");
  if (stream === "on_page") return "fix";
  if (stream === "outreach")
    return rec.detail?.router?.branch === "inclusion_opportunity" ? "inclusion" : "reach";
  return rec.detail?.router ? "build" : "generic";
}

// "www.example.com/some/path/" -> "example.com/some/path"
export function urlLabel(url) {
  if (!url) return "";
  try {
    const u = new URL(url);
    const path = u.pathname === "/" ? "" : u.pathname.replace(/\/$/, "");
    return u.hostname.replace(/^www\./, "") + path;
  } catch {
    return url;
  }
}

export function domainOf(url) {
  if (!url) return "";
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

// "https://reddit.com/r/wedding/comments/..." -> "r/wedding"; anything else -> its domain.
const REDDIT_SUB = /reddit\.com\/r\/([^/?#]+)/i;
export function channelLabel(url) {
  const m = REDDIT_SUB.exec(url || "");
  return m ? `r/${m[1]}` : domainOf(url);
}

export const pctLabel = (x) => (x == null ? "—" : `${Math.round(x * 100)}%`);

// source_type bucket → color token. The set is CVD-validated as a group;
// every use pairs the color with a text label, never color alone.
const BUCKET_COLOR = {
  competitor: "var(--bucket-competitor)",
  editorial: "var(--bucket-editorial)",
  ugc: "var(--bucket-ugc)",
  reference: "var(--bucket-reference)",
  certifying_body: "var(--bucket-certifying)",
  review: "var(--bucket-review)",
  other: "var(--bucket-abstain)",
};
export const bucketColor = (b) => BUCKET_COLOR[b] ?? "var(--bucket-abstain)";
export const bucketLabel = (b) =>
  b === "certifying_body" ? "certifying" : b === "other" ? "abstained" : (b ?? "unknown");

// A rec's own outreach_feasibility (reach-branch primary) or its router's
// (inclusion/fan-out companions, which share the parent route's feasibility
// read) - whichever is present.
export const feasibilityOf = (rec) =>
  rec.detail?.outreach_feasibility ?? rec.detail?.router?.outreach_feasibility;

export const STATUS_LABELS = {
  accepted: "Accepted",
  in_progress: "In progress",
  implemented: "Implemented",
  measuring: "Measuring",
  validated: "Worked",
  failed: "No lift",
  inconclusive: "Inconclusive",
};
