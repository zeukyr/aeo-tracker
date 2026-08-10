import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { API_BASE_URL } from "../config";
import { formatDate } from "../lib/format";
import { ANGLE_LABELS, schoolLabel } from "../lib/blogIdeas";

// Slug for the downloaded filename - lowercase, non-alphanumeric runs
// collapsed to a single hyphen, trimmed, capped so it never turns into an
// unusably long filename for a long editorial title.
function slugify(title) {
  return (title || "blog-post")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 80) || "blog-post";
}

// One cluster idea's own page - the outline (planned brief) and the full
// post draft (generate/regenerate/copy/download/view) both need more room
// than the list's nested accordion gave them. Same
// standalone-page-with-its-own-URL pattern as RecommendationDetail.jsx
// (/recommendations/:recId).
function FullPostDraft({ body, title, generating, error, onGenerate }) {
  const [copied, setCopied] = useState(false);
  const handleCopy = () => {
    navigator.clipboard.writeText(body).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  };

  // Both actions build the file from the same in-memory draft text - no
  // extra API round-trip needed, the page already has it.
  const handleDownload = () => {
    const blob = new Blob([body], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${slugify(title)}.md`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const handleView = () => {
    const blob = new Blob([body], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    window.open(url, "_blank");
    // Revoke after giving the new tab time to load it, not immediately.
    setTimeout(() => URL.revokeObjectURL(url), 10000);
  };

  return (
    <div className="rc-brief__section">
      <span className="rc-brief__eyebrow">Full post draft</span>
      {body ? (
        <>
          <div className="draft-body">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{body}</ReactMarkdown>
          </div>
          <div className="draft-actions">
            <button className="btn btn--ghost" onClick={handleCopy}>{copied ? "Copied" : "Copy"}</button>
            <button className="btn btn--ghost" onClick={handleView}>View as file</button>
            <button className="btn btn--ghost" onClick={handleDownload}>⬇ Download .md</button>
            <button className="btn btn--ghost" onClick={onGenerate} disabled={generating}>
              {generating ? "Regenerating…" : "Regenerate"}
            </button>
          </div>
        </>
      ) : (
        <>
          <p className="rc-brief__empty">
            No full draft yet — this idea only has the planned outline below.
          </p>
          <div className="draft-actions">
            <button className="btn btn--primary" onClick={onGenerate} disabled={generating}>
              {generating ? "Generating…" : "✎ Generate full post"}
            </button>
          </div>
        </>
      )}
      {error && <p className="candidate-row__result candidate-row__result--error">{error}</p>}
    </div>
  );
}

function IdeaOutline({ outline }) {
  if (!outline) return null;
  const { heading, extractable_block: block, body_points: points, comparison, targets } = outline;
  const wordCount = block ? block.trim().split(/\s+/).length : 0;

  return (
    <>
      {heading && (
        <div className="rc-brief__section">
          <span className="rc-brief__eyebrow">Suggested H2</span>
          <div className="rc-brief__heading">
            <span className="rc-brief__heading-tag">H2</span>
            <span className="rc-brief__heading-text">"{heading}"</span>
          </div>
        </div>
      )}
      {block && (
        <div className="rc-brief__section">
          <span className="rc-brief__eyebrow">Extractable answer block (40–60 words)</span>
          <p className="extract-block">{block}</p>
          <p className="word-count">{wordCount} words</p>
        </div>
      )}
      {points?.length > 0 && (
        <div className="rc-brief__section">
          <span className="rc-brief__eyebrow">Full paragraph — key points (150–300 words)</span>
          <ul className="body-points">
            {points.map((p, i) => <li key={i}>{p}</li>)}
          </ul>
        </div>
      )}
      {comparison?.enabled && (
        <div className="rc-brief__section">
          <span className="rc-brief__eyebrow">Comparison structure</span>
          <div className="comparison-box"><span className="vs">VS</span> {comparison.vs}</div>
        </div>
      )}
      {targets?.length > 0 && (
        <div className="rc-brief__section">
          <span className="rc-brief__eyebrow">Targets (from the tracked-query bank)</span>
          <div className="target-list">
            {targets.map((t) => (
              <div className="target-row" key={t.question_id}>
                <span className="qshare">{Math.round(t.qc_share * 100)}% QC</span>
                <span className="qtext">"{t.text}"</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </>
  );
}

export default function BlogIdeaDetail() {
  const { ideaId } = useParams();
  const navigate = useNavigate();
  // Keyed by ideaId so navigating to another idea shows Loading instead of
  // the previous idea's data.
  const [result, setResult] = useState(null);
  const [generating, setGenerating] = useState(false);
  const [draftError, setDraftError] = useState(null);

  const load = () => {
    fetch(`${API_BASE_URL}/api/blog-ideas/${ideaId}`)
      .then((r) => {
        if (!r.ok) throw new Error(r.status === 404 ? "Blog idea not found" : `Server error ${r.status}`);
        return r.json();
      })
      .then((data) => setResult({ ideaId, idea: data }))
      .catch((err) => setResult({ ideaId, error: err.message }));
  };

  useEffect(load, [ideaId]);

  const idea = result?.ideaId === ideaId ? result.idea : null;
  const error = result?.ideaId === ideaId ? result.error : null;

  const handleStatusChange = (status) => {
    setResult((prev) => (prev?.idea ? { ...prev, idea: { ...prev.idea, status } } : prev));
    fetch(`${API_BASE_URL}/api/blog-ideas/${ideaId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status }),
    }).catch((err) => console.error("Failed to update blog idea status:", err));
  };

  const handleGenerateFullPost = () => {
    setGenerating(true);
    setDraftError(null);
    fetch(`${API_BASE_URL}/api/blog-ideas/${ideaId}/draft`, { method: "POST" })
      .then((r) => {
        if (!r.ok) return r.json().then((body) => { throw new Error(body?.detail?.message || "Generation failed"); });
        return r.json();
      })
      .then((res) => {
        setResult({ ideaId, idea: res.idea });
        setGenerating(false);
      })
      .catch((err) => {
        setDraftError(err.message);
        setGenerating(false);
      });
  };

  return (
    <div className="rec-page">
      <div className="card rec-header">
        <div>
          <button className="btn btn--ghost" onClick={() => navigate("/blog-ideas")}>
            ← Back to Blog Ideas
          </button>
          <p className="panel-title">Blog Idea</p>
          {idea && (
            <p className="rec-header__meta">
              {idea.topic} — {schoolLabel(idea.school)}
              {idea.generated_at && ` · generated ${formatDate(idea.generated_at)}`}
            </p>
          )}
        </div>
      </div>

      {error ? (
        <p className="state-msg state-msg--error">Error: {error}</p>
      ) : idea ? (
        idea.cluster_role !== "cluster" ? (
          <p className="state-empty">
            This is a pillar page, not a cluster post - pillar pages don't have a full-post draft. Open one of its cluster ideas from the Blog Ideas list instead.
          </p>
        ) : (
          <div className="card">
            <div className="rc-brief__section" style={{ marginBottom: 4 }}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
                <p className="panel-title" style={{ marginBottom: 0 }}>{idea.title}</p>
                <span className="cluster-chips">
                  <span className="angle-tag">{ANGLE_LABELS[idea.angle] ?? idea.angle}</span>
                  <select
                    className={`priority-pill priority-pill--${idea.status}`}
                    style={{ border: "none", fontFamily: "inherit", cursor: "pointer" }}
                    value={idea.status}
                    onChange={(e) => handleStatusChange(e.target.value)}
                  >
                    <option value="idea">Idea</option>
                    <option value="drafted">Drafted</option>
                    <option value="published">Published</option>
                  </select>
                </span>
              </div>
            </div>

            <div className="rc-brief">
              <FullPostDraft
                body={idea.body}
                title={idea.title}
                generating={generating}
                error={draftError}
                onGenerate={handleGenerateFullPost}
              />
              <IdeaOutline outline={idea.outline} />
            </div>
          </div>
        )
      ) : (
        <p className="state-msg">Loading…</p>
      )}
    </div>
  );
}
