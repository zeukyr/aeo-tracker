import { useEffect, useRef, useState } from "react";
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine
} from "recharts";
import { API_BASE_URL } from "../config";
import { useFilter } from "../context/useFilter";
import { TagList } from "../components/TagList";
import { SentimentTrendChart } from "../components/SentimentTrendChart";
import { SchoolFilter, CitationList, TabBar, filterData } from "../components/CitationWidgets";

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

function MetricCard({ label, value, diff, detail, highlight, tooltip }) {
  return (
    <div className={`metric-card ${highlight ? "metric-card--highlight" : ""}`}>
      <p className="metric-label">{label}</p>
      <p className="metric-value">
        {tooltip ? (
          <span className="metric-value-tip">
            {value}
            <span className="metric-tip-popup">{tooltip}</span>
          </span>
        ) : value}
      </p>
      {detail && <p className="metric-detail">{detail}</p>}
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

function RankRow({ rank, name, count }) {
  return (
    <div className="rank-row">
      <span className="rank-row__index">{rank}</span>
      <span className="rank-row__name">{name}</span>
      <span className="rank-row__count">{count}</span>
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

function SentimentScoreChart({ data }) {
  // linearGradient with default objectBoundingBox units scales to the rendered
  // line's own min/max, not the fixed -50..50 axis domain — so the split point
  // has to be computed from the data's actual range to land exactly on zero.
  const scores = data.map((d) => d.score).filter((v) => v != null);
  const max = scores.length ? Math.max(...scores) : 0;
  const min = scores.length ? Math.min(...scores) : 0;
  const zeroOffsetPct = max === min
    ? (max >= 0 ? 100 : 0)
    : Math.min(100, Math.max(0, (max / (max - min)) * 100));

  return (
    <ResponsiveContainer width="100%" height={220}>
      <LineChart data={data} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
        <defs>
          <linearGradient id="sentimentScoreSplit" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%"                    stopColor="#3b6d11" />
            <stop offset={`${zeroOffsetPct}%`}   stopColor="#3b6d11" />
            <stop offset={`${zeroOffsetPct}%`}   stopColor="#a32d2d" />
            <stop offset="100%"                  stopColor="#a32d2d" />
          </linearGradient>
        </defs>
        <XAxis dataKey="day" tick={{ fontSize: 11, fill: "#888780" }} axisLine={false} tickLine={false} />
        <YAxis domain={[-50, 50]} tick={{ fontSize: 11, fill: "#888780" }} axisLine={false} tickLine={false} width={32} />
        <ReferenceLine y={0} stroke="#e5e5e2" />
        <Tooltip formatter={(v) => [v, "Sentiment score"]} labelStyle={{ color: "#6b6b6b" }} contentStyle={{ fontSize: 12, borderRadius: 8 }} />
        <Line type="monotone" dataKey="score" stroke="url(#sentimentScoreSplit)" strokeWidth={2} dot={false} />
      </LineChart>
    </ResponsiveContainer>
  );
}

function Overview() {
  const { days, school } = useFilter();
  const [mentionData, setMentionData] = useState([]);
  const [summary, setSummary] = useState(null);
  const [competitorRanking, setCompetitorRanking] = useState([]);
  const [positives, setPositives] = useState([]);
  const [concerns, setConcerns] = useState([]);
  const [sentimentScoreTrend, setSentimentScoreTrend] = useState([]);
  const [sentimentDistribution, setSentimentDistribution] = useState([]);
  const [mentionCitations, setMentionCitations] = useState([]);
  const [sentimentCitations, setSentimentCitations] = useState([]);
  const [mentionSchool, setMentionSchool] = useState("All");
  const [sentimentSchool, setSentimentSchool] = useState("All");
  const [citationsTab, setCitationsTab] = useState("about");
  const [error, setError] = useState(null);

  const loading = summary === null && error === null;

  useEffect(() => {
    const params = new URLSearchParams();
    if (days) params.append("days", days);
    if (school && school !== "All") params.append("school", school);

    Promise.all([
      fetch(`${API_BASE_URL}/api/mention-rate-by-engine?${params}`).then((r) => r.json()),
      fetch(`${API_BASE_URL}/api/summary?${params}`).then((r) => r.json()),
      fetch(`${API_BASE_URL}/api/top-competitors-by-school?${params}`).then((r) => r.json()),
      fetch(`${API_BASE_URL}/api/top-positives?${params}`).then((r) => r.json()),
      fetch(`${API_BASE_URL}/api/top-concerns?${params}`).then((r) => r.json()),
      fetch(`${API_BASE_URL}/api/sentiment-score-trend?${params}`).then((r) => r.json()),
      fetch(`${API_BASE_URL}/api/sentiment-distribution?${params}`).then((r) => r.json()),
      fetch(`${API_BASE_URL}/api/citations-by-school?${params}`).then((r) => r.json()),
      fetch(`${API_BASE_URL}/api/sentiment-citations?${params}`).then((r) => r.json()),
    ])
      .then(([mentionData, summaryData, rankingData, positivesData, concernsData, scoreTrendData, distributionData, mentionCitationsData, sentimentCitationsData]) => {
        setMentionData(mentionData);
        setSummary(summaryData);
        setCompetitorRanking(rankingData);
        setPositives(positivesData);
        setConcerns(concernsData);
        setSentimentScoreTrend(scoreTrendData);
        setSentimentDistribution(distributionData);
        setMentionCitations(mentionCitationsData);
        setSentimentCitations(sentimentCitationsData);
      })
      .catch((err) => setError(err.message));
  }, [days, school]);

  if (loading) return <p className="state-msg">Loading...</p>;
  if (error)   return <p className="state-msg state-msg--error">Error: {error}</p>;

  const competitors = summary.top_competitors ?? [];

  const topCompetitors = Object.values(
    competitorRanking.reduce((acc, c) => {
      if (!acc[c.competitor]) acc[c.competitor] = { name: c.competitor, count: 0 };
      acc[c.competitor].count += c.count;
      return acc;
    }, {})
  )
    .sort((a, b) => b.count - a.count)
    .slice(0, 20);

  const mentionFiltered   = filterData(mentionCitations, mentionSchool);
  const sentimentFiltered = filterData(sentimentCitations, sentimentSchool);

  return (
    <div>
      <div className="metric-grid">
        <MetricCard
          label="Mention rate"
          value={`${summary.mention_rate}%`}
          detail={summary.mention_total ? `${summary.mention_count}/${summary.mention_total} responses` : null}
          diff={summary.mention_rate_diff}
          tooltip="% of tracked AI responses where QC is mentioned by name."
        />
        <MetricCard
          label="Visibility score"
          value={summary.visibility_score ?? "--"}
          diff={summary.visibility_score_diff}
          tooltip="Composite score: mention rate (40%) + rank score (45%) + citation quality (15%)."
        />
        <MetricCard
          label="Positive sentiment"
          value={`${summary.positive_sentiment_rate}%`}
          detail={summary.sentiment_total
            ? `${summary.positive_sentiment_count}/${summary.sentiment_total} · ${summary.neutral_sentiment_count} neutral, ${summary.negative_sentiment_count} negative${summary.sentiment_score != null ? ` · score ${summary.sentiment_score > 0 ? "+" : ""}${summary.sentiment_score}` : ""}`
            : null}
          diff={summary.positive_sentiment_diff}
          tooltip="% of sentiment-analyzed responses where the AI's tone toward QC is classified positive (vs. neutral or negative)."
        />
        <MetricCard
          label="Citation rate"
          value={summary.citation_rate ? `${summary.citation_rate}%` : "--"}
          diff={summary.citation_rate_diff}
          tooltip="% of responses where a QC-owned page is cited as a source."
        />
        <MetricCard
          label="Share of voice"
          value={summary.sov ? `${summary.sov}%` : "--"}
          diff={summary.sov_diff}
          tooltip="QC's mentions as a % of all brand mentions (QC + competitors) across responses."
        />
        <MetricCard
          label="Average rank"
          value={summary.avg_rank ? (
            <>
              {summary.avg_rank}
              {summary.avg_field_size != null && (
                <span style={{ fontSize: 13, fontWeight: 400, color: "#9b9b9b" }}> /{summary.avg_field_size}</span>
              )}
            </>
          ) : "--"}
          diff={summary.avg_rank_diff}
          detail={summary.avg_rank_score != null ? `normalized: ${summary.avg_rank_score}/100` : undefined}
          tooltip="Average position QC appears at among all businesses listed, when mentioned. /x shows the average field size."
        />
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
              name={school && school !== "All" ? school : "QC (all schools)"}
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

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginTop: 12 }}>
        <div className="card">
          <p className="panel-title">Sentiment score over time</p>
          <p className="panel-subtitle">Weighted score from -50 to 50, based on sentiment, competitor comparisons, and concerns/positives raised</p>
          <SentimentScoreChart data={sentimentScoreTrend} />

          <div style={{ marginTop: 16, paddingTop: 16, borderTop: "0.5px solid rgba(0,0,0,0.08)" }}>
            <p className="panel-title">Sentiment breakdown</p>
            <p className="panel-subtitle">Positive, neutral, and negative mention share over time</p>
            <SentimentTrendChart data={sentimentDistribution} />
          </div>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div className="card">
            <p className="panel-title">Top positives</p>
            <p className="panel-subtitle">What AI says in QC's favour</p>
            <TagList items={positives} labelKey="positive" countKey="count" color="#3b6d11" bg="#eaf3de" />
          </div>
          <div className="card">
            <p className="panel-title">Top concerns</p>
            <p className="panel-subtitle">Caveats or negatives raised about QC</p>
            <TagList items={concerns} labelKey="concern" countKey="count" color="#a32d2d" bg="#fcebeb" />
          </div>
        </div>
      </div>

      <div style={{ borderTop: "0.5px solid rgba(0,0,0,0.10)", margin: "20px 0" }} />

      <div className="card">
        <TabBar
          tabs={[
            { id: "about",     label: "About QC" },
            { id: "discovery", label: "Course discovery" },
          ]}
          active={citationsTab}
          onChange={setCitationsTab}
        />

        {citationsTab === "about" && (
          <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
              <div>
                <p className="panel-title">Sources used when AI answers questions about QC</p>
                <p className="panel-subtitle">From credibility and competition questions — these directly shape QC's reputation</p>
              </div>
              <SchoolFilter value={sentimentSchool} onChange={setSentimentSchool} />
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20 }}>
              <div>
                <p style={{ fontSize: 12, fontWeight: 500, color: "#6b6b6b", marginBottom: 10 }}>QC owned</p>
                <CitationList data={sentimentFiltered.qc} color="#378add" emptyMsg="No QC-owned sources found." />
              </div>
              <div>
                <p style={{ fontSize: 12, fontWeight: 500, color: "#6b6b6b", marginBottom: 4 }}>External</p>
                <p style={{ fontSize: 11, color: "#9b9b9b", marginBottom: 10 }}>Review sites, Reddit threads, competitor pages shaping AI's view of QC</p>
                <CitationList data={sentimentFiltered.external} color="#a32d2d" emptyMsg="No external sources found." />
              </div>
            </div>
          </div>
        )}

        {citationsTab === "discovery" && (
          <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
              <div>
                <p className="panel-title">Sources used when AI recommends courses generally</p>
                <p className="panel-subtitle">From course and general questions — what QC is competing against for visibility</p>
              </div>
              <SchoolFilter value={mentionSchool} onChange={setMentionSchool} />
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20 }}>
              <div>
                <p style={{ fontSize: 12, fontWeight: 500, color: "#6b6b6b", marginBottom: 10 }}>QC owned</p>
                <CitationList data={mentionFiltered.qc} color="#378add" emptyMsg="No QC-owned sources found." />
              </div>
              <div>
                <p style={{ fontSize: 12, fontWeight: 500, color: "#6b6b6b", marginBottom: 4 }}>External</p>
                <p style={{ fontSize: 11, color: "#9b9b9b", marginBottom: 10 }}>Course aggregators, competitor pages, job boards cited instead of QC</p>
                <CitationList data={mentionFiltered.external} color="#7c3aed" emptyMsg="No external sources found." />
              </div>
            </div>
          </div>
        )}
      </div>

      <div className="card" style={{ marginTop: 12 }}>
        <p className="panel-title">Top competitors</p>
        <p className="panel-subtitle">Ranked by total mentions across responses</p>
        <div className="rank-list">
          {topCompetitors.map((c, i) => (
            <RankRow key={c.name} rank={i + 1} name={c.name} count={c.count} />
          ))}
          {topCompetitors.length === 0 && (
            <p className="state-empty">No competitor data yet.</p>
          )}
        </div>
      </div>
    </div>
  );
}

export default Overview;