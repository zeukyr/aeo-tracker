import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { API_BASE_URL } from "../config";
import RecommendationCard from "../components/RecommendationCard";
import { formatDate } from "../lib/format";

// Standalone recommendation page — each rec has its own URL
// (/recommendations/:recId), so cards can be shared, bookmarked, and opened
// from a question's "View recommendation" button.
export default function RecommendationDetail() {
  const { recId } = useParams();
  const navigate = useNavigate();
  // Keyed by recId so navigating to another rec shows Loading instead of the
  // previous rec's data (and no sync setState is needed in the effect).
  const [result, setResult] = useState(null);
  const [popoverOpen, setPopoverOpen] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetch(`${API_BASE_URL}/api/recommendations/${recId}`)
      .then((r) => {
        if (!r.ok) throw new Error(r.status === 404 ? "Recommendation not found" : `Server error ${r.status}`);
        return r.json();
      })
      .then((data) => { if (!cancelled) setResult({ recId, rec: data }); })
      .catch((err) => { if (!cancelled) setResult({ recId, error: err.message }); });
    return () => { cancelled = true; };
  }, [recId]);

  const rec = result?.recId === recId ? result.rec : null;
  const error = result?.recId === recId ? result.error : null;

  const patchRecommendation = (id, body) => {
    setPopoverOpen(false);
    setResult((prev) => (prev?.rec ? { ...prev, rec: { ...prev.rec, ...body } } : prev));
    fetch(`${API_BASE_URL}/api/recommendations/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).catch((err) => console.error("Failed to update recommendation:", err));
  };

  const handleAccept = (id) => patchRecommendation(id, { status: "accepted" });
  const handleConfirmImplemented = (id, dateStr) =>
    patchRecommendation(id, { status: "implemented", implemented_at: dateStr });

  return (
    <div className="rec-page">
      <div className="card rec-header">
        <div>
          <button className="btn btn--ghost" onClick={() => navigate("/recommendations")}>
            ← Back to all recommendations
          </button>
          <p className="panel-title">Recommendation</p>
          {rec?.generated_at && (
            <p className="rec-header__meta">Generated {formatDate(rec.generated_at)}</p>
          )}
        </div>
      </div>
      {error ? (
        <p className="state-msg state-msg--error">Error: {error}</p>
      ) : rec ? (
        <div className="rec-list">
          {(rec.detail?.question_plan?.question_id ?? rec.segment?.question_id) && (
            <div className="rc-plan__banner">
              <span>This is one action in this question's plan.</span>
              <button
                type="button"
                onClick={() => navigate(`/prompts/${rec.detail?.question_plan?.question_id ?? rec.segment.question_id}/plan`)}
              >
                View all actions →
              </button>
            </div>
          )}
          <RecommendationCard
            rec={rec}
            isPopoverOpen={popoverOpen}
            onAccept={handleAccept}
            onOpenPopover={() => setPopoverOpen(true)}
            onCancelPopover={() => setPopoverOpen(false)}
            onConfirmImplemented={handleConfirmImplemented}
            onOpenPrompt={(promptId) => navigate(`/prompts/${promptId}`)}
          />
        </div>
      ) : (
        <p className="state-msg">Loading…</p>
      )}
    </div>
  );
}
