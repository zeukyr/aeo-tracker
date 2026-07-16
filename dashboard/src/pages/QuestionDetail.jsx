import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { API_BASE_URL } from "../config";
import { useFilter } from "../context/useFilter";
import PromptMetricsPanel from "../components/PromptMetricsPanel";
import ResponseDrawer from "../components/ResponseDrawer";
import { recTriageMessage } from "../lib/recTriage";

function QuestionCitationsTable({ citations }) {
  return (
    <div className="card question-evidence">
      <p className="panel-title">Cited URLs</p>
      <p className="panel-subtitle">All cited URLs for this question, with cached page facts only.</p>
      <div className="question-evidence__table-wrap">
        <table className="question-evidence__table">
          <thead>
            <tr>
              <th>URL</th>
              <th className="num">Count</th>
              <th>page_type</th>
              <th>source_type</th>
              <th>fetch status</th>
            </tr>
          </thead>
          <tbody>
            {citations?.length ? citations.map((c) => (
              <tr key={c.url}>
                <td>
                  <a href={c.url} target="_blank" rel="noreferrer" className="question-evidence__url">
                    {c.url}
                  </a>
                </td>
                <td className="num">{c.citation_count}</td>
                <td>{c.page_type ?? "—"}</td>
                <td>{c.source_type ?? "—"}</td>
                <td>{c.fetch_status ?? "—"}</td>
              </tr>
            )) : (
              <tr>
                <td colSpan={5} className="state-empty">No cited URLs yet.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function QuestionRecButton({ questionId, onOpenPlan }) {
  const { days } = useFilter();
  const [status, setStatus] = useState(null);      // recommendation-status payload
  const [generating, setGenerating] = useState(false);
  const [message, setMessage] = useState(null);    // triage / error outcome

  // State resets between questions by remount - the parent keys this
  // component on questionId - so the effect only fetches.
  useEffect(() => {
    if (!questionId) return undefined;
    let cancelled = false;
    fetch(`${API_BASE_URL}/api/questions/${questionId}/recommendation-status`)
      .then(r => { if (!r.ok) throw new Error(`Server error ${r.status}`); return r.json(); })
      .then(s => { if (!cancelled) setStatus(s); })
      .catch(() => { if (!cancelled) setStatus({ recommendations: [], can_generate: false }); });
    return () => { cancelled = true; };
  }, [questionId]);

  // Older payloads carry only the singular field.
  const existingCount = status?.recommendations?.length ?? (status?.recommendation ? 1 : 0);

  const handleClick = () => {
    if (existingCount > 0) {
      onOpenPlan?.();
      return;
    }
    setGenerating(true);
    setMessage(null);
    const params = new URLSearchParams();
    if (days) params.append("days", days);
    fetch(`${API_BASE_URL}/api/questions/${questionId}/recommendation?${params}`, { method: "POST" })
      .then(r => { if (!r.ok) throw new Error(`Server error ${r.status}`); return r.json(); })
      .then(res => {
        setGenerating(false);
        const recs = res.recommendations ?? (res.recommendation ? [res.recommendation] : []);
        if (recs.length > 0) {
          setStatus({ recommendations: recs, can_generate: false });
          onOpenPlan?.();
        } else {
          setMessage(recTriageMessage(res.triage));
        }
      })
      .catch(err => {
        setGenerating(false);
        setMessage(`Generation failed: ${err.message}`);
      });
  };

  return (
    <div className="question-view__rec-action">
      <button
        className="btn btn--primary"
        onClick={handleClick}
        disabled={!status || generating}
        title={existingCount > 0 && status?.blocked_by === "cooldown"
          ? `Regeneration available ${new Date(status.next_available_at).toLocaleDateString()}`
          : undefined}
      >
        {!status ? "…"
          : generating ? "Generating…"
          : existingCount > 1 ? `View ${existingCount} recommendations`
          : existingCount === 1 ? "View recommendation"
          : "Generate recommendations"}
      </button>
      {message && <p className="question-view__rec-message">{message}</p>}
    </div>
  );
}

// Standalone question page — each prompt/topic question has its own URL
// (/prompts/:promptId). This replaced the Prompts tab's inline expanded card:
// metrics, matched page, cited URLs, and the per-engine response drawer all
// live here now.
export default function QuestionDetail() {
  const { promptId } = useParams();
  const navigate = useNavigate();
  const { days } = useFilter();
  // Keyed by prompt + period so switching either shows Loading instead of the
  // previous question's data (and no sync setState is needed in the effect).
  const fetchKey = `${promptId}|${days ?? ""}`;
  const [result, setResult] = useState(null);
  const [drawer, setDrawer] = useState({ open: false, engine: null, promptText: null, promptId: null });

  useEffect(() => {
    let cancelled = false;
    const params = new URLSearchParams();
    if (days) params.append("days", days);

    fetch(`${API_BASE_URL}/api/topic-prompt/${promptId}?${params}`)
      .then((r) => {
        if (!r.ok) throw new Error(`Server error ${r.status}`);
        return r.json();
      })
      .then((data) => { if (!cancelled) setResult({ key: fetchKey, detail: data }); })
      .catch((err) => { if (!cancelled) setResult({ key: fetchKey, error: err.message }); });
    return () => { cancelled = true; };
  }, [promptId, days, fetchKey]);

  const detail = result?.key === fetchKey ? result.detail : null;
  const error = result?.key === fetchKey ? result.error : null;

  if (error) {
    return <div className="card question-view"><p className="state-msg state-msg--error">Error: {error}</p></div>;
  }
  if (!detail) {
    return <div className="card question-view"><p className="state-msg">Loading…</p></div>;
  }

  const prompt = { id: detail.question_id, text: detail.question };
  const evidence = detail.evidence || {};
  const matched = evidence.matched_page;

  return (
    <div className="question-view">
      <div className="card question-view__header">
        <div className="question-view__header-copy">
          <button className="btn btn--ghost question-view__back" onClick={() => navigate("/prompts")}>
            ← Back to prompt explorer
          </button>
          <p className="panel-title">Question detail</p>
          <p className="panel-subtitle">{detail.topic ?? "Uncategorized"}{detail.school ? ` · ${detail.school}` : ""}{detail.question_type ? ` · ${detail.question_type}` : ""}</p>
        </div>
        <QuestionRecButton
          key={detail.question_id}
          questionId={detail.question_id}
          onOpenPlan={() => navigate(`/prompts/${detail.question_id}/plan`)}
        />
      </div>

      <div className="question-view__stack">
        <div className="card question-view__metrics">
          <PromptMetricsPanel
            prompt={prompt}
            detail={detail}
            onOpenDrawer={(engine, promptText, id) => setDrawer({ open: true, engine, promptText, promptId: id })}
            showDrawerButtons
          />
        </div>

        <div className="card question-view__matched">
          <p className="panel-title">QC matched page</p>
          {matched?.url ? (
            <div className="question-view__matched-body">
              <a href={matched.url} target="_blank" rel="noreferrer" className="question-view__matched-url">{matched.url}</a>
              <p className="question-view__matched-meta">page_type: {matched.page_type ?? "—"} · fetch status: {matched.fetch_status ?? "—"}</p>
            </div>
          ) : (
            <p className="state-empty">No QC page matched yet.</p>
          )}
        </div>

        <QuestionCitationsTable citations={evidence.citations || []} />
      </div>

      <ResponseDrawer drawer={drawer} onClose={() => setDrawer((d) => ({ ...d, open: false }))} />
    </div>
  );
}
