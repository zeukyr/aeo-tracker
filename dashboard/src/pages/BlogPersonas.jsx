import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { API_BASE_URL } from "../config";
import { formatDate } from "../lib/format";
import { apiSchool } from "../lib/blogIdeas";
import { SCHOOL_OPTIONS } from "../context/FilterContextConstants";

// Schools a persona can be saved for - every real school plus "General";
// "All" isn't a single school so it's excluded here.
const PERSONA_EDITABLE_SCHOOLS = SCHOOL_OPTIONS.filter((s) => s !== "All");

// The three saved categories, in the order they're shown/used - ideation
// draws on all three, but full-post drafting deliberately excludes
// testimonials (see blog_ideas.py's _format_persona).
const PERSONA_FIELDS = [
  {
    key: "buyer_persona",
    icon: "🎯",
    label: "Buyer persona",
    hint: "Who they are: archetypes, demographics, what they're buying, how they research, what they fear.",
    placeholder: "e.g. \"Persona A - The Aspiring Entrepreneur: age 21-39, strong creative background but no formal business experience...\"",
    accept: ".md,.txt",
  },
  {
    key: "stats",
    icon: "📊",
    label: "Stats / original data",
    hint: "Survey results, demographics, and behavioral data - cited as original-data support instead of a generic claim.",
    placeholder: "e.g. \"56% of students want to start their own business - the largest single motivation.\"",
    accept: ".xlsx",
  },
  {
    key: "testimonials",
    icon: "💬",
    label: "Testimonials",
    hint: "Named student quotes or case-study snippets. Used for idea angles only - never in a drafted full post.",
    placeholder: "e.g. \"Carisa Lockery - Owner of Pink Olive Events: 'It was a great experience and really helped guide the process...'\"",
    accept: ".md,.txt",
  },
];
const EMPTY_PERSONA_FIELDS = { buyer_persona: "", stats: "", testimonials: "" };

const wordCount = (text) => (text.trim() ? text.trim().split(/\s+/).length : 0);

const fieldsFrom = (entry) => ({
  buyer_persona: entry?.buyer_persona ?? "",
  stats: entry?.stats ?? "",
  testimonials: entry?.testimonials ?? "",
});

