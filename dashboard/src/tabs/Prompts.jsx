import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  LineChart, Line,
  XAxis, YAxis, Tooltip,
  ResponsiveContainer,
} from "recharts";
import { API_BASE_URL } from "../config";
import { useFilter } from "../context/useFilter";
import { ChartTooltip } from "../components/PromptMetricsPanel";

// One colour per topic — 6 distinct, none clash with each other or LLM colours
const TOPIC_COLORS = {
  "Career Exploration":    "#378add",
  "How to Become":         "#1d9e75",
  "Starting a Business":   "#7c3aed",
  "Course Discovery":      "#ba7517",
  "Brand Credibility":     "#d6336c",
  "Competitor Comparison": "#0ca678",
};
const FALLBACK_COLORS = ["#378add","#1d9e75","#7c3aed","#ba7517","#d6336c","#0ca678"];

// ─── prompt filter bar (engine / type / mentioned / sentiment; school is global, see App.jsx) ─
const ENGINES = ["All", "chatgpt", "perplexity", "gemini"];
const TYPES = ["All", "course", "general", "credibility", "competition"];
const SENTIMENTS = ["All", "positive", "neutral", "negative"];

function FilterSelect({ label, value, onChange, options }) {
  return (
    <div className="flex flex-col gap-1">
      <label className="text-xs text-gray-500">{label}</label>
      <select
        className="text-sm border border-gray-200 rounded px-2 py-1"
        value={value}
        onChange={e => onChange(e.target.value)}
      >
        {options.map(o => (
          <option key={typeof o === "string" ? o : o.value} value={typeof o === "string" ? o : o.value}>
            {typeof o === "string" ? o : o.label}
          </option>
        ))}
      </select>
    </div>
  );
}

// ─── small helpers ─────────────────────────────────────────────────────────────
function visColor(score) {
  if (score == null) return "bg-gray-100 text-gray-400";
  if (score >= 30) return "bg-green-100 text-green-700";
  if (score >= 10) return "bg-yellow-100 text-yellow-700";
  return "bg-red-100 text-red-700";
}

// Unified metric badge — shows visibility % for mention topics, positive-sentiment % for sentiment topics
function MetricBadge({ topic }) {
  if (topic.visibility != null) {
    const val = topic.visibility;
    return (
      <span className={`text-xs font-medium px-2 py-0.5 rounded ${visColor(val)}`}>
        {val}% vis
      </span>
    );
  }
  if (topic.sentiment != null) {
    const val = topic.sentiment;
    const cls = val >= 60
      ? "bg-green-100 text-green-700"
      : val >= 40
      ? "bg-yellow-100 text-yellow-700"
      : "bg-red-100 text-red-700";
    return (
      <span className={`text-xs font-medium px-2 py-0.5 rounded ${cls}`}>
        {val}% pos
      </span>
    );
  }
  return <span className="text-gray-300 text-xs">—</span>;
}

function SovBadge({ value }) {
  if (value == null) return <span className="text-gray-300 text-xs">—</span>;
  return (
    <span className={`text-xs font-medium px-2 py-0.5 rounded ${visColor(value)}`}>
      {value}%
    </span>
  );
}

