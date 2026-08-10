import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { API_BASE_URL } from "../config";
import { useFilter } from "../context/useFilter";
import { formatDate } from "../lib/format";
import { ANGLE_LABELS, schoolLabel, keyOf, parseKey } from "../lib/blogIdeas";

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

// Second ideation entry point, alongside TopicCandidatePicker below: instead
// of picking a (topic, school) pair off the tracked-query bank, pick a
// school with saved persona data and let the model mine that data directly
// for topics no tracked query has surfaced yet. Only schools that actually
// have a saved persona are selectable - generation would just fail
// (reason: "no_persona") for any other school.
function PersonaTopicGenerator({ personas, onGenerate, generating, result, genStatus }) {
  // No default-selection effect: the fallback to personas[0] is computed
  // inline below instead, so an unset/stale `school` (e.g. the previously
  // selected school's persona got cleared) self-corrects on every render
  // without a setState-in-effect render cascade.
  const [school, setSchool] = useState(null);
  const canGenerate = genStatus?.can_generate ?? true;
  const nextDate = genStatus?.next_available_at ? formatDate(genStatus.next_available_at) : null;

  if (!personas.length) return null;

  const selectedSchool = personas.some((p) => p.school === school) ? school : personas[0].school;

  return (
    <section className="card" style={{ marginTop: 24, display: "flex", flexDirection: "column", gap: 10 }}>
      <div>
        <p className="panel-title" style={{ marginBottom: 2 }}>Generate topics from persona data</p>
        <p className="panel-subtitle" style={{ margin: 0 }}>
          Mine a school's buyer persona, stats, and testimonials directly for new topics — no tracked query required.
        </p>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
        <select
          className="text-sm border border-gray-200 rounded px-3 py-1.5"
          value={selectedSchool ?? ""}
          disabled={generating}
          onChange={(e) => setSchool(e.target.value === "" ? null : e.target.value)}
        >
          {personas.map((p) => (
            <option key={p.school ?? ""} value={p.school ?? ""}>
              {schoolLabel(p.school)}
            </option>
          ))}
        </select>
        <button
          className="btn btn--primary"
          onClick={() => onGenerate(selectedSchool)}
          disabled={generating || !canGenerate}
          title={!canGenerate ? `Available again ${nextDate}` : undefined}
        >
          {generating ? "Generating…" : !canGenerate ? `Locked until ${nextDate}` : "Generate topics"}
        </button>
        {result && (
          <span className={`candidate-row__result candidate-row__result--${result.status}`}>{result.message}</span>
        )}
      </div>
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

// Checklist of (topic, school) pairs not yet covered by a pillar - a human
// checks off which ones to spend an LLM call on, then fires them in one
// request. Same structural pattern as Recommendations.jsx's
// CandidateQuestionPicker (checkbox rows -> selected count -> one generate
// button -> per-row result), reusing its generic .candidate-panel__*/
// .candidate-row__* CSS, which was never blog-specific.
function TopicCandidatePicker({ candidates, selected, onToggle, onGenerate, generating, rowResults, genStatus, personaSchools }) {
  const [open, setOpen] = useState(true);
  if (!candidates.length) return null;
  const selectedCount = selected.size;
  const canGenerate = genStatus?.can_generate ?? true;
  const nextDate = genStatus?.next_available_at ? formatDate(genStatus.next_available_at) : null;

  return (
    <section className="candidate-panel">
      <div className="candidate-panel__head">
        <button className="candidate-panel__toggle" onClick={() => setOpen(!open)}>
          <span>{open ? "▾" : "▸"} Select topic/school pairs to generate blog ideas for — {candidates.length} uncovered</span>
        </button>
      </div>
      {open && (
        <>
          <div className="candidate-panel__list">
            {candidates.map((c, i) => {
              const key = keyOf(c.topic, c.school);
              const result = rowResults[key];
              const busy = generating && result?.status === "generating";
              return (
                <label className="candidate-row" key={key}>
                  <input
                    type="checkbox"
                    checked={selected.has(key)}
                    disabled={generating}
                    onChange={() => onToggle(key)}
                  />
                  <span className="candidate-row__rank">#{i + 1}</span>
                  <div className="candidate-row__body">
                    <p className="candidate-row__question">
                      {c.topic} — {schoolLabel(c.school)}
                      {personaSchools.has(c.school) && <span className="chip chip--segment" style={{ marginLeft: 6 }}>persona data</span>}
                    </p>
                    <p className="candidate-row__meta">
                      {c.n_queries} tracked queries · weakest {Math.round(c.weakest_qc_share * 100)}% QC cited
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
              disabled={selectedCount === 0 || generating || !canGenerate}
              title={!canGenerate ? `Available again ${nextDate}` : undefined}
            >
              {generating
                ? "Generating…"
                : !canGenerate
                  ? `Locked until ${nextDate}`
                  : selectedCount > 0
                    ? `Generate ideas for ${selectedCount} selected`
                    : "Select topics to generate"}
            </button>
          </div>
        </>
      )}
    </section>
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
  const [selected, setSelected] = useState(() => new Set());
  const [generatingSelected, setGeneratingSelected] = useState(false);
  const [rowResults, setRowResults] = useState({});
  const [openPillars, setOpenPillars] = useState(() => new Set());
  const [personas, setPersonas] = useState([]);
  const [generatingPersona, setGeneratingPersona] = useState(false);
  const [personaGenResult, setPersonaGenResult] = useState(null);

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

  const personaSchools = new Set(personas.map((p) => p.school));

  const toggleSelected = (key) => {
    setSelected((prev) => {
      const next = new Set(prev);
      next.has(key) ? next.delete(key) : next.add(key);
      return next;
    });
  };

  const handleGenerateSelected = () => {
    const keys = Array.from(selected);
    if (!keys.length) return;
    setGeneratingSelected(true);
    setRowResults((prev) => {
      const next = { ...prev };
      keys.forEach((k) => { next[k] = { status: "generating" }; });
      return next;
    });

    const params = new URLSearchParams();
    if (days) params.append("days", days);
    const selections = keys.map(parseKey);

    fetch(`${API_BASE_URL}/api/blog-ideas/generate?${params}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ selections }),
    })
      .then((r) => {
        if (!r.ok) return r.json().then((body) => { throw new Error(body?.detail?.message || "Generation failed"); });
        return r.json();
      })
      .then((result) => {
        const succeededKeys = new Set((result.topics ?? []).map((s) => keyOf(s.topic, s.school)));
        const skippedKeys = new Set((result.skipped_topics ?? []).map((s) => keyOf(s.topic, s.school)));
        setRowResults((prev) => {
          const next = { ...prev };
          keys.forEach((k) => {
            if (succeededKeys.has(k)) {
              next[k] = { status: "success", message: "Generated." };
            } else if (skippedKeys.has(k)) {
              next[k] = { status: "error", message: "Couldn't generate a usable idea for this pair — try again later." };
            } else {
              next[k] = { status: "error", message: "Not generated — already covered or the bank changed." };
            }
          });
          return next;
        });
        setGeneratingSelected(false);
        setSelected(new Set());
        loadIdeas();
        loadCandidates();
      })
      .catch((err) => {
        setRowResults((prev) => {
          const next = { ...prev };
          keys.forEach((k) => { next[k] = { status: "error", message: err.message }; });
          return next;
        });
        setGeneratingSelected(false);
      });
  };

  const handleGeneratePersona = (school) => {
    setGeneratingPersona(true);
    setPersonaGenResult(null);
    fetch(`${API_BASE_URL}/api/blog-ideas/generate-from-persona`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ school }),
    })
      .then((r) => {
        if (!r.ok) return r.json().then((body) => { throw new Error(body?.detail?.message || "Generation failed"); });
        return r.json();
      })
      .then((result) => {
        const topicList = (result.topics ?? []).join(", ");
        setPersonaGenResult({
          status: "success",
          message: `Generated ${result.pillars} topic${result.pillars === 1 ? "" : "s"}${topicList ? `: ${topicList}` : ""}.`,
        });
        setGeneratingPersona(false);
        loadIdeas();
      })
      .catch((err) => {
        setPersonaGenResult({ status: "error", message: err.message });
        setGeneratingPersona(false);
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

      <PersonaTopicGenerator
        personas={personas}
        onGenerate={handleGeneratePersona}
        generating={generatingPersona}
        result={personaGenResult}
        genStatus={genStatus}
      />

      <TopicCandidatePicker
        candidates={candidates}
        selected={selected}
        onToggle={toggleSelected}
        onGenerate={handleGenerateSelected}
        generating={generatingSelected}
        rowResults={rowResults}
        genStatus={genStatus}
        personaSchools={personaSchools}
      />

      {pillars.length === 0 ? (
        <p className="state-empty">
          No blog ideas yet — select topic/school pairs above and generate a pillar/cluster plan from your tracked-query bank.
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
