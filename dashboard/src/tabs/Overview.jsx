import { useEffect, useRef, useState } from "react";
import { API_BASE_URL } from "../config";
import { useFilter } from "../context/useFilter";

function DiffBadge({ diff }) {
  if (diff === null || diff === undefined)
    return <span className="badge badge--neutral">— no data</span>;
  if (diff === 0)
    return <span className="badge badge--neutral">— no change</span>;
  const positive = diff > 0;
  return (
    <span className={`badge ${positive ? "badge--up" : "badge--down"}`}>
      {positive ? "↑" : "↓"} {Math.abs(diff)}% vs prev
    </span>
  );
}

function MetricCard({ label, value, diff, highlight }) {
  return (
    <div className={`metric-card ${highlight ? "metric-card--highlight" : ""}`}>
      <p className="metric-label">{label}</p>
      <p className="metric-value">{value}</p>
      <DiffBadge diff={diff} />
    </div>
  );
}

function BrandBar({ name, pct, delta, isYou, color }) {
  return (
    <div>
      <div className="brand-row__header">
        <div className="brand-row__name">
          {isYou && <span className="badge badge--you">YOU</span>}
          <span className={`brand-name ${isYou ? "brand-name--you" : ""}`}>{name}</span>
        </div>
        <div className="brand-row__stats">
          <span className="brand-pct">{pct}%</span>
          {delta !== null && (
            <span className={`brand-delta ${delta >= 0 ? "brand-delta--up" : "brand-delta--down"}`}>
              {delta >= 0 ? "+" : ""}{delta}%
            </span>
          )}
        </div>
      </div>
      <div className="bar-track">
        <div className="bar-fill" style={{ width: `${pct}%`, background: color }} />
      </div>
    </div>
  );
}

function MentionChart({ data }) {
  const canvasRef = useRef(null);
  const chartRef = useRef(null);

  useEffect(() => {
    if (!data || data.length === 0) return;

    const buildChart = () => {
      if (!window.Chart) return;
      if (chartRef.current) chartRef.current.destroy();

      chartRef.current = new window.Chart(canvasRef.current, {
        type: "line",
        data: {
          labels: data.map((d) => d.day),
          datasets: [
            {
              label: "ChatGPT",
              data: data.map((d) => d.chatgpt ?? null),
              borderColor: "#378add",
              backgroundColor: "#378add",
              borderWidth: 2,
              pointRadius: 4,
              pointHoverRadius: 6,
              pointBackgroundColor: "#378add",
              tension: 0.3,
              spanGaps: true,
            },
            {
              label: "Perplexity",
              data: data.map((d) => d.perplexity ?? null),
              borderColor: "#1d9e75",
              backgroundColor: "#1d9e75",
              borderWidth: 2,
              pointRadius: 4,
              pointHoverRadius: 6,
              pointBackgroundColor: "#1d9e75",
              borderDash: [4, 3],
              tension: 0.3,
              spanGaps: true,
            },
            {
              label: "Gemini",
              data: data.map((d) => d.gemini ?? null),
              borderColor: "#ba7517",
              backgroundColor: "#ba7517",
              borderWidth: 2,
              pointRadius: 4,
              pointHoverRadius: 6,
              pointBackgroundColor: "#ba7517",
              borderDash: [2, 2],
              tension: 0.3,
              spanGaps: true,
            },
          ],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: { display: false },
            tooltip: {
              callbacks: { label: (ctx) => ` ${ctx.dataset.label}: ${ctx.parsed.y}%` },
            },
          },
          scales: {
            x: {
              grid: { display: false },
              ticks: { font: { size: 11 }, color: "#888780", maxRotation: 0, autoSkip: true, maxTicksLimit: 8 },
            },
            y: {
              min: 0,
              max: 100,
              grid: { color: "rgba(136,135,128,0.12)" },
              ticks: { font: { size: 11 }, color: "#888780", callback: (v) => `${v}%` },
            },
          },
        },
      });
    };

    if (window.Chart) {
      buildChart();
    } else {
      const script = document.createElement("script");
      script.src = "https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js";
      script.onload = buildChart;
      document.head.appendChild(script);
    }

    return () => {
      if (chartRef.current) { chartRef.current.destroy(); chartRef.current = null; }
    };
  }, [data]);

  return (
    <div style={{ position: "relative", width: "100%", height: "240px" }}>
      <canvas ref={canvasRef} role="img" aria-label="Line chart showing QC mention rate by AI engine over time">
        Mention rate trends for ChatGPT, Perplexity, and Gemini.
      </canvas>
    </div>
  );
}

