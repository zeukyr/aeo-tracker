import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { API_BASE_URL } from "../config";
import { useFilter } from "../context/useFilter";
import { formatDate } from "../lib/format";
import { ANGLE_LABELS, schoolLabel } from "../lib/blogIdeas";

// Summary card linking out to the persona editor's own page
// (/blog-ideas/personas, pages/BlogPersonas.jsx) rather than inlining the
// editor here - it's settings-like content edited occasionally per school,
// not something that needs to sit in the middle of the generation flow.
function PersonaSummary({ personas, onManage }) {
  return (
    <div className="card" style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, flexWrap: "wrap", marginTop: 24 }}>
      <div>
        <p className="panel-title" style={{ marginBottom: 2 }}>Buyer persona, stats & testimonials</p>
        <p className="panel-subtitle" style={{ margin: 0 }}>
          {personas.length > 0
            ? `${personas.length} school${personas.length === 1 ? "" : "s"} configured — used to ground blog idea generation`
            : "Not configured yet — add a school's persona, stats, and testimonials to ground idea generation"}
        </p>
      </div>
      <button className="btn btn--ghost" onClick={onManage}>Manage persona data →</button>
    </div>
  );
}

function AgentAvatar() {
  return (
    <span style={{
      width: 26, height: 26, borderRadius: "50%", background: "#e6f1fb", color: "#185fa5",
      display: "inline-flex", alignItems: "center", justifyContent: "center", flexShrink: 0, fontSize: 13,
    }}>
      ✦
    </span>
  );
}

function AssistantBubble({ children }) {
  return (
    <div style={{ display: "flex", gap: 10, alignItems: "flex-start" }}>
      <AgentAvatar />
      <div style={{ background: "#f7f7f5", borderRadius: 12, padding: "10px 14px", fontSize: 13, color: "#111", lineHeight: 1.55, maxWidth: 560 }}>
        {children}
      </div>
    </div>
  );
}

function ChecklistRow({ children }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 10, background: "#fff", border: "0.5px solid rgba(0,0,0,0.10)", borderRadius: 10, padding: "9px 14px", fontSize: 13 }}>
      <span style={{ width: 18, height: 18, borderRadius: "50%", background: "#eaf3de", color: "#3b6d11", display: "inline-flex", alignItems: "center", justifyContent: "center", fontSize: 11, flexShrink: 0 }}>✓</span>
      <span>{children}</span>
    </div>
  );
}

