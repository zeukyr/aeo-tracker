import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { API_BASE_URL } from "../config";
import { formatDate } from "../lib/format";
import { ANGLE_LABELS, PRIORITY_LABELS, schoolLabel } from "../lib/blogIdeas";

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

// Priority | Type | Status info row, directly under the title - mirrors a
// commercial AEO tool's article-detail header, but Priority is computed
// deterministically from real target-query volume/weakness
// (blog_ideas.py's _compute_priority), never LLM-assigned, and Status
// reuses the same idea/drafted/published lifecycle the list view's dropdown
// already edits (no new "approved" state - see BlogIdeaDetail's history:
// deliberately not adding a gate in front of the existing status control).
function InfoBar({ priority, angle, status, onStatusChange }) {
  return (
    <div className="bi-infobar">
      {priority && (
        <div className="bi-infobar__item">
          <span className="bi-infobar__label">Priority</span>
          <span className={`priority-pill priority-pill--${priority}`}>
            {PRIORITY_LABELS[priority] ?? priority}
          </span>
        </div>
      )}
      {angle && (
        <div className="bi-infobar__item">
          <span className="bi-infobar__label">Type</span>
          <span className="angle-tag">{ANGLE_LABELS[angle] ?? angle}</span>
        </div>
      )}
      <div className="bi-infobar__item">
        <span className="bi-infobar__label">Status</span>
        <select
          className={`priority-pill priority-pill--${status}`}
          style={{ border: "none", fontFamily: "inherit", cursor: "pointer" }}
          value={status}
          onChange={(e) => onStatusChange(e.target.value)}
        >
          <option value="idea">Idea</option>
          <option value="drafted">Drafted</option>
          <option value="published">Published</option>
        </select>
      </div>
    </div>
  );
}

// Small colored ring + percentage, same "how often QC is cited" number the
// list-view targets already carried as plain text - just given the same
// glanceable ring treatment a commercial AEO dashboard uses for visibility.
// Thresholds match blog_ideas.py's own _compute_priority breakpoints
// (0.15 / 0.35) so the color language stays consistent front-to-back.
function VisibilityRing({ pct, size = 30 }) {
  const radius = (size - 4) / 2;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference * (1 - Math.max(0, Math.min(100, pct)) / 100);
  const color = pct < 15 ? "#a32d2d" : pct < 35 ? "#ba7517" : "#3b6d11";
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} style={{ flexShrink: 0 }} aria-hidden="true">
      <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke="#edecea" strokeWidth="3" />
      <circle
        cx={size / 2} cy={size / 2} r={radius} fill="none" stroke={color} strokeWidth="3"
        strokeDasharray={circumference} strokeDashoffset={offset} strokeLinecap="round"
        transform={`rotate(-90 ${size / 2} ${size / 2})`}
      />
      <text x="50%" y="52%" textAnchor="middle" dominantBaseline="middle" fontSize="9" fontWeight="700" fill="#111" fontFamily="ui-monospace, monospace">
        {Math.round(pct)}
      </text>
    </svg>
  );
}

// A keyword chip's difficulty/volume come from real data (blog_ideas.py's
// _normalize_keywords): "difficulty" is QC's own average citation share
// across this idea's target queries (low share = harder/more valuable
// gap), "tracked" is a real count of tracked AI-search queries this idea
// targets - never a fabricated external search-volume/difficulty number,
// since we have no such data source (see module note in blog_ideas.py).
const _DIFFICULTY_COLOR = {
  high:   { bg: "#fcebeb", text: "#a32d2d" },
  medium: { bg: "#fbf0de", text: "#ba7517" },
  low:    { bg: "#eaf3de", text: "#3b6d11" },
};

function KeywordChip({ phrase, tracked_queries: tracked, difficulty }) {
  const c = _DIFFICULTY_COLOR[difficulty];
  return (
    <div className="bi-keyword">
      <span className="bi-keyword__phrase">{phrase}</span>
      <span className="bi-keyword__stats">
        {c && (
          <span className="bi-keyword__difficulty" style={{ background: c.bg, color: c.text }}>
            {difficulty} difficulty
          </span>
        )}
        <span className="bi-keyword__tracked">{tracked} tracked quer{tracked === 1 ? "y" : "ies"}</span>
      </span>
    </div>
  );
}

// The screenshot-matching brief: description, rationale, keywords, and the
// prompts this idea addresses - everything a human needs to decide whether
// this idea is worth a full-post LLM call, before ever opening the outline
// below. All of it (except the LLM-authored description/keyword phrases
// themselves) is derived from real tracked-query data, never invented.
function ArticleBrief({ outline }) {
  if (!outline) return null;
  const { description, why_this_article: rationale, keywords, targets } = outline;

  return (
    <>
      {description && (
        <div className="rc-brief__section">
          <span className="rc-brief__eyebrow">Description</span>
          <p className="bi-prose">{description}</p>
        </div>
      )}
      {rationale && (
        <div className="rc-brief__section">
          <span className="rc-brief__eyebrow">Why this article?</span>
          <p className="bi-prose">{rationale}</p>
        </div>
      )}
      {keywords?.length > 0 && (
        <div className="rc-brief__section">
          <span className="rc-brief__eyebrow">Keywords</span>
          <div className="bi-keyword-list">
            {keywords.map((k) => <KeywordChip key={k.phrase} {...k} />)}
          </div>
        </div>
      )}
      {targets?.length > 0 && (
        <div className="rc-brief__section">
          <span className="rc-brief__eyebrow">Addressed Prompts</span>
          <div className="bi-prompt-list">
            {targets.map((t) => (
              <div className="bi-prompt-row" key={t.question_id}>
                <VisibilityRing pct={t.qc_share * 100} />
                <span className="qtext">"{t.text}"</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </>
  );
}

// The existing GEO content-outline fields (H2 heading, extractable answer
// block, body points, comparison structure) that feed
// _build_full_post_prompt - kept as their own section below the brief
// above, rather than removed, since they're still the real input to
// "Generate full post".
function IdeaOutline({ outline }) {
  if (!outline) return null;
  const { heading, extractable_block: block, body_points: points, comparison } = outline;
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
              <p className="panel-title" style={{ marginBottom: 10 }}>{idea.title}</p>
              <InfoBar
                priority={idea.priority}
                angle={idea.angle}
                status={idea.status}
                onStatusChange={handleStatusChange}
              />
            </div>

            <div className="rc-brief">
              <ArticleBrief outline={idea.outline} />

              <p className="rc-brief__eyebrow" style={{ marginTop: 4 }}>Content outline</p>
              <IdeaOutline outline={idea.outline} />

              <FullPostDraft
                body={idea.body}
                title={idea.title}
                generating={generating}
                error={draftError}
                onGenerate={handleGenerateFullPost}
              />
            </div>
          </div>
        )
      ) : (
        <p className="state-msg">Loading…</p>
      )}
    </div>
  );
}
