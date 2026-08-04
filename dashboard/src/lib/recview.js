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

// winner_format bucket -> short display label. Orthogonal to source_type:
// source_type says who owns the slot, format says what kind of page it is.
const FORMAT_LABEL = {
  how_to: "how-to guide",
  long_form: "blog / long-form",
  listicle: "listicle",
  landing: "landing page",
};
export const formatLabel = (f) => FORMAT_LABEL[f] ?? "unclassified";

// format -> color token. A separate 4-color set from BUCKET_COLOR above,
// validated together (not just adjacent-pair) since callers sort by count -
// any two can end up next to each other. Always paired with a text label.
const FORMAT_COLOR = {
  how_to: "var(--format-how-to)",
  long_form: "var(--format-long-form)",
  listicle: "var(--format-listicle)",
  landing: "var(--format-landing)",
};
export const formatColor = (f) => FORMAT_COLOR[f] ?? "var(--bucket-abstain)";

// Topics whose questions are branded/reputation-framed ("what do people
// think of QC", "QC vs rival X") - mirrors REPUTATION_TOPICS in
// api/queries/question_router.py. Every other topic is an unbranded category
// question ("how to become a dog trainer"), where engines citing the broader
// field instead of QC-specific pages is the expected result, not a mismatch.
const REPUTATION_TOPICS = new Set(["Brand Credibility", "Competitor Comparison"]);
export const isUnbrandedTopic = (topic) => !!topic && !REPUTATION_TOPICS.has(topic);

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
