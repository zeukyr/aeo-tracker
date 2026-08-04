import { useEffect, useState } from "react";
import { API_BASE_URL } from "../config";
import { useFilter } from "../context/useFilter";
import { TagList } from "../components/TagList";
import { SentimentTrendChart } from "../components/SentimentTrendChart";

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

function Sentiment() {
  const { days, school } = useFilter();
  const [sentimentData, setSentimentData] = useState([]);
  const [concerns, setConcerns] = useState([]);
  const [positives, setPositives] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const params = new URLSearchParams();
    if (days) params.append("days", days);
    if (school && school !== "All") params.append("school", school);

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
  }, [days, school]);

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
        <SentimentTrendChart data={sentimentData} />
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