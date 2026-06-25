import { useEffect, useState } from "react";
import {
  LineChart, Line,
  AreaChart, Area,
  XAxis, YAxis, Tooltip,
  ResponsiveContainer,
} from "recharts";
import { API_BASE_URL } from "../config";
import { useFilter } from "../context/useFilter";

// ─── constants ────────────────────────────────────────────────────────────────
const LLM_ENGINES   = ["chatgpt", "gemini", "perplexity"];
const LLM_LABELS    = { chatgpt: "ChatGPT", gemini: "Gemini", perplexity: "Perplexity" };
const LLM_COLORS    = { chatgpt: "#378add", gemini: "#ba7517", perplexity: "#1d9e75" };
const QC_BLUE       = "#378add";

// ─── small helpers ─────────────────────────────────────────────────────────────
function visColor(score) {
  if (score == null) return "bg-gray-100 text-gray-400";
  if (score >= 30) return "bg-green-100 text-green-700";
  if (score >= 10) return "bg-yellow-100 text-yellow-700";
  return "bg-red-100 text-red-700";
}

function MetricBadge({ value, suffix = "%" }) {
  if (value == null) return <span className="text-gray-300 text-xs">—</span>;
  return (
    <span className={`text-xs font-medium px-2 py-0.5 rounded ${visColor(value)}`}>
      {value}{suffix}
    </span>
  );
}

function SentimentBadge({ value }) {
  if (value == null) return <span className="text-gray-300 text-xs">—</span>;
  const cls = value >= 60
    ? "bg-green-100 text-green-700"
    : value >= 40
    ? "bg-yellow-100 text-yellow-700"
    : "bg-red-100 text-red-700";
  return (
    <span className={`text-xs font-medium px-2 py-0.5 rounded ${cls}`}>
      {value}% pos
    </span>
  );
}

// ─── chart tooltip (matches Sentiment.jsx style) ──────────────────────────────
function ChartTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return (
    <div style={{
      background: "#fff",
      border: "0.5px solid rgba(0,0,0,0.10)",
      borderRadius: 8,
      padding: "8px 12px",
      fontSize: 13,
      boxShadow: "0 2px 8px rgba(0,0,0,0.08)",
    }}>
      <p style={{ color: "#6b6b6b", marginBottom: 6, fontSize: 12 }}>{label}</p>
      {payload.map(p => (
        <p key={p.name} style={{ color: p.color || p.stroke, fontWeight: 500, margin: "2px 0" }}>
          {p.name}: {p.value}%
        </p>
      ))}
    </div>
  );
}

// ─── visibility trend line chart (mention-type prompts) ───────────────────────
function VisibilityChart({ data }) {
  if (!data?.length) return <p className="text-xs text-gray-400 italic">No time-series data yet.</p>;
  return (
    <ResponsiveContainer width="100%" height={200}>
      <LineChart data={data} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
        <XAxis dataKey="day" tick={{ fontSize: 11, fill: "#888780" }} axisLine={false} tickLine={false} />
        <YAxis
          tickFormatter={v => `${v}%`}
          tick={{ fontSize: 11, fill: "#888780" }}
          axisLine={false} tickLine={false}
          width={36} domain={[0, 100]}
        />
        <Tooltip content={<ChartTooltip />} />
        {/* Mention rate and citation rate as paler supporting lines */}
        <Line
          type="monotone" dataKey="mentionRate" name="Mention rate"
          stroke={QC_BLUE} strokeWidth={1} strokeOpacity={0.35} dot={false} />
        <Line
          type="monotone" dataKey="citationRate" name="Citation rate"
          stroke="#1d9e75" strokeWidth={1} strokeOpacity={0.35} dot={false} />
        {/* Visibility = main, bold */}
        <Line
          type="monotone" dataKey="visibility" name="Visibility"
          stroke={QC_BLUE} strokeWidth={2.5} dot={false} />
      </LineChart>
    </ResponsiveContainer>
  );
}