// Single generation entry point - replaces the old picker (pick a topic/
// school pair) + separate "generate from persona" button with one flow: the
// backend (generate_blog_ideas) auto-picks the highest-yield/weakest
// tracked-query groups and automatically falls back to persona-mined topics
// for any school whose tracked-query bank is thin. This panel only narrates
// what happened - it never asks a human to choose a mode or a topic.
function ContentAgentPanel({ candidates, personas, onGenerate, generating, result, error, genStatus }) {
  const canGenerate = genStatus?.can_generate ?? true;
  const nextDate = genStatus?.next_available_at ? formatDate(genStatus.next_available_at) : null;
  const totalPendingQueries = candidates.reduce((sum, c) => sum + c.n_queries, 0);
  const buttonLabel = !canGenerate ? `Locked until ${nextDate}` : generating ? "Generating…" : "✦ Generate blog ideas";

  return (
    <section className="card" style={{ marginTop: 24, display: "flex", flexDirection: "column", gap: 14 }}>
      <div>
        <p className="panel-title" style={{ marginBottom: 2 }}>Content Agent</p>
        <p className="panel-subtitle" style={{ margin: 0 }}>
          Finds the tracked queries QC is weakest on{personas.length > 0 ? " and mines persona data on rotation" : ""} — one button, no mode to pick.
        </p>
      </div>

      <AssistantBubble>
        I rank your tracked AI-search queries by how rarely QC is actually cited — not by how many phrasings we
        happen to track, which isn't a real demand signal — and draft pillar + cluster ideas for the weakest
        ones{personas.length > 0 ? ". Each run also mines persona data for a couple of schools on rotation, alongside those picks rather than only when the tracked-query bank runs dry" : ""}.
      </AssistantBubble>

      {!result && (
        <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
          <button className="btn btn--primary" onClick={onGenerate} disabled={generating || !canGenerate} title={!canGenerate ? `Available again ${nextDate}` : undefined}>
            {buttonLabel}
          </button>
          <span style={{ fontSize: 12, color: "#6b6b6b" }}>
            {candidates.length > 0
              ? `${candidates.length} uncovered topic/school pair${candidates.length === 1 ? "" : "s"} identified (${totalPendingQueries} tracked queries)`
              : personas.length > 0
                ? "No uncovered tracked-query topics left — will mine persona data instead"
                : "Nothing to generate from yet — add tracked queries or persona data first"}
          </span>
        </div>
      )}

      {error && <p className="state-msg state-msg--error">{error}</p>}

      {result && (
        result.generated ? (
          <>
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              <ChecklistRow>
                Identified {result.identifiedCount} uncovered topic/school pair{result.identifiedCount === 1 ? "" : "s"}
              </ChecklistRow>
              <ChecklistRow>
                Created {result.pillars} pillar idea{result.pillars === 1 ? "" : "s"} + {result.cluster_ideas} cluster idea{result.cluster_ideas === 1 ? "" : "s"}
              </ChecklistRow>
              <ChecklistRow>Saved to your idea backlog below</ChecklistRow>
            </div>
            <AssistantBubble>
              <p style={{ margin: "0 0 6px", fontWeight: 600 }}>
                {result.pillars} new pillar topic{result.pillars === 1 ? "" : "s"}:
              </p>
              <ol style={{ margin: 0, paddingLeft: 18 }}>
                {result.topics.map((t) => (
                  <li key={`bank-${t.topic}-${t.school}`}><b>{t.topic}</b> — {schoolLabel(t.school)} (tracked-query bank)</li>
                ))}
                {result.persona_topics.flatMap((p) =>
                  p.topics.map((topic) => (
                    <li key={`persona-${p.school}-${topic}`}><b>{topic}</b> — {schoolLabel(p.school)} (mined from persona data)</li>
                  ))
                )}
              </ol>
              <p style={{ margin: "8px 0 0", color: "#6b6b6b" }}>
                Click any pillar below to review the outline, then generate a full post for whichever cluster ideas are worth the LLM call.
              </p>
            </AssistantBubble>
          </>
        ) : (
          <AssistantBubble>
            Nothing new to generate right now — every tracked topic and persona-backed school already has an idea.
          </AssistantBubble>
        )
      )}

      {result && (
        <button className="btn btn--ghost" onClick={onGenerate} disabled={generating || !canGenerate} title={!canGenerate ? `Available again ${nextDate}` : undefined} style={{ alignSelf: "flex-start" }}>
          {!canGenerate ? `Locked until ${nextDate}` : generating ? "Generating…" : "Run again"}
        </button>
      )}
    </section>
  );
}

function GenerationHeader({ candidates, pillarCount, clusterCount, coveredQueryCount, draftedCount, lastGeneratedAt }) {
  const totalPendingQueries = candidates.reduce((sum, c) => sum + c.n_queries, 0);

  return (
    <>
      <div className="card rec-header">
        <div>
          <p className="panel-title">Blog Ideas</p>
          <p className="panel-subtitle">Ongoing content backlog for AI visibility — pillar/cluster ideas generated from your tracked-query bank or mined directly from persona data</p>
          <p className="rec-header__meta">
            {totalPendingQueries} tracked queries across {candidates.length} uncovered topic{candidates.length === 1 ? "" : "s"}/school pair{candidates.length === 1 ? "" : "s"}
            {lastGeneratedAt && ` · ideas last generated ${formatDate(lastGeneratedAt)}`}
          </p>
        </div>
      </div>

      <div className="metric-grid">
        <div className="metric-card">
          <span className="metric-label">Pillars</span>
          <span className="metric-value">{pillarCount}</span>
          <p className="metric-detail">one per topic/school pair</p>
        </div>
        <div className="metric-card">
          <span className="metric-label">Cluster ideas</span>
          <span className="metric-value">{clusterCount}</span>
          <p className="metric-detail">across all pillars</p>
        </div>
        <div className="metric-card">
          <span className="metric-label">Queries covered</span>
          <span className="metric-value">{coveredQueryCount}</span>
          <p className="metric-detail">from the tracked-query bank</p>
        </div>
        <div className="metric-card">
          <span className="metric-label">Drafted</span>
          <span className="metric-value">{draftedCount}</span>
          <p className="metric-detail">0 published yet</p>
        </div>
      </div>
    </>
  );
}