// ─── top-level topics-over-time chart ─────────────────────────────────────────
function TopicsOverTimeChart({ chartData }) {
  if (!chartData) return null;
  const { topics, series } = chartData;

  const visTopics  = topics.filter(t => t.kind === "mention");
  const sentTopics = topics.filter(t => t.kind === "sentiment");

  const renderHalf = (halfTopics, subtitle) => (
    <div style={{ flex: 1, minWidth: 0 }}>
      <p style={{ fontSize: 11, fontWeight: 600, color: "#6b6b6b", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 8 }}>
        {subtitle}
      </p>
      <div style={{ display: "flex", gap: 12, marginBottom: 10, flexWrap: "wrap" }}>
        {halfTopics.map(t => {
          const color = TOPIC_COLORS[t.name] || "#888";
          return (
            <span key={t.name} style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 11, color: "#6b6b6b" }}>
              <span style={{ width: 8, height: 8, borderRadius: "50%", background: color, flexShrink: 0 }} />
              {t.name}
            </span>
          );
        })}
      </div>
      {series?.length && halfTopics.length ? (
        <ResponsiveContainer width="100%" height={200}>
          <LineChart data={series} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
            <XAxis dataKey="day" tick={{ fontSize: 11, fill: "#888780" }} axisLine={false} tickLine={false} />
            <YAxis
              tickFormatter={v => `${v}%`}
              tick={{ fontSize: 11, fill: "#888780" }}
              axisLine={false} tickLine={false}
              width={36} domain={[0, 100]}
            />
            <Tooltip content={<ChartTooltip />} />
            {halfTopics.map(t => {
              const color = TOPIC_COLORS[t.name] || "#888";
              return (
                <Line
                  key={t.name}
                  type="monotone"
                  dataKey={t.name}
                  name={t.name}
                  stroke={color}
                  strokeWidth={2}
                  dot={{ r: 3, strokeWidth: 0, fill: color }}
                  activeDot={{ r: 5 }}
                  connectNulls
                />
              );
            })}
          </LineChart>
        </ResponsiveContainer>
      ) : (
        <p className="state-empty" style={{ fontSize: 12 }}>No data yet.</p>
      )}
    </div>
  );

  return (
    <div className="card" style={{ marginBottom: 12 }}>
      <p className="panel-title">Topics over time</p>
      <div style={{ display: "flex", gap: 24, marginTop: 4 }}>
        {renderHalf(visTopics, "Visibility")}
        <div style={{ width: 1, background: "#f0efec", flexShrink: 0 }} />
        {renderHalf(sentTopics, "Sentiment")}
      </div>
    </div>
  );
}

// ─── chart legend helper ───────────────────────────────────────────────────────
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
        <Line type="monotone" dataKey="mentionRate"  name="Mention rate"  stroke={QC_BLUE}   strokeWidth={1} strokeOpacity={0.35} dot={false} />
        <Line type="monotone" dataKey="citationRate" name="Citation rate" stroke="#1d9e75"  strokeWidth={1} strokeOpacity={0.35} dot={false} />
        <Line type="monotone" dataKey="visibility"   name="Visibility"    stroke={QC_BLUE}   strokeWidth={2.5} dot={false} />
      </LineChart>
    </ResponsiveContainer>
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
        <YAxis tickFormatter={v => `${v}%`} tick={{ fontSize: 11, fill: "#888780" }} axisLine={false} tickLine={false} width={36} />
        <Tooltip content={<ChartTooltip />} />
        <Area type="monotone" dataKey="positive" name="Positive" stroke="#3b6d11" strokeWidth={2} fill="url(#tGradPos)" dot={false} />
        <Area type="monotone" dataKey="neutral"  name="Neutral"  stroke="#854f0b" strokeWidth={2} fill="url(#tGradNeu)" dot={false} />
        <Area type="monotone" dataKey="negative" name="Negative" stroke="#a32d2d" strokeWidth={2} fill="url(#tGradNeg)" dot={false} />
      </AreaChart>
    </ResponsiveContainer>
  );
}