// chart legend helper
function ChartLegend({ items }) {
  return (
    <div style={{ display: "flex", gap: 14, marginBottom: 10, flexWrap: "wrap" }}>
      {items.map(({ label, color, dashed }) => (
        <span key={label} style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 12, color: "#6b6b6b" }}>
          <span style={{
            width: dashed ? 14 : 8,
            height: dashed ? 0 : 8,
            borderRadius: dashed ? 0 : "50%",
            background: dashed ? "none" : color,
            borderTop: dashed ? `2px dashed ${color}` : "none",
            flexShrink: 0,
            opacity: dashed ? 0.5 : 1,
          }} />
          {label}
        </span>
      ))}
    </div>
  );
}

// ─── sentiment area chart (sentiment-type prompts) ────────────────────────────
function SentimentChart({ data }) {
  if (!data?.length) return <p className="text-xs text-gray-400 italic">No time-series data yet.</p>;
  return (
    <ResponsiveContainer width="100%" height={200}>
      <AreaChart data={data} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
        <defs>
          <linearGradient id="tGradPos" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%"  stopColor="#3b6d11" stopOpacity={0.15} />
            <stop offset="95%" stopColor="#3b6d11" stopOpacity={0.02} />
          </linearGradient>
          <linearGradient id="tGradNeu" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%"  stopColor="#854f0b" stopOpacity={0.15} />
            <stop offset="95%" stopColor="#854f0b" stopOpacity={0.02} />
          </linearGradient>
          <linearGradient id="tGradNeg" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%"  stopColor="#a32d2d" stopOpacity={0.15} />
            <stop offset="95%" stopColor="#a32d2d" stopOpacity={0.02} />
          </linearGradient>
        </defs>
        <XAxis dataKey="day" tick={{ fontSize: 11, fill: "#888780" }} axisLine={false} tickLine={false} />
        <YAxis
          tickFormatter={v => `${v}%`}
          tick={{ fontSize: 11, fill: "#888780" }}
          axisLine={false} tickLine={false} width={36}
        />
        <Tooltip content={<ChartTooltip />} />
        <Area type="monotone" dataKey="positive" name="Positive" stroke="#3b6d11" strokeWidth={2} fill="url(#tGradPos)" dot={false} />
        <Area type="monotone" dataKey="neutral"  name="Neutral"  stroke="#854f0b" strokeWidth={2} fill="url(#tGradNeu)" dot={false} />
        <Area type="monotone" dataKey="negative" name="Negative" stroke="#a32d2d" strokeWidth={2} fill="url(#tGradNeg)" dot={false} />
      </AreaChart>
    </ResponsiveContainer>
  );
}