// Compact row only - clicking it opens the idea's own page
// (/blog-ideas/:ideaId, pages/BlogIdeaDetail.jsx) where the outline and full
// post draft (generate/regenerate/copy) live. Same compact-row-navigates-to-
// detail-page pattern as RecListItem -> /recommendations/:recId.
function ClusterRow({ cluster, onOpen, onStatusChange }) {
  return (
    <div className="cluster-card">
      <button className="cluster-head" onClick={() => onOpen(cluster.id)}>
        <span className="cluster-caret">→</span>
        <span className="cluster-title">{cluster.title}</span>
        <span className="cluster-chips" onClick={(e) => e.stopPropagation()}>
          <span className="angle-tag">{ANGLE_LABELS[cluster.angle] ?? cluster.angle}</span>
          {cluster.source === "persona" ? (
            <span className="chip chip--segment">from persona</span>
          ) : (
            <span className="chip chip--segment">
              {cluster.target_query_ids.length} quer{cluster.target_query_ids.length === 1 ? "y" : "ies"}
            </span>
          )}
          <select
            className={`priority-pill priority-pill--${cluster.status}`}
            style={{ border: "none", fontFamily: "inherit", cursor: "pointer" }}
            value={cluster.status}
            onChange={(e) => onStatusChange(cluster.id, e.target.value)}
          >
            <option value="idea">Idea</option>
            <option value="drafted">Drafted</option>
            <option value="published">Published</option>
          </select>
        </span>
      </button>
    </div>
  );
}

function PillarCard({ pillar, clusters, open, onTogglePillar, onOpenIdea, onStatusChange }) {
  return (
    <div className="card pillar-card">
      <button className="pillar-head" onClick={onTogglePillar}>
        <span className="pillar-caret">{open ? "▾" : "▸"}</span>
        <span className="pillar-topic">{pillar.topic}</span>
        <div className="pillar-body">
          <p className="pillar-title">
            {pillar.title}
            {pillar.source === "persona" && <span className="chip chip--segment" style={{ marginLeft: 6 }}>from persona</span>}
          </p>
          <p className="pillar-meta">
            {schoolLabel(pillar.school)} · pillar page · links out to {clusters.length} cluster post{clusters.length === 1 ? "" : "s"} below
          </p>
        </div>
        <span className="pillar-stat">
          {pillar.source === "persona" ? "persona-sourced" : `${pillar.target_query_ids.length} queries`} · {clusters.length} ideas
        </span>
      </button>
      {open && (
        <div className="cluster-list">
          {clusters.map((c) => (
            <ClusterRow key={c.id} cluster={c} onOpen={onOpenIdea} onStatusChange={onStatusChange} />
          ))}
        </div>
      )}
    </div>
  );
}

