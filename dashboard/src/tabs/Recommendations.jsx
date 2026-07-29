import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { API_BASE_URL } from "../config";
import { useFilter } from "../context/useFilter";
import RecommendationCard from "../components/RecommendationCard";
import QuestionGroup from "../components/rec/QuestionGroup";
import InfoTip from "../components/InfoTip";
import { formatDate } from "../lib/format";
import { recTriageMessage } from "../lib/recTriage";

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

function GenerationHeader({ genStatus, refreshing, onRefreshSignals }) {
  const lastDate = genStatus?.last_generated_at ? formatDate(genStatus.last_generated_at) : null;
  const nextDate = genStatus?.next_available_at ? formatDate(genStatus.next_available_at) : null;
  const canGenerate = genStatus?.can_generate ?? true;

  return (
    <div className="card rec-header">
      <div>
        <p className="panel-title">Recommendations</p>
        <p className="panel-subtitle">AI-visibility strategy generated from your tracked data</p>
        <p className="rec-header__meta">
          Pick questions in the panel below to generate recommendations for them.
          {lastDate && ` · signals last refreshed ${lastDate}`}
        </p>
      </div>
      <button
        className="btn btn--ghost"
        onClick={onRefreshSignals}
        disabled={refreshing || !canGenerate}
        title={
          !canGenerate
            ? `Available again ${nextDate}`
            : "Refreshes brand concern and credibility recommendations — not tied to a specific question"
        }
      >
        {refreshing ? "Refreshing…" : canGenerate ? "↻ Refresh signal recommendations" : `Locked until ${nextDate}`}
      </button>
    </div>
  );
}