// Grows to fit its content instead of scrolling internally - the actual
// complaint this fixes is a small fixed-height box making a few hundred
// words of pasted persona/testimonial text unreadable without scrolling
// inside it. CSS max-height + overflow-y (index.css) still caps it for the
// rare pathological paste, so the page itself doesn't turn into one
// enormous field. Recalculates on every value change, not just user
// keystrokes, so a school switch or a file-upload extraction (both set
// `value` programmatically) resize it too.
function AutoGrowTextarea({ value, ...props }) {
  const ref = useRef(null);

  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${el.scrollHeight}px`;
  }, [value]);

  return <textarea ref={ref} value={value} {...props} />;
}

// Hidden native file input behind a styled label, plus a small inline
// status line - one per category box, since each accepts a different file
// type (.xlsx for stats, .md/.txt for the other two - see
// blog_persona_extract.py). Extraction replaces that box's text outright
// rather than appending, so it confirms first if the box isn't empty.
function PersonaFileUpload({ fieldKey, accept, hasContent, onExtracted }) {
  const [status, setStatus] = useState(null);
  const inputId = `persona-upload-${fieldKey}`;

  const handleChange = (e) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    if (hasContent && !window.confirm(`Replace the current text with the contents of "${file.name}"?`)) {
      return;
    }
    setStatus({ kind: "loading", text: "Extracting…" });
    const body = new FormData();
    body.append("file", file);
    fetch(`${API_BASE_URL}/api/blog-personas/extract`, { method: "POST", body })
      .then(async (r) => {
        const data = await r.json();
        if (!r.ok) throw new Error(data?.detail || "Extraction failed");
        return data;
      })
      .then((data) => {
        onExtracted(data.text);
        setStatus({ kind: "success", text: `Loaded ${file.name}` });
      })
      .catch((err) => setStatus({ kind: "error", text: err.message }));
  };

  return (
    <span className="persona-field__upload">
      <label htmlFor={inputId} className="btn btn--ghost persona-field__upload-btn">
        📎 Upload {accept}
      </label>
      <input id={inputId} type="file" accept={accept} onChange={handleChange} hidden />
      {status && (
        <span className={`candidate-row__result candidate-row__result--${status.kind === "success" ? "success" : status.kind === "error" ? "error" : "generating"}`}>
          {status.text}
        </span>
      )}
    </span>
  );
}

// Standalone page (own URL, /blog-ideas/personas) for editing the
// buyer-persona/stats/testimonials input that blog idea generation reads
// instead of a hardcoded knowledge file (see migrations/013_blog_personas.sql,
// migrations/014_blog_personas_categories.sql). Linked from the Blog Ideas
// tab rather than inlined there - this is settings-like content edited
// occasionally per school, not something that needs to sit in the middle of
// the generation flow.
export default function BlogPersonas() {
  const navigate = useNavigate();
  const [personas, setPersonas] = useState([]);
  const [loaded, setLoaded] = useState(false);
  const [selectedSchool, setSelectedSchool] = useState(PERSONA_EDITABLE_SCHOOLS[0]);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState(null);

  const loadPersonas = () => {
    fetch(`${API_BASE_URL}/api/blog-personas`)
      .then((r) => r.json())
      .then((data) => setPersonas(Array.isArray(data) ? data : []))
      .catch(() => {})
      .finally(() => setLoaded(true));
  };

  useEffect(loadPersonas, []);

  const existing = personas.find((p) => p.school === apiSchool(selectedSchool));
  const [fields, setFields] = useState(() => fieldsFrom(existing));

  // Reset the boxes whenever the selected school changes, or the initial
  // fetch finishes for the still-selected default school - adjusting state
  // during render (React's recommended pattern for this) rather than in a
  // useEffect, since this only needs to react to those two things, not to
  // every personas update (e.g. right after this page's own save). Without
  // the `loaded` half of the key, the boxes for the default-selected school
  // would stay blank forever: the initial `fields` state is captured before
  // the fetch resolves, and a plain selectedSchool-only key never fires
  // again once that fetch lands on the same school.
  const resetKey = `${selectedSchool}::${loaded}`;
  const [prevResetKey, setPrevResetKey] = useState(resetKey);
  if (resetKey !== prevResetKey) {
    setPrevResetKey(resetKey);
    setFields(fieldsFrom(existing));
    setMessage(null);
  }

  const isBlank = Object.values(fields).every((v) => !v.trim());

  const handleSave = () => {
    setSaving(true);
    setMessage(null);
    fetch(`${API_BASE_URL}/api/blog-personas`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ school: apiSchool(selectedSchool), ...fields }),
    })
      .then((r) => {
        if (!r.ok) throw new Error("Save failed");
        return r.json();
      })
      .then(() => {
        setSaving(false);
        setMessage(isBlank ? "Cleared." : "Saved.");
        loadPersonas();
      })
      .catch((err) => {
        setSaving(false);
        setMessage(err.message);
      });
  };

  return (
    <div className="rec-page">
      <div className="card rec-header">
        <div>
          <button className="btn btn--ghost" onClick={() => navigate("/blog-ideas")}>
            ← Back to Blog Ideas
          </button>
          <p className="panel-title">Buyer Persona, Stats & Testimonials</p>
          <p className="rec-header__meta">
            {loaded
              ? `${personas.length} school${personas.length === 1 ? "" : "s"} configured`
              : "Loading…"}
            {" "}— used to ground blog idea generation instead of inventing generic claims
          </p>
        </div>
      </div>

      <div className="card">
        <div className="persona-editor__head">
          <div className="persona-editor__school">
            <label htmlFor="persona-school-select">Editing</label>
            <select
              id="persona-school-select"
              className="text-sm border border-gray-200 rounded px-3 py-1.5"
              value={selectedSchool}
              onChange={(e) => setSelectedSchool(e.target.value)}
            >
              {PERSONA_EDITABLE_SCHOOLS.map((s) => (
                <option key={s} value={s}>
                  {s}{personas.some((p) => p.school === apiSchool(s)) ? " ✓" : ""}
                </option>
              ))}
            </select>
          </div>
          {existing?.updated_at && (
            <span className="candidate-row__meta">last updated {formatDate(existing.updated_at)}</span>
          )}
        </div>

        <div className="persona-fields">
          {PERSONA_FIELDS.map(({ key, icon, label, hint, placeholder, accept }) => (
            <div className="persona-field" key={key}>
              <div className="persona-field__head">
                <span className="persona-field__icon">{icon}</span>
                <span className="persona-field__label">{label}</span>
                <PersonaFileUpload
                  fieldKey={key}
                  accept={accept}
                  hasContent={!!fields[key].trim()}
                  onExtracted={(text) => setFields((prev) => ({ ...prev, [key]: text }))}
                />
              </div>
              <p className="persona-field__hint">{hint}</p>
              <AutoGrowTextarea
                value={fields[key]}
                onChange={(e) => setFields((prev) => ({ ...prev, [key]: e.target.value }))}
                rows={4}
                placeholder={placeholder}
              />
              <p className="persona-field__count">{wordCount(fields[key])} words</p>
            </div>
          ))}
        </div>

        <div className="candidate-panel__actions" style={{ position: "static", marginTop: 16 }}>
          <span className="candidate-row__result candidate-row__result--success">{message}</span>
          <span style={{ display: "flex", gap: 8 }}>
            <button className="btn btn--ghost" onClick={() => setFields({ ...EMPTY_PERSONA_FIELDS })} disabled={saving || isBlank}>
              Clear
            </button>
            <button className="btn btn--primary" onClick={handleSave} disabled={saving}>
              {saving ? "Saving…" : "Save"}
            </button>
          </span>
        </div>
      </div>
    </div>
  );
}
