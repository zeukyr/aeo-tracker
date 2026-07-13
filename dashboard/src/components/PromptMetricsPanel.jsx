import {
  LineChart, Line,
  AreaChart, Area,
  XAxis, YAxis, Tooltip,
  ResponsiveContainer,
} from "recharts";
import { LLM_ENGINES, LLM_LABELS, LLM_COLORS, QC_BLUE } from "../lib/llm";

// ─── shared chart tooltip ─────────────────────────────────────────────────────
export function ChartTooltip({ active, payload, label }) {
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

export default function PromptMetricsPanel({ prompt, detail, onOpenDrawer, showDrawerButtons = true }) {
  const { kind, timeseries, competitors, llms } = detail;

  return (
    <div className="prompt-metrics-panel">
      <p className="prompt-metrics-panel__question">"{prompt.text}"</p>

      <div className="prompt-metrics-panel__layout">
        <div className="prompt-metrics-panel__chart">
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

        <div className="prompt-metrics-panel__competitors">
          <p className="text-xs font-medium text-gray-500 uppercase mb-2">Top competitors</p>
          <CompetitorRanking competitors={competitors} />
        </div>
      </div>

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
                <span style={{ fontSize: 12, fontWeight: 600, color, width: 82, flexShrink: 0 }}>
                  {LLM_LABELS[engine]}
                </span>

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

                {showDrawerButtons && (
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
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
