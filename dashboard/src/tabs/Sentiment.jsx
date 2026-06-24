import { useEffect, useState } from "react";
import {
  AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer
} from "recharts";
import { API_BASE_URL } from "../config";
import { useFilter } from "../context/useFilter";

function CustomTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return (
    <div style={{
      background: "#fff",
      border: "0.5px solid rgba(0,0,0,0.10)",
      borderRadius: 8,
      padding: "8px 12px",
      fontSize: 13,
      boxShadow: "0 2px 8px rgba(0,0,0,0.08)"
    }}>
      <p style={{ color: "#6b6b6b", marginBottom: 6, fontSize: 12 }}>{label}</p>
      {payload.map(p => (
        <p key={p.name} style={{ color: p.color, fontWeight: 500, margin: "2px 0" }}>
          {p.name}: {p.value}%
        </p>
      ))}
    </div>
  );
}

function SentimentPill({ label, value, color, bg }) {
  return (
    <div style={{
      background: bg,
      borderRadius: 10,
      padding: "12px 16px",
      display: "flex",
      flexDirection: "column",
      gap: 4,
      flex: 1,
      minWidth: 0,
    }}>
      <p style={{ fontSize: 11, fontWeight: 500, color, textTransform: "uppercase", letterSpacing: "0.04em" }}>{label}</p>
      <p style={{ fontSize: 26, fontWeight: 500, color, lineHeight: 1 }}>{value}%</p>
    </div>
  );
}

function TagList({ items, labelKey, countKey, color, bg }) {
  if (!items?.length) return <p className="state-empty">No data yet.</p>;
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
      {items.map((item, i) => {
        const maxCount = items[0]?.[countKey] ?? 1;
        const opacity = 0.4 + 0.6 * (item[countKey] / maxCount);
        return (
          <span key={i} style={{
            background: bg,
            color,
            opacity,
            fontSize: 12,
            fontWeight: 500,
            padding: "5px 11px",
            borderRadius: 99,
            whiteSpace: "nowrap",
            cursor: "default",
          }}
            title={`${item[countKey]} mentions`}
          >
            {item[labelKey]}
          </span>
        );
      })}
    </div>
  );
}

function Sentiment() {
  const { days } = useFilter();
  const [sentimentData, setSentimentData] = useState([]);
  const [concerns, setConcerns] = useState([]);
  const [positives, setPositives] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const params = new URLSearchParams();
    if (days) params.append("days", days);

    Promise.all([
      fetch(`${API_BASE_URL}/api/sentiment-distribution?${params}`).then(r => r.json()),
      fetch(`${API_BASE_URL}/api/top-concerns?${params}`).then(r => r.json()),
      fetch(`${API_BASE_URL}/api/top-positives?${params}`).then(r => r.json()),
    ])
      .then(([sentiment, concerns, positives]) => {
        setSentimentData(sentiment);
        setConcerns(concerns);
        setPositives(positives);
        setLoading(false);
      })
      .catch(err => {
        setError(err.message);
        setLoading(false);
      });
  }, [days]);

  if (loading) return <p className="state-msg">Loading...</p>;
  if (error)   return <p className="state-msg state-msg--error">Error: {error}</p>;

  const latest = sentimentData[sentimentData.length - 1] ?? {};

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>

      {/* Summary pills */}
      <div style={{ display: "flex", gap: 10 }}>
        <SentimentPill label="Positive"  value={latest.positive ?? "--"} color="#3b6d11" bg="#eaf3de" />
        <SentimentPill label="Neutral"   value={latest.neutral  ?? "--"} color="#854f0b" bg="#faeeda" />
        <SentimentPill label="Negative"  value={latest.negative ?? "--"} color="#a32d2d" bg="#fcebeb" />
      </div>

      {/* Sentiment over time */}
      <div className="card">
        <p className="panel-title">Sentiment over time</p>
        <p className="panel-subtitle">Breakdown of positive, neutral, and negative mentions</p>

        <div style={{ display: "flex", gap: 14, marginBottom: 12, flexWrap: "wrap" }}>
          {[
            { label: "Positive", color: "#3b6d11", bg: "#eaf3de" },
            { label: "Neutral",  color: "#854f0b", bg: "#faeeda" },
            { label: "Negative", color: "#a32d2d", bg: "#fcebeb" },
          ].map(({ label, color }) => (
            <span key={label} style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 12, color: "#6b6b6b" }}>
              <span style={{ width: 8, height: 8, borderRadius: "50%", background: color, flexShrink: 0 }} />
              {label}
            </span>
          ))}
        </div>

        <ResponsiveContainer width="100%" height={220}>
          <AreaChart data={sentimentData} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
            <defs>
              <linearGradient id="gradPos" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%"  stopColor="#3b6d11" stopOpacity={0.15} />
                <stop offset="95%" stopColor="#3b6d11" stopOpacity={0.02} />
              </linearGradient>
              <linearGradient id="gradNeu" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%"  stopColor="#854f0b" stopOpacity={0.15} />
                <stop offset="95%" stopColor="#854f0b" stopOpacity={0.02} />
              </linearGradient>
              <linearGradient id="gradNeg" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%"  stopColor="#a32d2d" stopOpacity={0.15} />
                <stop offset="95%" stopColor="#a32d2d" stopOpacity={0.02} />
              </linearGradient>
            </defs>
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
            />
            <Tooltip content={<CustomTooltip />} />
            <Area type="monotone" dataKey="positive" stroke="#3b6d11" strokeWidth={2} fill="url(#gradPos)" name="Positive" dot={false} />
            <Area type="monotone" dataKey="neutral"  stroke="#854f0b" strokeWidth={2} fill="url(#gradNeu)" name="Neutral"  dot={false} />
            <Area type="monotone" dataKey="negative" stroke="#a32d2d" strokeWidth={2} fill="url(#gradNeg)" name="Negative" dot={false} />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      {/* Tag clouds */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
        <div className="card">
          <p className="panel-title">Top positives</p>
          <p className="panel-subtitle">What AI says in QC's favour — larger opacity = more frequent</p>
          <TagList items={positives} labelKey="positive" countKey="count" color="#3b6d11" bg="#eaf3de" />
        </div>

        <div className="card">
          <p className="panel-title">Top concerns</p>
          <p className="panel-subtitle">Caveats or negatives raised about QC — larger opacity = more frequent</p>
          <TagList items={concerns} labelKey="concern" countKey="count" color="#a32d2d" bg="#fcebeb" />
        </div>
      </div>

    </div>
  );
}

export default Sentiment;