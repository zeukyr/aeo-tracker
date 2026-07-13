import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { API_BASE_URL } from "../config";
import RecommendationCard from "../components/RecommendationCard";
import { formatDate } from "../lib/format";
import { pctLabel } from "../lib/recview";

// The three work-streams, for the header's "teams involved" summary.
const STREAM_LABELS = {
  strategic: "Strategic Growth",
  on_page: "Improve Existing Pages",
  outreach: "Outreach & Earn",
};

// One question's full action plan (/prompts/:promptId/plan): every live rec
// covering the question, the plan's primary first, companions after. This is
// where "Generate recommendations" on the question page lands.
export default function QuestionPlan() {
  const { promptId } = useParams();
  const navigate = useNavigate();
  // Keyed by promptId so navigating between plans shows Loading instead of
  // the previous plan's data.
  const [result, setResult] = useState(null);
  const [popoverId, setPopoverId] = useState(null);

  const load = () => {
    fetch(`${API_BASE_URL}/api/questions/${promptId}/recommendations`)
      .then((r) => {
        if (!r.ok) throw new Error(`Server error ${r.status}`);
        return r.json();
      })
      .then((recs) => setResult({ promptId, recs }))
      .catch((err) => setResult({ promptId, error: err.message }));
  };

  // Stale responses are harmless: recs/error only read when result.promptId
  // matches the current route param.
  useEffect(load, [promptId]);

  const recs = result?.promptId === promptId ? result.recs : null;
  const error = result?.promptId === promptId ? result.error : null;

  const patchRecommendation = (id, body) => {
    setPopoverId(null);
    setResult((prev) =>
      prev?.recs
        ? { ...prev, recs: prev.recs.map((r) => (r.id === id ? { ...r, ...body } : r)) }
        : prev
    );
    fetch(`${API_BASE_URL}/api/recommendations/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })
      .then(() => load())
      .catch((err) => console.error("Failed to update recommendation:", err));
  };

  const cardProps = {
    onAccept: (id) => patchRecommendation(id, { status: "accepted" }),
    onOpenPopover: setPopoverId,
    onCancelPopover: () => setPopoverId(null),
    onConfirmImplemented: (id, dateStr) =>
      patchRecommendation(id, { status: "implemented", implemented_at: dateStr }),
    onOpenPrompt: (qid) => navigate(`/prompts/${qid}`),
    onOpenDetail: (recId) => navigate(`/recommendations/${recId}`),
  };

  // The router detail on any rec carries the question's text and share.
  const router = recs?.find((r) => r.detail?.router)?.detail?.router;
  const primary = recs?.filter((r) => r.detail?.question_plan?.role !== "companion") ?? [];
  const companions = recs?.filter((r) => r.detail?.question_plan?.role === "companion") ?? [];
  const streams = [...new Set((recs ?? []).map((r) => STREAM_LABELS[r.work_stream]).filter(Boolean))];
  const newest = recs?.length
    ? recs.reduce((a, r) => (r.generated_at > a ? r.generated_at : a), recs[0].generated_at)
    : null;

  return (
    <div className="rec-page">
      <div className="card rc-plan__head">
        <div>
          <button className="btn btn--ghost" onClick={() => navigate(`/prompts/${promptId}`)}>
            ← Back to question
          </button>
          <p className="rc-plan__eyebrow">Action plan</p>
          <p className="rc-plan__question">{router?.question ?? "This question"}</p>
          <p className="rc-plan__meta">
            {router?.qc_share != null && `QC cited in ${pctLabel(router.qc_share)} of responses`}
            {router?.n_citations != null && ` · ${router.n_citations} citations analyzed`}
            {recs?.length ? ` · ${recs.length} action${recs.length === 1 ? "" : "s"}` : ""}
            {streams.length > 0 && ` · ${streams.join(", ")}`}
            {newest && ` · generated ${formatDate(newest)}`}
          </p>
        </div>
      </div>

      {error ? (
        <p className="state-msg state-msg--error">Error: {error}</p>
      ) : recs === null ? (
        <p className="state-msg">Loading…</p>
      ) : recs.length === 0 ? (
        <p className="state-empty">
          No live recommendations for this question yet. Generate them from the question page.
        </p>
      ) : (
        <>
          {primary.length > 0 && (
            <section>
              <p className="section-header">Recommended action</p>
              <div className="rec-list">
                {primary.map((rec) => (
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
          {companions.length > 0 && (
            <section>
              <p className="section-header">Also worth doing · {companions.length}</p>
              <div className="rec-list">
                {companions.map((rec) => (
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
        </>
      )}
    </div>
  );
}