// ─── competitor SOV ranking (right ⅓ panel) ───────────────────────────────────
function CompetitorRanking({ competitors, kind }) {
  if (!competitors?.length) {
    return <p className="text-xs text-gray-400 italic">No competitor data.</p>;
  }
  const maxCount = Math.max(...competitors.map(c => c.count), 1);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      {competitors.slice(0, 8).map((comp, i) => {
        const barPct = Math.round((comp.count / maxCount) * 100);
        const barColor = comp.isQC ? QC_BLUE : "#7c3aed";
        const opacity  = comp.isQC ? 1 : (0.4 + 0.6 * (comp.count / maxCount));
        return (
          <div key={comp.name} style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <span style={{ width: 18, textAlign: "right", fontSize: 12, color: "#9b9b9b", flexShrink: 0 }}>
              {i + 1}
            </span>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
                <span style={{ fontSize: 12, color: comp.isQC ? QC_BLUE : "#111", fontWeight: comp.isQC ? 600 : i === 0 ? 500 : 400 }}>
                  {comp.name}
                  {comp.isQC && (
                    <span className="badge badge--you" style={{ marginLeft: 6, fontSize: 10 }}>YOU</span>
                  )}
                </span>
                <span style={{ fontSize: 11, color: "#6b6b6b", flexShrink: 0, marginLeft: 8 }}>
                  {kind === "mention" && comp.sov != null ? `${comp.sov}%` : comp.count}
                </span>
              </div>
              <div style={{ height: 4, background: "#f0efec", borderRadius: 99, overflow: "hidden" }}>
                <div style={{
                  height: "100%", width: `${barPct}%`,
                  background: barColor, opacity,
                  borderRadius: 99, transition: "width 0.4s ease",
                }} />
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ─── LLM response drawer (slide-in from right) ───────────────────────────────
function ResponseDrawer({ drawer, onClose }) {
  const { open, engine, response, date, promptText } = drawer;

  // Close on Escape
  useEffect(() => {
    if (!open) return;
    const handler = e => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [open, onClose]);

  if (!open) return null;

  const color = LLM_COLORS[engine] || "#888";

  return (
    <>
      {/* backdrop */}
      <div
        onClick={onClose}
        style={{
          position: "fixed", inset: 0, background: "rgba(0,0,0,0.18)", zIndex: 40,
        }}
      />
      {/* panel */}
      <div style={{
        position: "fixed", top: 0, right: 0, bottom: 0,
        width: "min(520px, 90vw)",
        background: "#fff",
        borderLeft: "1px solid #e5e7eb",
        boxShadow: "-4px 0 24px rgba(0,0,0,0.08)",
        zIndex: 50,
        display: "flex", flexDirection: "column",
        overflow: "hidden",
      }}>
        {/* header */}
        <div style={{
          padding: "16px 20px",
          borderBottom: "1px solid #e5e7eb",
          display: "flex", alignItems: "center", justifyContent: "space-between",
          flexShrink: 0,
        }}>
          <div>
            <p style={{ fontSize: 13, fontWeight: 600, color, marginBottom: 2 }}>
              {LLM_LABELS[engine] || engine}
            </p>
            <p style={{ fontSize: 11, color: "#9b9b9b" }}>
              {date ? `Latest response · ${date}` : "Latest response"}
            </p>
          </div>
          <button
            onClick={onClose}
            style={{
              background: "none", border: "none", cursor: "pointer",
              fontSize: 18, color: "#9b9b9b", lineHeight: 1, padding: "4px 8px",
            }}
            aria-label="Close"
          >
            ✕
          </button>
        </div>

        {/* prompt context */}
        {promptText && (
          <div style={{ padding: "12px 20px", borderBottom: "1px solid #f0efec", flexShrink: 0 }}>
            <p style={{ fontSize: 11, color: "#9b9b9b", fontStyle: "italic" }}>
              "{promptText}"
            </p>
          </div>
        )}

        {/* response body */}
        <div style={{ flex: 1, overflowY: "auto", padding: "16px 20px" }}>
          {response
            ? <p style={{ fontSize: 13, color: "#374151", lineHeight: 1.7, whiteSpace: "pre-wrap" }}>
                {response}
              </p>
            : <p style={{ fontSize: 13, color: "#9b9b9b", fontStyle: "italic" }}>No response available.</p>
          }
        </div>
      </div>
    </>
  );
}

// ─── expanded prompt detail panel ─────────────────────────────────────────────
function PromptDetail({ prompt, detail, loading, onOpenDrawer }) {
  if (loading) {
    return (
      <tr>
        <td colSpan={4} className="px-4 pb-4 pt-1">
          <div className="ml-8 bg-gray-50 rounded-lg p-4">
            <p className="text-xs text-gray-400 italic">Loading…</p>
          </div>
        </td>
      </tr>
    );
  }
  if (!detail) return null;

  const { kind, timeseries, competitors, llms } = detail;

  return (
    <tr>
      <td colSpan={4} className="px-4 pb-4 pt-1">
        <div className="ml-8 bg-gray-50 rounded-lg p-4 space-y-4">

          {/* prompt text */}
          <p className="italic text-gray-600 text-sm">"{prompt.text}"</p>

          {/* chart + competitor SOV side by side */}
          <div style={{ display: "flex", gap: 16, alignItems: "flex-start" }}>

            {/* ⅔ chart */}
            <div style={{ flex: 2, minWidth: 0 }}>
              <p className="text-xs font-medium text-gray-500 uppercase mb-2">
                {kind === "mention" ? "Visibility over time" : "Sentiment over time"}
              </p>
              {kind === "mention" ? (
                <>
                  <ChartLegend items={[
                    { label: "Visibility",    color: QC_BLUE },
                    { label: "Mention rate",  color: QC_BLUE, dashed: true },
                    { label: "Citation rate", color: "#1d9e75", dashed: true },
                  ]} />
                  <VisibilityChart data={timeseries} />
                </>
              ) : (
                <>
                  <ChartLegend items={[
                    { label: "Positive", color: "#3b6d11" },
                    { label: "Neutral",  color: "#854f0b" },
                    { label: "Negative", color: "#a32d2d" },
                  ]} />
                  <SentimentChart data={timeseries} />
                </>
              )}
            </div>

            {/* ⅓ competitor ranking */}
            <div style={{ flex: 1, minWidth: 140 }}>
              <p className="text-xs font-medium text-gray-500 uppercase mb-2">
                {kind === "mention" ? "Share of voice" : "Winner frequency"}
              </p>
              <CompetitorRanking competitors={competitors} kind={kind} />
            </div>
          </div>

          {/* per-LLM summaries */}
          <div>
            <p className="text-xs font-medium text-gray-500 uppercase mb-2">LLM Breakdown</p>
            <div className="space-y-2">
              {LLM_ENGINES.map(engine => {
                const llm = llms?.find(l => l.engine === engine);
                const color = LLM_COLORS[engine];
                return (
                  <div key={engine} style={{
                    display: "flex", alignItems: "center", gap: 12,
                    background: "#fff", borderRadius: 8, padding: "8px 12px",
                    border: "1px solid #f0efec",
                  }}>
                    {/* engine label */}
                    <span style={{ fontSize: 12, fontWeight: 600, color, width: 80, flexShrink: 0 }}>
                      {LLM_LABELS[engine]}
                    </span>

                    {/* metrics */}
                    {llm ? (
                      <div style={{ flex: 1, display: "flex", gap: 12, flexWrap: "wrap", alignItems: "center" }}>
                        {llm.kind === "mention" ? (
                          <>
                            <span className="text-xs text-gray-500">
                              Visibility <span className="font-medium text-gray-800">{llm.visibility}%</span>
                            </span>
                            <span className="text-xs text-gray-400">·</span>
                            <span className="text-xs text-gray-500">
                              Mention <span className="font-medium text-gray-800">{llm.mentionRate}%</span>
                            </span>
                            <span className="text-xs text-gray-400">·</span>
                            <span className="text-xs text-gray-500">
                              Citation <span className="font-medium text-gray-800">{llm.citationRate}%</span>
                            </span>
                            <span className="text-xs text-gray-400">·</span>
                            <span className="text-xs text-gray-500">
                              SOV <span className="font-medium text-gray-800">{llm.sov}%</span>
                            </span>
                          </>
                        ) : (
                          <>
                            <span className="text-xs text-gray-500">
                              Positive <span style={{ color: "#3b6d11" }} className="font-medium">{llm.positive}%</span>
                            </span>
                            <span className="text-xs text-gray-400">·</span>
                            <span className="text-xs text-gray-500">
                              Neutral <span style={{ color: "#854f0b" }} className="font-medium">{llm.neutral}%</span>
                            </span>
                            <span className="text-xs text-gray-400">·</span>
                            <span className="text-xs text-gray-500">
                              Negative <span style={{ color: "#a32d2d" }} className="font-medium">{llm.negative}%</span>
                            </span>
                          </>
                        )}
                      </div>
                    ) : (
                      <span className="text-xs text-gray-400 flex-1">No data</span>
                    )}

                    {/* arrow to open drawer */}
                    <button
                      onClick={() => onOpenDrawer(engine, llm, prompt.text)}
                      style={{
                        background: "none", border: "none", cursor: "pointer",
                        color: llm ? color : "#d1d5db",
                        fontSize: 13, padding: "2px 4px",
                        flexShrink: 0,
                      }}
                      title={llm ? `View ${LLM_LABELS[engine]} response` : "No response yet"}
                      aria-label={`Open ${LLM_LABELS[engine]} response`}
                    >
                      ▶
                    </button>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </td>
    </tr>
  );
}

// ─── prompt row ───────────────────────────────────────────────────────────────
function PromptRow({ prompt, expanded, onToggle, detail, detailLoading, onOpenDrawer }) {
  return (
    <>
      <tr
        className="border-t border-gray-100 hover:bg-gray-50 cursor-pointer"
        onClick={onToggle}
      >
        {/* prompt text */}
        <td className="px-4 py-2.5 pl-10">
          <div className="flex items-center gap-2">
            <span className="text-gray-400 text-xs">{expanded ? "▼" : "▶"}</span>
            <span className="text-sm text-gray-700 truncate max-w-sm" title={prompt.text}>
              "{prompt.text}"
            </span>
          </div>
        </td>

        {/* visibility */}
        <td className="px-3 py-2.5">
          <MetricBadge value={prompt.visibility} />
        </td>

        {/* sentiment */}
        <td className="px-3 py-2.5">
          <SentimentBadge value={prompt.sentiment} />
        </td>

        {/* SOV */}
        <td className="px-3 py-2.5">
          <MetricBadge value={prompt.sov} />
        </td>
      </tr>

      {expanded && (
        <PromptDetail
          prompt={prompt}
          detail={detail}
          loading={detailLoading}
          onOpenDrawer={onOpenDrawer}
        />
      )}
    </>
  );
}

// ─── topic header row ─────────────────────────────────────────────────────────
function TopicRow({ topic, expanded, onToggle, expandedPrompts, onTogglePrompt, promptDetails, loadingDetails, onOpenDrawer }) {
  return (
    <>
      <tr
        className="bg-gray-50 cursor-pointer hover:bg-gray-100 border-t border-gray-200"
        onClick={onToggle}
      >
        {/* topic name */}
        <td className="px-4 py-3">
          <div className="flex items-center gap-2">
            <span className="text-gray-500 text-xs">{expanded ? "▼" : "▶"}</span>
            <div>
              <p className="text-sm font-semibold text-gray-800">{topic.name}</p>
              <p className="text-xs text-gray-400">{topic.promptCount} prompts</p>
            </div>
          </div>
        </td>

        {/* visibility */}
        <td className="px-3 py-3">
          <MetricBadge value={topic.visibility} />
        </td>

        {/* sentiment */}
        <td className="px-3 py-3">
          <SentimentBadge value={topic.sentiment} />
        </td>

        {/* SOV */}
        <td className="px-3 py-3">
          <MetricBadge value={topic.sov} />
        </td>
      </tr>

      {expanded && topic.prompts.map(prompt => (
        <PromptRow
          key={prompt.id}
          prompt={prompt}
          expanded={expandedPrompts.has(prompt.id)}
          onToggle={e => { e.stopPropagation(); onTogglePrompt(prompt.id, prompt.kind); }}
          detail={promptDetails[prompt.id]}
          detailLoading={loadingDetails.has(prompt.id)}
          onOpenDrawer={onOpenDrawer}
        />
      ))}
    </>
  );
}

// ─── main Topics component ────────────────────────────────────────────────────
export default function Topics() {
  const { days } = useFilter();
  const [data,          setData]          = useState([]);
  const [loading,       setLoading]       = useState(true);
  const [error,         setError]         = useState(null);
  const [expandedTopics,  setExpandedTopics]  = useState(new Set());
  const [expandedPrompts, setExpandedPrompts] = useState(new Set());
  const [promptDetails,   setPromptDetails]   = useState({});  // id → detail object
  const [loadingDetails,  setLoadingDetails]  = useState(new Set());
  const [drawer, setDrawer] = useState({ open: false, engine: null, response: null, date: null, promptText: null });

  // fetch topic list whenever the day filter changes
  useEffect(() => {
    setLoading(true);
    setError(null);
    setExpandedTopics(new Set());
    setExpandedPrompts(new Set());
    setPromptDetails({});

    const params = new URLSearchParams();
    if (days) params.append("days", days);

    fetch(`${API_BASE_URL}/api/topics?${params}`)
      .then(r => r.json())
      .then(d => { setData(d); setLoading(false); })
      .catch(err => { setError(err.message); setLoading(false); });
  }, [days]);

  function toggleTopic(name) {
    setExpandedTopics(prev => {
      const next = new Set(prev);
      next.has(name) ? next.delete(name) : next.add(name);
      return next;
    });
  }

  function togglePrompt(id, kind) {
    setExpandedPrompts(prev => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
        // lazy-load detail if not yet fetched
        if (!promptDetails[id] && !loadingDetails.has(id)) {
          fetchPromptDetail(id);
        }
      }
      return next;
    });
  }

  function fetchPromptDetail(id) {
    setLoadingDetails(prev => new Set([...prev, id]));
    const params = new URLSearchParams();
    if (days) params.append("days", days);

    fetch(`${API_BASE_URL}/api/topic-prompt/${id}?${params}`)
      .then(r => r.json())
      .then(detail => {
        setPromptDetails(prev => ({ ...prev, [id]: detail }));
        setLoadingDetails(prev => {
          const next = new Set(prev);
          next.delete(id);
          return next;
        });
      })
      .catch(() => {
        setLoadingDetails(prev => {
          const next = new Set(prev);
          next.delete(id);
          return next;
        });
      });
  }

  function openDrawer(engine, llm, promptText) {
    setDrawer({
      open:         true,
      engine,
      response:     llm?.latestResponse ?? null,
      date:         llm?.latestResponseDate ?? null,
      promptText,
    });
  }

  function closeDrawer() {
    setDrawer(d => ({ ...d, open: false }));
  }

  if (loading) return <p className="state-msg">Loading…</p>;
  if (error)   return <p className="state-msg state-msg--error">Error: {error}</p>;
  if (!data.length) return <p className="state-empty">No topic data yet. Run the pipeline to collect responses.</p>;

  return (
    <>
      <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
        <table className="w-full text-left table-fixed">
          <colgroup>
            <col style={{ width: "45%" }} />
            <col style={{ width: "18.33%" }} />
            <col style={{ width: "18.33%" }} />
            <col style={{ width: "18.33%" }} />
          </colgroup>
          <thead>
            <tr className="border-b border-gray-200 bg-gray-50">
              <th className="px-4 py-2.5 text-xs text-gray-500 uppercase font-medium">Prompt / Topic</th>
              <th className="px-3 py-2.5 text-xs text-gray-500 uppercase font-medium">Visibility</th>
              <th className="px-3 py-2.5 text-xs text-gray-500 uppercase font-medium">Sentiment</th>
              <th className="px-3 py-2.5 text-xs text-gray-500 uppercase font-medium">Share of Voice</th>
            </tr>
          </thead>
          <tbody>
            {data.map(topic => (
              <TopicRow
                key={topic.name}
                topic={topic}
                expanded={expandedTopics.has(topic.name)}
                onToggle={() => toggleTopic(topic.name)}
                expandedPrompts={expandedPrompts}
                onTogglePrompt={togglePrompt}
                promptDetails={promptDetails}
                loadingDetails={loadingDetails}
                onOpenDrawer={openDrawer}
              />
            ))}
          </tbody>
        </table>
      </div>

      <ResponseDrawer drawer={drawer} onClose={closeDrawer} />
    </>
  );
}
