import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { API_BASE_URL } from "../config";
import { useFilter } from "../context/useFilter";
import PromptMetricsPanel from "../components/PromptMetricsPanel";
import ResponseDrawer from "../components/ResponseDrawer";
import { recTriageMessage } from "../lib/recTriage";
import { formatLabel } from "../lib/recview";
import { FormatMeter } from "../components/ShareMeter";

function QuestionCitationsTable({ citations }) {
  return (
    <div className="card question-evidence">
      <p className="panel-title">Cited URLs</p>
      <p className="panel-subtitle">All cited URLs for this question, with cached page facts only.</p>
      <p className="question-evidence__legend">
        source_type is who owns the page (a rival, a neutral editorial page, a forum, a reference
        site) — it decides whether QC can compete for the slot. format is what kind of page it is
        (how-to guide, blog, listicle, landing page) — it decides what QC should build.
      </p>
      <FormatMeter pages={citations} />
      <div className="question-evidence__table-wrap">
        <table className="question-evidence__table">
          <thead>
            <tr>
              <th>URL</th>
              <th className="num">Count</th>
              <th>page_type</th>
              <th>source_type</th>
              <th>format</th>
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
                <td>{c.format ? formatLabel(c.format) : "—"}</td>
                <td>{c.fetch_status ?? "—"}</td>
              </tr>
            )) : (
              <tr>
                <td colSpan={6} className="state-empty">No cited URLs yet.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// Lets a person correct the sitemap matcher's pick directly on the question
// page (rather than only in a rec card, since the match also drives the
// "QC matched page" reading here) - the matcher is a text-similarity proxy
// for "does QC have the right page," and is wrong or silent often enough
// that a reviewer should be able to just say so. Saving re-generates the
// question's plan immediately (see PUT .../qc-url-override) instead of
// waiting for the normal 30-day cooldown.
function QcMatchedPageCard({ questionId, matched, onCorrected }) {
  const [editing, setEditing] = useState(false);
  const [url, setUrl] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const startEdit = () => {
    setUrl(matched?.url ?? "");
    setNote("");
    setError(null);
    setEditing(true);
  };

  const save = (method, body) => {
    setBusy(true);
    setError(null);
    fetch(`${API_BASE_URL}/api/questions/${questionId}/qc-url-override`, {
      method,
      headers: { "Content-Type": "application/json" },
      body: body ? JSON.stringify(body) : undefined,
    })
      .then((r) => { if (!r.ok) throw new Error(`Server error ${r.status}`); return r.json(); })
      .then((res) => {
        setBusy(false);
        setEditing(false);
        onCorrected(res);
      })
      .catch((err) => {
        setBusy(false);
        setError(`Couldn't save: ${err.message}`);
      });
  };

  return (
    <div className="card question-view__matched">
      <p className="panel-title">QC matched page</p>
      {matched?.url ? (
        <div className="question-view__matched-body">
          <a href={matched.url} target="_blank" rel="noreferrer" className="question-view__matched-url">
            {matched.url}
          </a>
          <p className="question-view__matched-meta">
            page_type: {matched.page_type ?? "—"} · fetch status: {matched.fetch_status ?? "—"}
            {matched.override ? " · manually corrected" : ""}
          </p>
        </div>
      ) : (
        <p className="state-empty">No QC page matched yet.</p>
      )}

      {!editing && (
        <div className="question-view__matched-actions">
          <button className="btn btn--ghost" onClick={startEdit} disabled={busy}>
            This isn&rsquo;t right
          </button>
          {matched?.override && (
            <button className="btn btn--ghost" onClick={() => save("DELETE")} disabled={busy}>
              Undo correction
            </button>
          )}
        </div>
      )}

      {editing && (
        <div className="question-view__matched-form">
          <input
            type="url"
            className="question-view__matched-input"
            placeholder="The actual QC page URL"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            autoFocus
          />
          <input
            type="text"
            className="question-view__matched-input"
            placeholder="Note (optional)"
            value={note}
            onChange={(e) => setNote(e.target.value)}
          />
          <div className="rc-track__actions">
            <button
              className="btn btn--primary"
              onClick={() => save("PUT", { qc_url: url.trim(), note: note.trim() || null })}
              disabled={busy || !url.trim()}
            >
              {busy ? "Saving…" : "Save correction"}
            </button>
            <button className="btn btn--ghost" onClick={() => setEditing(false)} disabled={busy}>
              Cancel
            </button>
          </div>
        </div>
      )}
      {error && <p className="question-view__rec-message question-view__rec-message--error">{error}</p>}
    </div>
  );
}

function QuestionRecButton({ questionId, onOpenPlan }) {
  const { days } = useFilter();
  const [status, setStatus] = useState(null);      // recommendation-status payload
  const [generating, setGenerating] = useState(false);
  const [message, setMessage] = useState(null);    // triage / error outcome
  const [messageIsInfo, setMessageIsInfo] = useState(false);

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
    setMessageIsInfo(false);
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
          // reach_out_auto_covered isn't a failure - the router routed this
          // question away from build/fix on purpose (see reach_out_sweep.py).
          setMessageIsInfo(res.triage?.reason === "reach_out_auto_covered");
          setMessage(recTriageMessage(res.triage));
        }
      })
      .catch(err => {
        setGenerating(false);
        setMessageIsInfo(false);
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
      {message && (
        <p className={`question-view__rec-message${messageIsInfo ? " question-view__rec-message--info" : ""}`}>
          {message}
        </p>
      )}
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
  // Bumped after a QC-page correction so QuestionRecButton (keyed on it below)
  // remounts and re-fetches recommendation-status instead of showing the
  // stale pre-correction gate.
  const [recNonce, setRecNonce] = useState(0);

  // cancelled=true is checked by the mount/param-change effect only - a
  // manual reload() (post-correction) always wants to land, even mid-unmount.
  const loadDetail = (cancelledRef) => {
    const params = new URLSearchParams();
    if (days) params.append("days", days);
    return fetch(`${API_BASE_URL}/api/topic-prompt/${promptId}?${params}`)
      .then((r) => {
        if (!r.ok) throw new Error(`Server error ${r.status}`);
        return r.json();
      })
      .then((data) => { if (!cancelledRef?.current) setResult({ key: fetchKey, detail: data }); })
      .catch((err) => { if (!cancelledRef?.current) setResult({ key: fetchKey, error: err.message }); });
  };

  useEffect(() => {
    const cancelledRef = { current: false };
    loadDetail(cancelledRef);
    return () => { cancelledRef.current = true; };
  }, [promptId, days, fetchKey]);

  const detail = result?.key === fetchKey ? result.detail : null;
  const error = result?.key === fetchKey ? result.error : null;

  // qc-url-override save/clear regenerates the question's plan server-side
  // (see PUT/DELETE .../qc-url-override) - re-read the matched page and force
  // the rec-status button to re-check, then jump straight to the plan when a
  // new one actually came out of it (mirrors QuestionRecButton's own
  // generate -> onOpenPlan flow).
  const handleCorrected = (res) => {
    loadDetail();
    setRecNonce((n) => n + 1);
    const recs = res?.recommendations ?? (res?.recommendation ? [res.recommendation] : []);
    if (recs.length > 0) {
      navigate(`/prompts/${promptId}/plan`);
    }
  };

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
          key={`${detail.question_id}-${recNonce}`}
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

        <QcMatchedPageCard
          key={detail.question_id}
          questionId={detail.question_id}
          matched={matched}
          onCorrected={handleCorrected}
        />

        <QuestionCitationsTable citations={evidence.citations || []} />
      </div>

      <ResponseDrawer drawer={drawer} onClose={() => setDrawer((d) => ({ ...d, open: false }))} />
    </div>
  );
}
