// Card identity per variant, shared between RecommendationCard (full card)
// and RecRow (condensed question-group row). Inclusion shares the reach
// (green) identity — it's the outreach stream's high-confidence sub-type.
export const VARIANTS = {
  fix: { cls: "rc--fix", badge: "Fix page" },
  reach: { cls: "rc--reach", badge: "Reach out" },
  inclusion: { cls: "rc--reach", badge: "Get listed" },
  build: { cls: "rc--build", badge: "Build" },
  generic: { cls: "rc--build", badge: "Strategy" },
};

export const BADGE_ICONS = {
  fix: (
    <svg viewBox="0 0 12 12" width="12" height="12" fill="currentColor" aria-hidden="true">
      <path d="M10.5 3.9L8.1 1.5a3.2 3.2 0 00-4 4L1 8.6V11h2.4l3.1-3.1a3.2 3.2 0 004-4zM6.3 5.7a1.7 1.7 0 112.4-2.4z" />
    </svg>
  ),
  reach: (
    <svg viewBox="0 0 12 12" width="12" height="12" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round" aria-hidden="true">
      <path d="M11 1L5.5 6.5M11 1L7.5 11l-2-4.5L1 4.5z" />
    </svg>
  ),
  inclusion: (
    <svg viewBox="0 0 12 12" width="12" height="12" fill="currentColor" aria-hidden="true">
      <path d="M2 2h8v2H2zm0 3h8v2H2zm0 3h5v2H2z" />
    </svg>
  ),
  build: (
    <svg viewBox="0 0 12 12" width="12" height="12" fill="currentColor" aria-hidden="true">
      <path d="M6 1l5 4v6H7V8H5v3H1V5z" />
    </svg>
  ),
};