function Overview() {
  const { days } = useFilter();
  const [mentionData, setMentionData] = useState([]);
  const [summary, setSummary] = useState(null);
  const [error, setError] = useState(null);

  const loading = summary === null && error === null;

  useEffect(() => {
    const params = new URLSearchParams();
    if (days) params.append("days", days);

    Promise.all([
      fetch(`${API_BASE_URL}/api/mention-rate-by-engine?${params}`).then((r) => r.json()),
      fetch(`${API_BASE_URL}/api/summary?${params}`).then((r) => r.json()),
    ])
      .then(([mentionData, summaryData]) => {
        setMentionData(mentionData);
        setSummary(summaryData);
      })
      .catch((err) => setError(err.message));
  }, [days]);

  if (loading) return <p className="state-msg">Loading...</p>;
  if (error)   return <p className="state-msg state-msg--error">Error: {error}</p>;

  const competitors = summary.top_competitors ?? [];

  return (
    <div>
      <div className="metric-grid">
        <MetricCard label="Mention rate"       value={`${summary.mention_rate}%`}                          diff={summary.mention_rate_diff} />
        <MetricCard label="Visibility score"   value={summary.visibility_score ?? "--"}                    diff={summary.visibility_score_diff} />
        <MetricCard label="Positive sentiment" value={`${summary.positive_sentiment_rate}%`}               diff={summary.positive_sentiment_diff} />
        <MetricCard label="Citation rate"      value={summary.citation_rate ? `${summary.citation_rate}%` : "--"} diff={summary.citation_rate_diff} />
        <MetricCard label="Share of voice"     value={summary.sov ? `${summary.sov}%` : "--"} diff={summary.sov_diff} />
        <MetricCard label="Average rank"     value={summary.avg_rank ? `${summary.avg_rank}` : "--"} diff={summary.avg_rank_diff} />
      </div>

      <div className="chart-section">
        <div className="card">
          <p className="panel-title">Mention rate by engine</p>
          <p className="panel-subtitle">Daily mention rate across models</p>
          <div className="chart-legend">
            <span className="legend-item">
              <span className="legend-dot" style={{ background: "#378add" }} />
              ChatGPT
            </span>
            <span className="legend-item">
              <span className="legend-dot" style={{ background: "#1d9e75" }} />
              Perplexity
            </span>
            <span className="legend-item">
              <span className="legend-dot" style={{ background: "#ba7517" }} />
              Gemini
            </span>
          </div>
          <MentionChart data={mentionData} />
        </div>

        <div className="card">
          <p className="panel-title">Top brands by mentions</p>
          <p className="panel-subtitle">Share across all responses</p>
          <div className="brand-list">
            <BrandBar
              name="QC Pet Studies"
              pct={summary.qc_mention_rate ?? summary.mention_rate ?? 0}
              delta={summary.mention_rate_diff ?? null}
              isYou
              color="#378add"
            />
            {competitors.map((c) => (
              <BrandBar key={c.name} name={c.name} pct={c.mention_rate} delta={c.diff ?? null} color="#888780" />
            ))}
            {competitors.length === 0 && (
              <p className="state-empty">No competitor data yet.</p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export default Overview;