// ─── competitor ranking panel (right ⅓) ──────────────────────────────────────
// Branching behaviour:
//   • visibility != null  → ranked bar rows by mention-rate %
//   • visibility == null  → plain name pills (sentiment prompts, no mention data)
function CompetitorRanking({ competitors }) {
  if (!competitors?.length) {
    return <p className="text-xs text-gray-400 italic">No competitor data.</p>;
  }

  const hasVisibility = competitors.some(c => c.visibility != null);

  if (!hasVisibility) {
    // Plain pill list for sentiment prompts
    return (
      <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
        {competitors.map(c => (
          <span key={c.name} style={{
            fontSize: 11, padding: "3px 10px", borderRadius: 99,
            background: c.isQC ? "#dbeafe" : "#f0efec",
            color:      c.isQC ? QC_BLUE   : "#4b5563",
            fontWeight: c.isQC ? 600 : 400,
          }}>
            {c.name}{c.isQC ? " (YOU)" : ""}
          </span>
        ))}
      </div>
    );
  }

  // Ranked bars by visibility (mention rate %)
  const maxVis = Math.max(...competitors.map(c => c.visibility || 0), 1);
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      {competitors.slice(0, 8).map((comp, i) => {
        const barPct   = Math.round(((comp.visibility || 0) / maxVis) * 100);
        const barColor = comp.isQC ? QC_BLUE : "#7c3aed";
        const opacity  = comp.isQC ? 1 : (0.4 + 0.6 * ((comp.visibility || 0) / maxVis));
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
                  {comp.visibility}%
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

// ─── LLM stat node badge ──────────────────────────────────────────────────────
function StatNode({ label, value, color }) {
  if (value == null) return null;
  return (
    <div style={{
      display: "flex", flexDirection: "column", alignItems: "center",
      background: "#f4f4f2", borderRadius: 8,
      padding: "4px 10px", minWidth: 52,
    }}>
      <span style={{ fontSize: 10, color: "#9b9b9b", textTransform: "uppercase", letterSpacing: "0.04em", lineHeight: 1.3 }}>
        {label}
      </span>
      <span style={{ fontSize: 13, fontWeight: 600, color: color || "#374151", lineHeight: 1.3 }}>
        {value}%
      </span>
    </div>
  );
}

// ─── LLM response drawer (slide-in from right, with prev/next history nav) ───
function ResponseDrawer({ drawer, onClose }) {
  const { open, engine, promptText, promptId } = drawer;
  const { days } = useFilter();
  const [history, setHistory] = useState([]);
  const [index, setIndex] = useState(0);
  const [loading, setLoading] = useState(false);

  // Fetch the full response history for this (prompt, engine) pair whenever the drawer opens
  useEffect(() => {
    if (!open || !promptId || !engine) return;
    setLoading(true);
    setIndex(0);
    const params = new URLSearchParams({ engine });
    if (days) params.append("days", days);

    fetch(`${API_BASE_URL}/api/topic-prompt/${promptId}/responses?${params}`)
      .then(r => r.json())
      .then(rows => {
        setHistory(Array.isArray(rows) ? rows : []);
        setLoading(false);
      })
      .catch(() => {
        setHistory([]);
        setLoading(false);
      });
  }, [open, promptId, engine, days]);

  const total = history.length;
  const goPrevious = () => setIndex(i => Math.min(i + 1, total - 1));
  const goNext = () => setIndex(i => Math.max(i - 1, 0));

  useEffect(() => {
    if (!open) return;
    const handler = e => {
      if (e.key === "Escape") onClose();
      if (e.key === "ArrowLeft") setIndex(i => Math.min(i + 1, total - 1));
      if (e.key === "ArrowRight") setIndex(i => Math.max(i - 1, 0));
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [open, onClose, total]);

  if (!open) return null;
  const color = LLM_COLORS[engine] || "#888";
  const current = history[index];

  return (
    <>
      <div onClick={onClose} style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.18)", zIndex: 40 }} />
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
              {loading
                ? "Loading…"
                : total > 0
                  ? `Response ${index + 1} of ${total} · ${current?.date ?? ""}`
                  : "No responses"}
            </p>
          </div>
          <button
            onClick={onClose}
            style={{ background: "none", border: "none", cursor: "pointer", fontSize: 18, color: "#9b9b9b", lineHeight: 1, padding: "4px 8px" }}
            aria-label="Close"
          >
            ✕
          </button>
        </div>

        {/* prompt context */}
        {promptText && (
          <div style={{ padding: "12px 20px", borderBottom: "1px solid #f0efec", flexShrink: 0 }}>
            <p style={{ fontSize: 11, color: "#9b9b9b", fontStyle: "italic" }}>"{promptText}"</p>
          </div>
        )}

        {/* prev / next navigation */}
        {total > 1 && (
          <div style={{
            padding: "8px 20px",
            borderBottom: "1px solid #f0efec",
            display: "flex", alignItems: "center", justifyContent: "space-between",
            flexShrink: 0,
          }}>
            <button
              onClick={goPrevious}
              disabled={index >= total - 1}
              style={{
                background: "none", border: "none", cursor: index >= total - 1 ? "default" : "pointer",
                fontSize: 12, color: index >= total - 1 ? "#d1d5db" : "#374151",
                display: "flex", alignItems: "center", gap: 4, padding: "4px 6px",
              }}
              aria-label="Previous response"
            >
              ← Previous
            </button>
            <button
              onClick={goNext}
              disabled={index <= 0}
              style={{
                background: "none", border: "none", cursor: index <= 0 ? "default" : "pointer",
                fontSize: 12, color: index <= 0 ? "#d1d5db" : "#374151",
                display: "flex", alignItems: "center", gap: 4, padding: "4px 6px",
              }}
              aria-label="Next response"
            >
              Next →
            </button>
          </div>
        )}

        {/* response body */}
        <div style={{ flex: 1, overflowY: "auto", padding: "16px 20px" }}>
          {loading
            ? <p style={{ fontSize: 13, color: "#9b9b9b", fontStyle: "italic" }}>Loading…</p>
            : current?.response
              ? <p style={{ fontSize: 13, color: "#374151", lineHeight: 1.7, whiteSpace: "pre-wrap" }}>{current.response}</p>
              : <p style={{ fontSize: 13, color: "#9b9b9b", fontStyle: "italic" }}>No response available.</p>
          }
        </div>
      </div>
    </>
  );
}

// ─── fanout queries expandable section ───────────────────────────────────────
function FanoutQueriesSection({ promptId }) {
  const [open, setOpen] = useState(false);

  return (
    <div style={{ borderTop: "1px solid #f0efec", marginTop: 4 }}>
      <button
        onClick={() => setOpen(o => !o)}
        style={{
          display: "flex", alignItems: "center", gap: 6,
          width: "100%", background: "none", border: "none",
          cursor: "pointer", padding: "8px 0", textAlign: "left",
        }}
      >
        <span style={{ fontSize: 10, color: "#9b9b9b", transition: "transform 0.15s", display: "inline-block", transform: open ? "rotate(90deg)" : "rotate(0deg)" }}>
          ▶
        </span>
        <span style={{ fontSize: 11, fontWeight: 600, color: "#6b6b6b", textTransform: "uppercase", letterSpacing: "0.05em" }}>
          Fanout Queries
        </span>
      </button>

      {open && (
        <div style={{ paddingBottom: 8 }}>
          <p className="text-xs text-gray-400 italic">No fanout queries loaded yet.</p>
        </div>
      )}
    </div>
  );
}

// ─── expanded prompt detail panel ─────────────────────────────────────────────
function PromptDetail({ prompt, detail, loading, error, onOpenDrawer }) {
  if (loading) {
    return (
      <tr>
        <td colSpan={3} className="px-4 pb-4 pt-1">
          <div className="ml-8 bg-gray-50 rounded-lg p-4">
            <p className="text-xs text-gray-400 italic">Loading…</p>
          </div>
        </td>
      </tr>
    );
  }
  if (error) {
    return (
      <tr>
        <td colSpan={3} className="px-4 pb-4 pt-1">
          <div className="ml-8 bg-gray-50 rounded-lg p-4">
            <p className="text-xs text-red-500">Failed to load detail ({error}). Restart the backend server and reload.</p>
          </div>
        </td>
      </tr>
    );
  }
  if (!detail) return null;

  const { kind, timeseries, competitors, llms } = detail;

  return (
    <tr>
      <td colSpan={3} className="px-4 pb-4 pt-1">
        <div className="ml-8 bg-gray-50 rounded-lg p-4 space-y-4">

          {/* prompt text */}
          <p className="italic text-gray-600 text-sm">"{prompt.text}"</p>

          {/* chart (⅔) + competitors (⅓) */}
          <div style={{ display: "flex", gap: 16, alignItems: "flex-start" }}>

            {/* chart */}
            <div style={{ flex: 2, minWidth: 0 }}>
              <p className="text-xs font-medium text-gray-500 uppercase mb-2">
                {kind === "mention" ? "Visibility over time" : "Sentiment over time"}
              </p>
              {kind === "mention" ? (
                <>
                  <ChartLegend items={[
                    { label: "Visibility",    color: QC_BLUE },
                    { label: "Mention rate",  color: QC_BLUE,  dashed: true },
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

            {/* competitor panel */}
            <div style={{ flex: 1, minWidth: 140 }}>
              <p className="text-xs font-medium text-gray-500 uppercase mb-2">Top competitors</p>
              <CompetitorRanking competitors={competitors} />
            </div>
          </div>

          {/* per-LLM breakdown */}
          <div>
            <p className="text-xs font-medium text-gray-500 uppercase mb-2">LLM Breakdown</p>
            <div className="space-y-2">
              {LLM_ENGINES.map(engine => {
                const llm   = llms?.find(l => l.engine === engine);
                const color = LLM_COLORS[engine];
                return (
                  <div key={engine} style={{
                    display: "flex", alignItems: "center", gap: 12,
                    background: "#fff", borderRadius: 8, padding: "8px 12px",
                    border: "1px solid #f0efec",
                  }}>
                    {/* engine label */}
                    <span style={{ fontSize: 12, fontWeight: 600, color, width: 82, flexShrink: 0 }}>
                      {LLM_LABELS[engine]}
                    </span>

                    {/* stat node badges */}
                    {llm ? (
                      <div style={{ flex: 1, display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center" }}>
                        {llm.kind === "mention" ? (
                          <>
                            <StatNode label="Vis"      value={llm.visibility}   color={QC_BLUE}   />
                            <StatNode label="Mention"  value={llm.mentionRate}  color="#374151"   />
                            <StatNode label="Citation" value={llm.citationRate} color="#374151"   />
                            <StatNode label="SOV"      value={llm.sov}          color="#7c3aed"   />
                          </>
                        ) : (
                          <>
                            <StatNode label="Pos" value={llm.positive} color="#3b6d11" />
                            <StatNode label="Neu" value={llm.neutral}  color="#854f0b" />
                            <StatNode label="Neg" value={llm.negative} color="#a32d2d" />
                          </>
                        )}
                      </div>
                    ) : (
                      <span className="text-xs text-gray-400 flex-1">No data</span>
                    )}

                    {/* arrow → response drawer */}
                    <button
                      onClick={() => onOpenDrawer(engine, prompt.text, prompt.id)}
                      style={{
                        background: "none", border: "none", cursor: "pointer",
                        color: llm ? color : "#d1d5db",
                        fontSize: 13, padding: "2px 4px", flexShrink: 0,
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

            <FanoutQueriesSection promptId={prompt.id} />
          </div>
        </div>
      </td>
    </tr>
  );
}

// ─── prompt row ───────────────────────────────────────────────────────────────
// The inline expanded card is gone — every prompt now has its own question
// page at /prompts/:promptId (metrics, matched page, citations, responses).
function PromptRow({ prompt, onOpenPrompt }) {
  return (
    <tr
      className="border-t border-gray-100 hover:bg-gray-50 cursor-pointer"
      onClick={() => onOpenPrompt(prompt.id)}
    >
      <td className="px-4 py-2.5 pl-10">
        <div className="flex items-center gap-2">
          <span className="text-gray-400 text-xs">→</span>
          <span className="text-sm text-gray-700 truncate max-w-sm" title={prompt.text}>
            "{prompt.text}"
          </span>
        </div>
      </td>
      <td className="px-3 py-2.5"><MetricBadge topic={prompt} /></td>
      <td className="px-3 py-2.5"><SovBadge value={prompt.sov} /></td>
    </tr>
  );
}

// ─── topic header row ─────────────────────────────────────────────────────────
function TopicRow({ topic, expanded, onToggle, onOpenPrompt }) {
  return (
    <>
      <tr
        className="bg-gray-50 cursor-pointer hover:bg-gray-100 border-t border-gray-200"
        onClick={onToggle}
      >
        <td className="px-4 py-3">
          <div className="flex items-center gap-2">
            <span className="text-gray-500 text-xs">{expanded ? "▼" : "▶"}</span>
            <div>
              <p className="text-sm font-semibold text-gray-800">{topic.name}</p>
              <p className="text-xs text-gray-400">{topic.promptCount} prompts</p>
            </div>
          </div>
        </td>
        <td className="px-3 py-3"><MetricBadge topic={topic} /></td>
        <td className="px-3 py-3"><SovBadge value={topic.sov} /></td>
      </tr>

      {expanded && topic.prompts.map(prompt => (
        <PromptRow key={prompt.id} prompt={prompt} onOpenPrompt={onOpenPrompt} />
      ))}
    </>
  );
}

// ─── sortable column header ───────────────────────────────────────────────────
function SortableHeader({ children, field, sort, onSort, className }) {
  const active = sort.field === field;
  return (
    <th className={`${className} cursor-pointer select-none`} onClick={() => onSort(field)}>
      <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
        {children}
        <span style={{ fontSize: 8, color: active ? "#374151" : "#d1d5db", lineHeight: 1 }}>
          {active ? (sort.dir === "asc" ? "▲" : "▼") : "▲▼"}
        </span>
      </span>
    </th>
  );
}

// sort topics list + prompts within each topic by the given field
function applySort(topics, sort) {
  if (!sort.field) return topics;
  const f = sort.field;
  const cmp = (a, b) => sort.dir === "asc"
    ? (a[f] ?? -1) - (b[f] ?? -1)
    : (b[f] ?? -1) - (a[f] ?? -1);
  return [...topics]
    .sort(cmp)
    .map(t => ({ ...t, prompts: [...(t.prompts || [])].sort(cmp) }));
}

// ─── prompt search box ────────────────────────────────────────────────────────
function PromptSearch({ data, onSelect }) {
  const [text, setText] = useState("");
  const [open, setOpen] = useState(false);
  const containerRef = useRef(null);

  const results = useMemo(() => {
    const q = text.trim().toLowerCase();
    if (!q) return [];
    const out = [];
    for (const topic of data) {
      for (const prompt of (topic.prompts || [])) {
        if (prompt.text.toLowerCase().includes(q)) {
          out.push({ ...prompt, topicName: topic.name });
          if (out.length >= 8) return out;
        }
      }
    }
    return out;
  }, [text, data]);

  useEffect(() => {
    function handleClickOutside(e) {
      if (containerRef.current && !containerRef.current.contains(e.target)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  function handleSelect(result) {
    onSelect(result);
    setText("");
    setOpen(false);
  }

  return (
    <div ref={containerRef} style={{ position: "relative", marginBottom: 14 }}>
      <input
        type="text"
        placeholder="Search prompts…"
        value={text}
        onChange={e => { setText(e.target.value); setOpen(true); }}
        onFocus={() => { if (text) setOpen(true); }}
        style={{
          width: "100%",
          fontSize: 13,
          padding: "7px 12px",
          border: "1px solid #e5e7eb",
          borderRadius: 8,
          outline: "none",
          color: "#374151",
          background: "#f9f9f8",
          boxSizing: "border-box",
        }}
      />

      {open && results.length > 0 && (
        <div style={{
          position: "absolute",
          top: "calc(100% + 4px)",
          left: 0, right: 0,
          background: "#fff",
          border: "1px solid #e5e7eb",
          borderRadius: 8,
          boxShadow: "0 4px 16px rgba(0,0,0,0.10)",
          zIndex: 100,
          maxHeight: 300,
          overflowY: "auto",
        }}>
          {results.map((result, i) => (
            <button
              key={result.id}
              onMouseDown={e => { e.preventDefault(); handleSelect(result); }}
              style={{
                display: "block",
                width: "100%",
                textAlign: "left",
                padding: "9px 14px",
                background: "none",
                border: "none",
                borderBottom: i < results.length - 1 ? "1px solid #f5f5f3" : "none",
                cursor: "pointer",
              }}
              className="hover:bg-gray-50"
            >
              <span style={{ fontSize: 11, color: "#9b9b9b", display: "block", marginBottom: 2 }}>
                {result.topicName}
              </span>
              <span style={{ fontSize: 13, color: "#374151", display: "block" }}>
                "{result.text}"
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

// ─── main Prompts component ───────────────────────────────────────────────────
export default function Prompts() {
  const navigate = useNavigate();
  const { days, school } = useFilter();
  const [data,      setData]      = useState([]);
  const [loading,   setLoading]   = useState(true);
  const [error,     setError]     = useState(null);
  const [chartData, setChartData] = useState(null);
  const [expandedTopics, setExpandedTopics] = useState(new Set());
  const [filters, setFilters] = useState({
    engine: "All",
    question_type: "All",
    qc_mentioned: "All",
    sentiment: "All",
  });
  const [sortUnbranded, setSortUnbranded] = useState({ field: null, dir: "desc" });
  const [sortBranded,   setSortBranded]   = useState({ field: null, dir: "desc" });

  const setFilter = (key, value) => setFilters(f => ({ ...f, [key]: value }));

  const openPrompt = (promptId) => navigate(`/prompts/${promptId}`);

  function toggleSortUnbranded(field) {
    setSortUnbranded(prev => ({ field, dir: prev.field === field && prev.dir === "desc" ? "asc" : "desc" }));
  }
  function toggleSortBranded(field) {
    setSortBranded(prev => ({ field, dir: prev.field === field && prev.dir === "desc" ? "asc" : "desc" }));
  }

  const sortedUnbranded = useMemo(
    () => applySort(data.filter(t => t.kind === "mention"), sortUnbranded),
    [data, sortUnbranded]
  );
  const sortedBranded = useMemo(
    () => applySort(data.filter(t => t.kind === "sentiment"), sortBranded),
    [data, sortBranded]
  );

  // Fetch the accordion list + the top chart in parallel
  useEffect(() => {
    setLoading(true);
    setError(null);
    setExpandedTopics(new Set());

    const params = new URLSearchParams();
    if (days) params.append("days", days);
    if (school && school !== "All") params.append("school", school);
    if (filters.engine !== "All") params.append("engine", filters.engine);
    if (filters.question_type !== "All") params.append("question_type", filters.question_type);
    if (filters.qc_mentioned !== "All") params.append("qc_mentioned", filters.qc_mentioned === "Yes");
    if (filters.sentiment !== "All") params.append("sentiment", filters.sentiment);
    const qs = params.toString();

    Promise.all([
      fetch(`${API_BASE_URL}/api/topics?${qs}`).then(r => r.json()),
      fetch(`${API_BASE_URL}/api/topics-over-time?${qs}`).then(r => r.json()),
    ])
      .then(([topics, chart]) => {
        setData(topics);
        setChartData(chart);
        setLoading(false);
      })
      .catch(err => {
        setError(err.message);
        setLoading(false);
      });
  }, [days, school, filters]);

  function toggleTopic(name) {
    setExpandedTopics(prev => {
      const next = new Set(prev);
      next.has(name) ? next.delete(name) : next.add(name);
      return next;
    });
  }

  // Search results jump straight to the prompt's question page
  const selectSearchResult = (result) => openPrompt(result.id);

  return (
    <>
      {/* Top line graph */}
      <TopicsOverTimeChart chartData={chartData} />

      {/* Filters */}
      <div className="bg-white border border-gray-200 rounded-lg p-4" style={{ marginBottom: 12 }}>
        <p className="font-medium mb-3">Filters</p>
        <PromptSearch data={data} onSelect={selectSearchResult} />
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <FilterSelect label="Engine" value={filters.engine} onChange={v => setFilter("engine", v)} options={ENGINES} />
          <FilterSelect label="Question type" value={filters.question_type} onChange={v => setFilter("question_type", v)} options={TYPES} />
          <FilterSelect label="QC mentioned" value={filters.qc_mentioned} onChange={v => setFilter("qc_mentioned", v)} options={["All", "Yes", "No"]} />
          <FilterSelect label="Sentiment" value={filters.sentiment} onChange={v => setFilter("sentiment", v)} options={SENTIMENTS} />
        </div>
      </div>

      {/* Accordion tables */}
      {loading ? (
        <p className="state-msg">Loading…</p>
      ) : error ? (
        <p className="state-msg state-msg--error">Error: {error}</p>
      ) : !data.length ? (
        <p className="state-empty">
          {(school === "All" || !school) && Object.values(filters).every(v => v === "All")
            ? "No topic data yet. Run the pipeline to collect responses."
            : "No prompts match your filters."}
        </p>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>

          {/* ── Unbranded ──────────────────────────────────────────────── */}
          {sortedUnbranded.length > 0 && (
            <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
              <div style={{ padding: "6px 16px", background: "#f8f7f5", borderBottom: "1px solid #e5e7eb" }}>
                <span style={{ fontSize: 11, fontWeight: 700, color: "#6b6b6b", textTransform: "uppercase", letterSpacing: "0.06em" }}>
                  Unbranded
                </span>
              </div>
              <table className="w-full text-left table-fixed">
                <colgroup>
                  <col style={{ width: "55%" }} />
                  <col style={{ width: "22.5%" }} />
                  <col style={{ width: "22.5%" }} />
                </colgroup>
                <thead>
                  <tr className="border-b border-gray-200 bg-gray-50">
                    <th className="px-4 py-2.5 text-xs text-gray-500 uppercase font-medium">Prompt / Topic</th>
                    <SortableHeader field="visibility" sort={sortUnbranded} onSort={toggleSortUnbranded} className="px-3 py-2.5 text-xs text-gray-500 uppercase font-medium">Visibility</SortableHeader>
                    <SortableHeader field="sov"        sort={sortUnbranded} onSort={toggleSortUnbranded} className="px-3 py-2.5 text-xs text-gray-500 uppercase font-medium">Share of Voice</SortableHeader>
                  </tr>
                </thead>
                <tbody>
                  {sortedUnbranded.map(topic => (
                    <TopicRow
                      key={topic.name}
                      topic={topic}
                      expanded={expandedTopics.has(topic.name)}
                      onToggle={() => toggleTopic(topic.name)}
                      onOpenPrompt={openPrompt}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* ── Branded ────────────────────────────────────────────────── */}
          {sortedBranded.length > 0 && (
            <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
              <div style={{ padding: "6px 16px", background: "#f8f7f5", borderBottom: "1px solid #e5e7eb" }}>
                <span style={{ fontSize: 11, fontWeight: 700, color: "#6b6b6b", textTransform: "uppercase", letterSpacing: "0.06em" }}>
                  Branded
                </span>
              </div>
              <table className="w-full text-left table-fixed">
                <colgroup>
                  <col style={{ width: "55%" }} />
                  <col style={{ width: "22.5%" }} />
                  <col style={{ width: "22.5%" }} />
                </colgroup>
                <thead>
                  <tr className="border-b border-gray-200 bg-gray-50">
                    <th className="px-4 py-2.5 text-xs text-gray-500 uppercase font-medium">Prompt / Topic</th>
                    <SortableHeader field="sentiment" sort={sortBranded} onSort={toggleSortBranded} className="px-3 py-2.5 text-xs text-gray-500 uppercase font-medium">Sentiment</SortableHeader>
                    <SortableHeader field="sov"       sort={sortBranded} onSort={toggleSortBranded} className="px-3 py-2.5 text-xs text-gray-500 uppercase font-medium">Share of Voice</SortableHeader>
                  </tr>
                </thead>
                <tbody>
                  {sortedBranded.map(topic => (
                    <TopicRow
                      key={topic.name}
                      topic={topic}
                      expanded={expandedTopics.has(topic.name)}
                      onToggle={() => toggleTopic(topic.name)}
                      onOpenPrompt={openPrompt}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          )}

        </div>
      )}
    </>
  );
}
