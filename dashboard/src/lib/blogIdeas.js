// Shared between the Blog Ideas list (tabs/BlogIdeas.jsx) and the per-idea
// detail page (pages/BlogIdeaDetail.jsx) — kept in one place so the two
// don't drift on angle labels or the (topic, school) composite-key format.

export const ANGLE_LABELS = {
  definition: "definition",
  how_to: "how_to",
  comparison: "comparison",
  case_study: "case_study",
  faq: "faq",
  advanced_technique: "advanced_technique",
  tool_framework: "tool_framework",
  benchmark: "benchmark",
};

export const schoolLabel = (school) => school ?? "General";

// The Blog Ideas tab's persona editor works in UI school labels ("General",
// "QC Pet Studies", ...) from SCHOOL_OPTIONS, but the API and blog_ideas
// candidate rows use the raw DB value (null for General). Keep the
// translation in one place so the editor and the "persona data" chip agree.
export const apiSchool = (uiSchool) => (uiSchool === "General" ? null : uiSchool);

// Candidate rows are keyed by (topic, school) since topic alone isn't a
// unique group anymore (see migrations/011_blog_ideas_school.sql).
export const keyOf = (topic, school) => `${topic}||${school ?? ""}`;

export const parseKey = (key) => {
  const idx = key.indexOf("||");
  const topic = key.slice(0, idx);
  const rawSchool = key.slice(idx + 2);
  return { topic, school: rawSchool === "" ? null : rawSchool };
};
