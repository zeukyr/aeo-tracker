// Shared between the Blog Ideas list (tabs/BlogIdeas.jsx) and the per-idea
// detail page (pages/BlogIdeaDetail.jsx) — kept in one place so the two
// don't drift on angle labels or the (topic, school) composite-key format.

export const ANGLE_LABELS = {
  definition: "Definition / Explainer",
  how_to: "How-To Guide",
  comparison: "Comparison",
  case_study: "Case Study",
  faq: "FAQ",
  advanced_technique: "Advanced Technique",
  tool_framework: "Tool / Framework Guide",
  benchmark: "Benchmark",
};

// "high"/"medium"/"low" -> the same label/color vocabulary priority-pill
// already uses elsewhere (dashboard/src/index.css) - blog_ideas.py computes
// this deterministically from real target-query volume/weakness, never an
// LLM-assigned label.
export const PRIORITY_LABELS = { high: "High", medium: "Medium", low: "Low" };

export const schoolLabel = (school) => school ?? "General";

// The Blog Ideas tab's persona editor works in UI school labels ("General",
// "QC Pet Studies", ...) from SCHOOL_OPTIONS, but the API and blog_ideas
// candidate rows use the raw DB value (null for General). Keep the
// translation in one place so the editor and the "persona data" chip agree.
export const apiSchool = (uiSchool) => (uiSchool === "General" ? null : uiSchool);
