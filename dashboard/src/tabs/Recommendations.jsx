import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { API_BASE_URL } from "../config";
import { useFilter } from "../context/useFilter";
import RecommendationCard from "../components/RecommendationCard";
import { formatDate } from "../lib/format";

// Statuses that count as "committed work" - immune to being superseded by a
// new batch, and shown in the Active section regardless of which batch they
// came from. Must match ACTIVE_STATUSES in api/queries/recommendations_synthesis.py.
const ACTIVE_STATUSES = [
  "accepted", "in_progress", "implemented",
  "measuring", "validated", "failed", "inconclusive",
];

// The three work-streams (question-router plan §5.8), one per router branch.
// Which tab a rec lands in comes from the API (work_stream, derived from
// action_type); streamOf falls back for older payloads.
const WORK_STREAMS = [
  {
    key: "strategic",
    label: "Strategic Growth",
    question: "What don't we have?",
    note: "For marketing / leadership — build the owned content AI engines reward but QC lacks.",
  },
  {
    key: "on_page",
    label: "Improve Existing Pages",
    question: "Why isn't AI using our page?",
    note: "For the web / content team — the page exists but engines skip it. Fix the page, not the footprint.",
  },
  {
    key: "outreach",
    label: "Outreach & Earn",
    question: "Where does AI look that we can't own?",
    note: "For PR / partnerships / community — earn presence on the third-party sources engines cite. Each card shows whether a channel exists (open / requires approval).",
  },
];

const OUTREACH_ACTION_TYPES = ["outreach", "citation", "community"];
const streamOf = (rec) =>
  rec.work_stream ??
  (rec.action_type === "technical"
    ? "on_page"
    : OUTREACH_ACTION_TYPES.includes(rec.action_type)
      ? "outreach"
      : "strategic");

// Match a rec against the global school filter. Recs tagged "both" apply to any
// specific school; unscoped recs (no school) show only under "All"/"General".
function matchesSchool(rec, school) {
  if (!school || school === "All") return true;
  const s = (rec.school || "").toLowerCase();
  if (school === "General") return !rec.school;
  return rec.school === school || s === "both";
}

const PRIORITY_LABELS = { high: "High priority", medium: "Medium priority", low: "Low priority" };

function GenerationHeader({ genStatus, generating, onGenerate }) {
  const lastDate = genStatus?.last_generated_at ? formatDate(genStatus.last_generated_at) : null;
  const nextDate = genStatus?.next_available_at ? formatDate(genStatus.next_available_at) : null;
  const canGenerate = genStatus?.can_generate ?? true;

  return (
    <div className="card rec-header">
      <div>
        <p className="panel-title">Recommendations</p>
        <p className="panel-subtitle">AI-visibility strategy generated from your tracked data</p>
        <p className="rec-header__meta">
          {lastDate ? `Last updated ${lastDate}` : "No recommendations generated yet"}
          {!canGenerate && nextDate && ` · next refresh available ${nextDate}`}
        </p>
      </div>
      <button
        className="btn btn--primary"
        onClick={onGenerate}
        disabled={generating || !canGenerate}
        title={!canGenerate ? `Available again ${nextDate}` : undefined}
      >
        {generating ? "Generating…" : canGenerate ? "↻ Generate new recommendations" : `Locked until ${nextDate}`}
      </button>
    </div>
  );
}

