import { useEffect, useState } from "react";
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

  return (
    <div className="card" style={{ marginBottom: 12 }}>
      <p className="panel-title">Topics over time</p>
      <p className="panel-subtitle">Visibility (mention topics) or positive-sentiment rate (credibility/comparison topics)</p>

      {/* legend */}
      <div style={{ display: "flex", gap: 14, marginBottom: 12, flexWrap: "wrap" }}>
        {topics.map((t, i) => {
          const color = TOPIC_COLORS[t.name] || FALLBACK_COLORS[i % FALLBACK_COLORS.length];
          return (
            <span key={t.name} style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 12, color: "#6b6b6b" }}>
              <span style={{ width: 8, height: 8, borderRadius: "50%", background: color, flexShrink: 0 }} />
              {t.name}
            </span>
          );
        })}
      </div>

      {series?.length ? (
        <ResponsiveContainer width="100%" height={220}>
          <LineChart data={series} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
            <XAxis
              dataKey="day"
              tick={{ fontSize: 11, fill: "#888780" }}
              axisLine={false}
              tickLine={false}
            />
            <YAxis
              tickFormatter={v => `${v}%`}
              tick={{ fontSize: 11, fill: "#888780" }}
              axisLine={false}
              tickLine={false}
              width={36}
              domain={[0, 100]}
            />
            <Tooltip content={<ChartTooltip />} />
            {topics.map((t, i) => {
              const color = TOPIC_COLORS[t.name] || FALLBACK_COLORS[i % FALLBACK_COLORS.length];
              return (
                <Line
                  key={t.name}
                  type="monotone"
                  dataKey={t.name}
                  name={t.name}
                  stroke={color}
                  strokeWidth={2}
                  dot={false}
                  connectNulls
                />
              );
            })}
          </LineChart>
        </ResponsiveContainer>
      ) : (
        <p className="state-empty">No time-series data yet.</p>
      )}
    </div>
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

  const setFilter = (key, value) => setFilters(f => ({ ...f, [key]: value }));

  const openPrompt = (promptId) => navigate(`/prompts/${promptId}`);

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

  return (
    <>
      {/* Top line graph */}
      <TopicsOverTimeChart chartData={chartData} />

      {/* Filters */}
      <div className="bg-white border border-gray-200 rounded-lg p-4" style={{ marginBottom: 12 }}>
        <p className="font-medium mb-3">Filters</p>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <FilterSelect label="Engine" value={filters.engine} onChange={v => setFilter("engine", v)} options={ENGINES} />
          <FilterSelect label="Question type" value={filters.question_type} onChange={v => setFilter("question_type", v)} options={TYPES} />
          <FilterSelect label="QC mentioned" value={filters.qc_mentioned} onChange={v => setFilter("qc_mentioned", v)} options={["All", "Yes", "No"]} />
          <FilterSelect label="Sentiment" value={filters.sentiment} onChange={v => setFilter("sentiment", v)} options={SENTIMENTS} />
        </div>
      </div>

      {/* Accordion table */}
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
        <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
          <table className="w-full text-left table-fixed">
            <colgroup>
              <col style={{ width: "55%" }} />
              <col style={{ width: "22.5%" }} />
              <col style={{ width: "22.5%" }} />
            </colgroup>
            <thead>
              <tr className="border-b border-gray-200 bg-gray-50">
                <th className="px-4 py-2.5 text-xs text-gray-500 uppercase font-medium">Prompt / Topic</th>
                <th className="px-3 py-2.5 text-xs text-gray-500 uppercase font-medium">Visibility / Sentiment</th>
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
                  onOpenPrompt={openPrompt}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