function HealthColumn({ variant, title, items }) {
  return (
    <div className={`card health-col--${variant}`}>
      <p className="panel-title">
        {title}
        <InfoTip id="health_summary" />
      </p>
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

// The live, weakest-first list of losing questions (question-router plan
// §9.1: qc_share <= 15%). A human checks the ones worth generating a
// recommendation for and fires them one at a time against the same on-demand
// endpoint QuestionDetail.jsx uses - no auto-pick-the-weakest-question step.
function CandidateQuestionPicker({ candidates, selected, onToggle, onGenerate, generating, rowResults }) {
  const [open, setOpen] = useState(true);
  if (!candidates.length) return null;
  const selectedCount = selected.size;

  return (
    <section className="candidate-panel">
      <div className="candidate-panel__head">
        <button className="candidate-panel__toggle" onClick={() => setOpen(!open)}>
          <span>{open ? "▾" : "▸"} Select questions to generate recommendations for — {candidates.length} losing question{candidates.length === 1 ? "" : "s"}</span>
        </button>
        <InfoTip id="losing_question" dir="up" align="right" />
      </div>
      {open && (
        <>
          <div className="candidate-panel__list">
            {candidates.map((c, i) => {
              const result = rowResults[c.question_id];
              const busy = generating && result?.status === "generating";
              return (
                <label className="candidate-row" key={c.question_id ?? i}>
                  <input
                    type="checkbox"
                    checked={selected.has(c.question_id)}
                    disabled={generating}
                    onChange={() => onToggle(c.question_id)}
                  />
                  <span className="candidate-row__rank">#{i + 1}</span>
                  <div className="candidate-row__body">
                    <p className="candidate-row__question">{c.question}</p>
                    <p className="candidate-row__meta">
                      {c.topic ? `${c.topic} · ` : ""}
                      QC cited {Math.round(c.qc_share * 100)}% · {c.n_citations} citations
                    </p>
                    {result && (
                      <p className={`candidate-row__result candidate-row__result--${result.status}`}>
                        {busy ? "Generating…" : result.message}
                      </p>
                    )}
                  </div>
                </label>
              );
            })}
          </div>
          <div className="candidate-panel__actions">
            <span className="candidate-panel__count">{selectedCount} selected</span>
            <button
              className="btn btn--primary"
              onClick={onGenerate}
              disabled={selectedCount === 0 || generating}
            >
              {generating
                ? "Generating…"
                : selectedCount > 0
                  ? `Generate recommendations for ${selectedCount} selected`
                  : "Select questions to generate"}
            </button>
          </div>
        </>
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
  const [refreshing, setRefreshing] = useState(false);
  const [stream, setStream] = useState("strategic");
  const [popoverId, setPopoverId] = useState(null);
  const [expandedRows, setExpandedRows] = useState(() => new Set());
  const [candidates, setCandidates] = useState([]);
  const [selected, setSelected] = useState(() => new Set());
  const [generatingSelected, setGeneratingSelected] = useState(false);
  const [rowResults, setRowResults] = useState({});

  const loading = recommendations === null && error === null;

  const openPrompt = (promptId) => navigate(`/prompts/${promptId}`);
  const openRecommendation = (recId) => navigate(`/recommendations/${recId}`);

  const loadRecommendations = () => {
    Promise.all([
      fetch(`${API_BASE_URL}/api/recommendations`).then((r) => r.json()),
      fetch(`${API_BASE_URL}/api/recommendations/generation-status`).then((r) => r.json()),
    ])
      .then(([recs, gen]) => {
        setRecommendations(recs);
        setGenStatus(gen);
      })
      .catch((err) => setError(err.message));
  };

  const loadCandidates = () => {
    const params = new URLSearchParams();
    if (days) params.append("days", days);

    fetch(`${API_BASE_URL}/api/recommendations/candidates?${params}`)
      .then((r) => r.json())
      .then((data) => setCandidates(Array.isArray(data) ? data : []))
      .catch((err) => setError(err.message));
  };

  useEffect(() => {
    loadRecommendations();
  }, []);

  useEffect(() => {
    loadCandidates();
  }, [days]);

  useEffect(() => {
    const params = new URLSearchParams();
    if (days) params.append("days", days);
    if (school && school !== "All") params.append("school", school);

    fetch(`${API_BASE_URL}/api/recommendations/health-summary?${params}`)
      .then((r) => r.json())
      .then(setHealth)
      .catch((err) => setError(err.message));
  }, [days, school]);

  const handleRefreshSignals = () => {
    setRefreshing(true);
    const params = new URLSearchParams();
    if (days) params.append("days", days);

    fetch(`${API_BASE_URL}/api/recommendations/refresh-signals?${params}`)
      .then((r) => {
        if (!r.ok) return r.json().then((body) => { throw new Error(body?.detail?.message || "Refresh failed"); });
        return r.json();
      })
      .then(() => {
        loadRecommendations();
        setRefreshing(false);
      })
      .catch((err) => {
        setError(err.message);
        setRefreshing(false);
      });
  };

  const toggleSelected = (questionId) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(questionId)) next.delete(questionId);
      else next.add(questionId);
      return next;
    });
  };

  const handleGenerateSelected = () => {
    const ids = Array.from(selected);
    if (!ids.length) return;
    setGeneratingSelected(true);
    setRowResults((prev) => {
      const next = { ...prev };
      ids.forEach((id) => { next[id] = { status: "generating" }; });
      return next;
    });

    const params = new URLSearchParams();
    if (days) params.append("days", days);

    Promise.allSettled(
      ids.map((id) =>
        fetch(`${API_BASE_URL}/api/questions/${id}/recommendation?${params}`, { method: "POST" })
          .then((r) => { if (!r.ok) throw new Error(`Server error ${r.status}`); return r.json(); })
      )
    ).then((settled) => {
      setRowResults((prev) => {
        const next = { ...prev };
        settled.forEach((outcome, i) => {
          const id = ids[i];
          if (outcome.status === "rejected") {
            next[id] = { status: "error", message: outcome.reason?.message || "Generation failed" };
            return;
          }
          const res = outcome.value;
          const recs = res.recommendations ?? (res.recommendation ? [res.recommendation] : []);
          if (res.generated) {
            next[id] = { status: "success", message: `Generated ${recs.length} recommendation${recs.length === 1 ? "" : "s"}` };
          } else if (recs.length > 0) {
            next[id] = {
              status: "blocked",
              message: res.blocked_by === "cooldown"
                ? `Already has a plan — next refresh available ${formatDate(res.next_available_at)}`
                : "Already has an active recommendation in progress",
            };
          } else {
            next[id] = { status: "triage", message: recTriageMessage(res.triage) };
          }
        });
        return next;
      });
      setGeneratingSelected(false);
      setSelected(new Set());
      loadRecommendations();
      loadCandidates();
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

  const toggleExpandRow = (id) => {
    setExpandedRows((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

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

  // Outreach & Earn only: one question can have several pitchable channels
  // (a subreddit, a certifying body, a directory) - grouping by question_id
  // makes that shape visible instead of scattering them across priority
  // tiers. Active + proposed merge into the same groups; priority becomes a
  // sort input (best label in the group, then citation volume), not a
  // section boundary. Questions with only one channel render exactly as
  // before - a flat full card, no group header.
  const PRIORITY_ORDER = { high: 0, medium: 1, low: 2 };
  let outreachGroups = [];
  if (stream === "outreach") {
    const byQuestion = new Map();
    streamFiltered.forEach((rec) => {
      const qid = rec.detail?.router?.question_id ?? `_solo_${rec.id}`;
      if (!byQuestion.has(qid)) byQuestion.set(qid, []);
      byQuestion.get(qid).push(rec);
    });
    outreachGroups = [...byQuestion.values()].sort((a, b) => {
      const aPri = Math.min(...a.map((r) => PRIORITY_ORDER[r.priority] ?? 3));
      const bPri = Math.min(...b.map((r) => PRIORITY_ORDER[r.priority] ?? 3));
      if (aPri !== bPri) return aPri - bPri;
      return (b[0].detail?.router?.n_citations ?? 0) - (a[0].detail?.router?.n_citations ?? 0);
    });
  }

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
      <GenerationHeader genStatus={genStatus} refreshing={refreshing} onRefreshSignals={handleRefreshSignals} />

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

      {stream === "outreach" ? (
        <>
          <div className="rec-filter-bar">
            <p className="panel-title">Prioritized recommendations</p>
          </div>
          {streamFiltered.length === 0 ? (
            <p className="state-empty">
              No open suggestions in this work-stream. {recommendations.length === 0 && "Select a question below to generate a recommendation for it."}
            </p>
          ) : (
            <div className="rec-list">
              {outreachGroups.map((group) =>
                group.length > 1 ? (
                  <QuestionGroup
                    key={group[0].detail?.router?.question_id ?? group[0].id}
                    group={group}
                    expandedIds={expandedRows}
                    onToggleExpand={toggleExpandRow}
                    popoverId={popoverId}
                    cardProps={cardProps}
                  />
                ) : (
                  <RecommendationCard
                    key={group[0].id}
                    rec={group[0]}
                    isPopoverOpen={popoverId === group[0].id}
                    {...cardProps}
                  />
                )
              )}
            </div>
          )}
        </>
      ) : (
        <>
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
              No open suggestions in this work-stream. {recommendations.length === 0 && "Select a question below to generate a recommendation for it."}
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
        </>
      )}

      <CandidateQuestionPicker
        candidates={candidates}
        selected={selected}
        onToggle={toggleSelected}
        onGenerate={handleGenerateSelected}
        generating={generatingSelected}
        rowResults={rowResults}
      />
    </div>
  );
}

export default Recommendations;