function BlogIdeas() {
  const navigate = useNavigate();
  const { days } = useFilter();
  const [ideas, setIdeas] = useState(null);
  const [genStatus, setGenStatus] = useState(null);
  const [candidates, setCandidates] = useState([]);
  const [error, setError] = useState(null);
  const [openPillars, setOpenPillars] = useState(() => new Set());
  const [personas, setPersonas] = useState([]);
  const [generating, setGenerating] = useState(false);
  const [genResult, setGenResult] = useState(null);
  const [genError, setGenError] = useState(null);

  const loading = ideas === null && error === null;

  const loadIdeas = () => {
    Promise.all([
      fetch(`${API_BASE_URL}/api/blog-ideas`).then((r) => r.json()),
      fetch(`${API_BASE_URL}/api/blog-ideas/generation-status`).then((r) => r.json()),
    ])
      .then(([data, gen]) => {
        setIdeas(Array.isArray(data) ? data : []);
        setGenStatus(gen);
      })
      .catch((err) => setError(err.message));
  };

  const loadPersonas = () => {
    fetch(`${API_BASE_URL}/api/blog-personas`)
      .then((r) => r.json())
      .then((data) => setPersonas(Array.isArray(data) ? data : []))
      .catch(() => {});
  };

  const loadCandidates = () => {
    const params = new URLSearchParams();
    if (days) params.append("days", days);
    fetch(`${API_BASE_URL}/api/blog-ideas/candidates?${params}`)
      .then((r) => r.json())
      .then((data) => setCandidates(Array.isArray(data) ? data : []))
      .catch((err) => setError(err.message));
  };

  useEffect(() => {
    loadIdeas();
    loadPersonas();
  }, []);

  useEffect(() => {
    loadCandidates();
  }, [days]);

  const handleGenerate = () => {
    setGenerating(true);
    setGenError(null);
    // Captured before the request fires, since a successful run immediately
    // shrinks the live candidate list (loadCandidates() below) - the
    // narration should report what was true when the agent started, not
    // the post-generation count.
    const identifiedCount = candidates.length;

    const params = new URLSearchParams();
    if (days) params.append("days", days);

    fetch(`${API_BASE_URL}/api/blog-ideas/generate?${params}`, { method: "POST" })
      .then((r) => {
        if (!r.ok) return r.json().then((body) => { throw new Error(body?.detail?.message || "Generation failed"); });
        return r.json();
      })
      .then((result) => {
        setGenResult({ ...result, identifiedCount });
        setGenerating(false);
        loadIdeas();
        loadCandidates();
      })
      .catch((err) => {
        setGenError(err.message);
        setGenerating(false);
      });
  };

  const handleStatusChange = (ideaId, status) => {
    setIdeas((prev) => prev.map((i) => (i.id === ideaId ? { ...i, status } : i)));
    fetch(`${API_BASE_URL}/api/blog-ideas/${ideaId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status }),
    }).catch((err) => console.error("Failed to update blog idea status:", err));
  };

  const togglePillar = (id) => setOpenPillars((prev) => {
    const next = new Set(prev);
    next.has(id) ? next.delete(id) : next.add(id);
    return next;
  });

  const openIdea = (ideaId) => navigate(`/blog-ideas/${ideaId}`);

  if (error) return <p className="state-msg state-msg--error">Error: {error}</p>;
  if (loading) return <p className="state-msg">Loading...</p>;

  const pillars = ideas.filter((i) => i.cluster_role === "pillar");
  const clusters = ideas.filter((i) => i.cluster_role === "cluster");
  const clustersByParent = clusters.reduce((acc, c) => {
    (acc[c.parent_id] ??= []).push(c);
    return acc;
  }, {});
  const coveredQueryCount = new Set(pillars.flatMap((p) => p.target_query_ids)).size;
  const draftedCount = clusters.filter((c) => c.status === "drafted" || c.status === "published").length;
  const lastGeneratedAt = genStatus?.last_generated_at ?? null;

  return (
    <div className="bi-page">
      <GenerationHeader
        candidates={candidates}
        pillarCount={pillars.length}
        clusterCount={clusters.length}
        coveredQueryCount={coveredQueryCount}
        draftedCount={draftedCount}
        lastGeneratedAt={lastGeneratedAt}
      />

      <PersonaSummary personas={personas} onManage={() => navigate("/blog-ideas/personas")} />

      <ContentAgentPanel
        candidates={candidates}
        personas={personas}
        onGenerate={handleGenerate}
        generating={generating}
        result={genResult}
        error={genError}
        genStatus={genStatus}
      />

      {pillars.length === 0 ? (
        <p className="state-empty">
          No blog ideas yet — click "Generate blog ideas" above to create your first pillar/cluster plan.
        </p>
      ) : (
        <div className="pillar-list">
          {pillars.map((p) => (
            <PillarCard
              key={p.id}
              pillar={p}
              clusters={clustersByParent[p.id] ?? []}
              open={openPillars.has(p.id)}
              onTogglePillar={() => togglePillar(p.id)}
              onOpenIdea={openIdea}
              onStatusChange={handleStatusChange}
            />
          ))}
        </div>
      )}
    </div>
  );
}

export default BlogIdeas;
