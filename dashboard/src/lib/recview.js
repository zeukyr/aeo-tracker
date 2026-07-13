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