function HealthColumn({ variant, title, items }) {
  return (
    <div className={`card health-col--${variant}`}>
      <p className="panel-title">{title}</p>
      <ul className="health-list">
        {items.length === 0 && <li className="state-empty">Not enough data yet.</li>}
        {items.map((item, i) => (
          <li className="health-list__item" key={i}>
            <span className="health-list__bullet">{variant === "good" ? "●" : "▲"}</span>
            <span>{item.text}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

// Human-readable framing per triage reason (question-router plan §5.9).
const TRIAGE_REASONS = {
  fragmented_field: "No single source type wins this query",
  insufficient_voters: "Too few citations to call it",
  no_cited_winners: "QC loses but nothing external is cited",
  feasibility_unknown: "Winners can't be owned; no channel found",
  reputation_no_channel: "Reputation question with nothing to pitch",
};

// The losing questions the router could not auto-action - ranked by how much
// is at stake (rank_score = citation volume x how badly QC is losing), so the
// strongest own-the-field candidates surface first. Collapsed by default;
// lives OUTSIDE the three action tabs because these rows need a human
// decision, not a team's backlog.
function TriagePanel({ items }) {
  const [open, setOpen] = useState(false);
  if (!items.length) return null;
  return (
    <section className="triage-panel">
      <button className="triage-panel__toggle" onClick={() => setOpen(!open)}>
        <span>{open ? "▾" : "▸"} Needs triage — {items.length} losing question{items.length === 1 ? "" : "s"} the router couldn't auto-action</span>
      </button>
      {open && (
        <div className="triage-panel__list">
          {items.map((t, i) => (
            <div className="triage-row" key={t.question_id ?? i}>
              <span className="triage-row__rank">#{i + 1}</span>
              <div className="triage-row__body">
                <p className="triage-row__question">{t.question}</p>
                <p className="triage-row__meta">
                  {TRIAGE_REASONS[t.reason] ?? t.reason}
                  {t.topic ? ` · ${t.topic}` : ""}
                  {t.n_citations != null ? ` · ${t.n_citations} citations` : ""}
                  {t.qc_share != null ? ` · QC cited ${Math.round(t.qc_share * 100)}%` : ""}
                </p>
              </div>
              <div className="triage-row__chips">
                <span className="chip">{t.reason}</span>
                {t.build_candidate && (
                  <span className="chip chip--metric" title="Buildable topic — QC could plausibly own this query with one strong page. Needs a human green-light.">
                    build candidate
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

function Recommendations() {
  const navigate = useNavigate();
  const { days, school } = useFilter();
  const [recommendations, setRecommendations] = useState(null);
  const [genStatus, setGenStatus] = useState(null);
  const [health, setHealth] = useState(null);
  const [error, setError] = useState(null);
  const [generating, setGenerating] = useState(false);
  const [stream, setStream] = useState("strategic");
  const [popoverId, setPopoverId] = useState(null);
  const [triage, setTriage] = useState([]);

  const loading = recommendations === null && error === null;

  const openPrompt = (promptId) => navigate(`/prompts/${promptId}`);
  const openRecommendation = (recId) => navigate(`/recommendations/${recId}`);

  const loadRecommendations = () => {
    Promise.all([
      fetch(`${API_BASE_URL}/api/recommendations`).then((r) => r.json()),
      fetch(`${API_BASE_URL}/api/recommendations/generation-status`).then((r) => r.json()),
      fetch(`${API_BASE_URL}/api/recommendations/triage`).then((r) => r.json()),
    ])
      .then(([recs, gen, tri]) => {
        setRecommendations(recs);
        setGenStatus(gen);
        setTriage(Array.isArray(tri) ? tri : []);
      })
      .catch((err) => setError(err.message));
  };

  useEffect(() => {
    loadRecommendations();
  }, []);

  useEffect(() => {
    const params = new URLSearchParams();
    if (days) params.append("days", days);
    if (school && school !== "All") params.append("school", school);

    fetch(`${API_BASE_URL}/api/recommendations/health-summary?${params}`)
      .then((r) => r.json())
      .then(setHealth)
      .catch((err) => setError(err.message));
  }, [days, school]);

  const handleGenerate = () => {
    setGenerating(true);
    const params = new URLSearchParams();
    if (days) params.append("days", days);

    fetch(`${API_BASE_URL}/api/generate-recommendations?${params}`)
      .then((r) => {
        if (!r.ok) return r.json().then((body) => { throw new Error(body?.detail?.message || "Generation failed"); });
        return r.json();
      })
      .then(() => {
        loadRecommendations();
        setGenerating(false);
      })
      .catch((err) => {
        setError(err.message);
        setGenerating(false);
      });
  };

  const patchRecommendation = (id, body) => {
    setPopoverId(null);
    setRecommendations((prev) => prev.map((r) => (r.id === id ? { ...r, ...body } : r)));
    fetch(`${API_BASE_URL}/api/recommendations/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })
      .then(() => loadRecommendations())
      .catch((err) => console.error("Failed to update recommendation:", err));
  };

  const handleAccept = (id) => patchRecommendation(id, { status: "accepted" });
  const handleConfirmImplemented = (id, dateStr) =>
    patchRecommendation(id, { status: "implemented", implemented_at: dateStr });

  if (error) return <p className="state-msg state-msg--error">Error: {error}</p>;
  if (loading) return <p className="state-msg">Loading...</p>;

  const schoolFiltered = recommendations.filter((r) => matchesSchool(r, school));
  const streamCounts = Object.fromEntries(
    WORK_STREAMS.map((s) => [
      s.key,
      schoolFiltered.filter(
        (r) => streamOf(r) === s.key && (r.status === "proposed" || ACTIVE_STATUSES.includes(r.status))
      ).length,
    ])
  );
  const streamFiltered = schoolFiltered.filter((r) => streamOf(r) === stream);
  const activeRecs = streamFiltered.filter((r) => ACTIVE_STATUSES.includes(r.status));
  const proposedRecs = streamFiltered.filter((r) => r.status === "proposed");

  const byPriority = { high: [], medium: [], low: [] };
  proposedRecs.forEach((r) => (byPriority[r.priority] ?? byPriority.low).push(r));

  const cardProps = {
    onAccept: handleAccept,
    onOpenPopover: setPopoverId,
    onCancelPopover: () => setPopoverId(null),
    onConfirmImplemented: handleConfirmImplemented,
    onOpenPrompt: openPrompt,
    onOpenDetail: openRecommendation,
  };

  return (
    <div className="rec-page">
      <GenerationHeader genStatus={genStatus} generating={generating} onGenerate={handleGenerate} />

      <div className="health-grid">
        <HealthColumn variant="good" title="What's going well" items={health?.going_well ?? []} />
        <HealthColumn variant="warn" title="What needs work" items={health?.needs_work ?? []} />
      </div>

      <div className="rec-tabs" role="tablist" aria-label="Recommendation work-streams">
        {WORK_STREAMS.map((s) => (
          <button
            key={s.key}
            role="tab"
            aria-selected={stream === s.key}
            className={`rec-tab ${stream === s.key ? "rec-tab--active" : ""}`}
            onClick={() => setStream(s.key)}
          >
            {s.label}
            <span className="rec-tab__question">{s.question}</span>
            <span className="rec-tab__count">{streamCounts[s.key]}</span>
          </button>
        ))}
      </div>
      <p className="rec-stream-note">{WORK_STREAMS.find((s) => s.key === stream).note}</p>

      {activeRecs.length > 0 && (
        <section>
          <p className="section-header">Active · {activeRecs.length}</p>
          <div className="rec-list">
            {activeRecs.map((rec) => (
              <RecommendationCard
                key={rec.id}
                rec={rec}
                isPopoverOpen={popoverId === rec.id}
                {...cardProps}
              />
            ))}
          </div>
        </section>
      )}

      <div className="rec-filter-bar">
        <p className="panel-title">Prioritized recommendations</p>
      </div>

      {proposedRecs.length === 0 ? (
        <p className="state-empty">
          No open suggestions in this work-stream. {recommendations.length === 0 && 'Click "Generate new recommendations" to analyze the current data.'}
        </p>
      ) : (
        ["high", "medium", "low"].map(
          (priority) =>
            byPriority[priority].length > 0 && (
              <section key={priority}>
                <p className="section-header">{PRIORITY_LABELS[priority]} · {byPriority[priority].length}</p>
                <div className="rec-list">
                  {byPriority[priority].map((rec) => (
                    <RecommendationCard
                      key={rec.id}
                      rec={rec}
                      isPopoverOpen={popoverId === rec.id}
                      {...cardProps}
                    />
                  ))}
                </div>
              </section>
            )
        )
      )}

      <TriagePanel items={triage} />
    </div>
  );
}

export default Recommendations;
